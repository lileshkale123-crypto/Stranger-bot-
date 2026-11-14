import time
from datetime import datetime, timezone

import asyncpg

pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           BIGINT PRIMARY KEY,
    gender       TEXT,
    age_bracket  TEXT,
    region       TEXT,
    premium_until TIMESTAMPTZ,
    banned       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- referral columns (idempotent: safe to run on the live database)
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_credited BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_rewards INT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS users_referred_by_idx ON users (referred_by) WHERE referral_credited;

CREATE TABLE IF NOT EXISTS payments (
    id                 BIGSERIAL PRIMARY KEY,
    user_id            BIGINT NOT NULL,
    plan               TEXT NOT NULL,
    stars              INT NOT NULL,
    telegram_charge_id TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    refunded           BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX IF NOT EXISTS payments_charge_uq ON payments (telegram_charge_id);

CREATE TABLE IF NOT EXISTS reports (
    id          BIGSERIAL PRIMARY KEY,
    reporter_id BIGINT NOT NULL,
    reported_id BIGINT NOT NULL,
    reason      TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_chats (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    seconds    INT NOT NULL,
    msgs       INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ai_chats_created_idx ON ai_chats (created_at);

CREATE TABLE IF NOT EXISTS bot_state (
    key        TEXT PRIMARY KEY,
    boot_id    TEXT NOT NULL,
    data       TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Only these columns may be changed through set_field (prevents SQL injection)
EDITABLE_FIELDS = {"gender", "age_bracket", "region"}

# Small in-memory cache so most messages skip the database entirely
_CACHE_TTL = 20.0
_CACHE_MAX = 20000
_cache: dict[int, tuple[float, asyncpg.Record | None]] = {}


def invalidate(user_id: int) -> None:
    _cache.pop(user_id, None)


async def init_db(dsn: str) -> None:
    global pool
    # statement_cache_size=0 keeps this compatible with Supabase's pooled connection string
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, statement_cache_size=0)
    async with pool.acquire() as con:
        await con.execute(SCHEMA)


async def close_db() -> None:
    if pool:
        await pool.close()


async def get_or_create_user(user_id: int, referrer: int | None = None) -> asyncpg.Record:
    """Create the user on first contact. `referrer` is stored only when the row is
    brand new, so existing users can never be 'referred' later. The returned record
    has an extra `is_new` field."""
    async with pool.acquire() as con:
        rec = await con.fetchrow(
            """
            INSERT INTO users (id, referred_by) VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET last_seen = now()
            RETURNING *, (xmax = 0) AS is_new
            """,
            user_id,
            referrer,
        )
    invalidate(user_id)
    return rec


async def get_user(user_id: int) -> asyncpg.Record | None:
    """Cached read. Returns None if the user never ran /start."""
    now = time.monotonic()
    hit = _cache.get(user_id)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    async with pool.acquire() as con:
        rec = await con.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    if len(_cache) > _CACHE_MAX:
        _cache.clear()
    _cache[user_id] = (now, rec)
    return rec


def is_premium(user) -> bool:
    until = user["premium_until"]
    return bool(until and until > datetime.now(timezone.utc))


async def set_field(user_id: int, field: str, value: str) -> None:
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Field not editable: {field}")
    async with pool.acquire() as con:
        await con.execute(f"UPDATE users SET {field} = $1 WHERE id = $2", value, user_id)
    invalidate(user_id)


async def add_report(reporter_id: int, reported_id: int, reason: str) -> None:
    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO reports (reporter_id, reported_id, reason) VALUES ($1, $2, $3)",
            reporter_id,
            reported_id,
            reason,
        )


async def _extend_vip(con, user_id: int, days: int) -> datetime:
    """Add VIP days on top of any remaining time. Call inside a transaction."""
    return await con.fetchval(
        """
        UPDATE users
        SET premium_until = GREATEST(COALESCE(premium_until, now()), now())
                            + make_interval(days => $2)
        WHERE id = $1
        RETURNING premium_until
        """,
        user_id,
        days,
    )


async def credit_referral(
    new_user_id: int, target: int, reward_days: int, repeat: bool
) -> dict | None:
    """Called once when a referred user finishes setup. Counts them for their referrer
    and grants VIP if a milestone was reached. Returns None if nothing to credit, else
    {"referrer": id, "count": n, "rewarded_days": d, "until": datetime | None}."""
    async with pool.acquire() as con:
        async with con.transaction():
            # Atomic "claim": only the first call for this user gets a row back
            referrer = await con.fetchval(
                """
                UPDATE users SET referral_credited = TRUE
                WHERE id = $1 AND referred_by IS NOT NULL AND NOT referral_credited
                RETURNING referred_by
                """,
                new_user_id,
            )
            if referrer is None:
                return None
            # Lock the referrer row so two friends finishing at once can't double-reward
            ref = await con.fetchrow(
                "SELECT banned, referral_rewards FROM users WHERE id = $1 FOR UPDATE", referrer
            )
            if ref is None or ref["banned"]:
                return None
            count = await con.fetchval(
                "SELECT count(*) FROM users WHERE referred_by = $1 AND referral_credited", referrer
            )
            earned = count // target
            if not repeat:
                earned = min(earned, 1)
            due = earned - ref["referral_rewards"]
            days, until = 0, None
            if due > 0:
                days = due * reward_days
                until = await _extend_vip(con, referrer, days)
                await con.execute(
                    "UPDATE users SET referral_rewards = $2 WHERE id = $1", referrer, earned
                )
    invalidate(referrer)
    return {"referrer": referrer, "count": count, "rewarded_days": days, "until": until}


async def referral_count(user_id: int) -> int:
    async with pool.acquire() as con:
        return await con.fetchval(
            "SELECT count(*) FROM users WHERE referred_by = $1 AND referral_credited", user_id
        )


async def stats() -> dict:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT count(*) AS users,
                   count(*) FILTER (WHERE premium_until > now()) AS vip,
                   count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS new_24h,
                   count(*) FILTER (WHERE referral_credited) AS referred
            FROM users
            """
        )
    return dict(row)


# ---------------------------------------------------------------- admin

async def user_card(user_id: int) -> dict | None:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT u.*,
              (SELECT count(*) FROM reports r WHERE r.reported_id = u.id) AS reports_against,
              (SELECT count(*) FROM reports r WHERE r.reporter_id = u.id) AS reports_made,
              (SELECT count(*) FROM users x WHERE x.referred_by = u.id AND x.referral_credited) AS invited,
              (SELECT COALESCE(sum(stars), 0) FROM payments p WHERE p.user_id = u.id AND NOT p.refunded) AS stars_spent
            FROM users u WHERE u.id = $1
            """,
            user_id,
        )
    return dict(row) if row else None


async def set_banned(user_id: int, banned: bool) -> bool:
    async with pool.acquire() as con:
        ok = await con.fetchval(
            "UPDATE users SET banned = $2 WHERE id = $1 RETURNING TRUE", user_id, banned
        )
        if ok and banned:
            await con.execute(
                "UPDATE reports SET status = 'actioned' WHERE reported_id = $1 AND status = 'open'",
                user_id,
            )
    invalidate(user_id)
    return bool(ok)


async def grant_vip(user_id: int, days: int) -> datetime | None:
    async with pool.acquire() as con:
        async with con.transaction():
            until = await _extend_vip(con, user_id, days)
    invalidate(user_id)
    return until


async def remove_vip(user_id: int) -> bool:
    async with pool.acquire() as con:
        ok = await con.fetchval(
            "UPDATE users SET premium_until = NULL WHERE id = $1 RETURNING TRUE", user_id
        )
    invalidate(user_id)
    return bool(ok)


async def next_open_report(after_id: int = 0) -> dict | None:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT r.*,
              (SELECT count(*) FROM reports x WHERE x.reported_id = r.reported_id) AS reports_against
            FROM reports r
            WHERE r.status = 'open' AND r.id > $1
            ORDER BY r.id LIMIT 1
            """,
            after_id,
        )
    return dict(row) if row else None


async def open_report_count() -> int:
    async with pool.acquire() as con:
        return await con.fetchval("SELECT count(*) FROM reports WHERE status = 'open'")


async def set_report_status(report_id: int, status: str) -> None:
    async with pool.acquire() as con:
        await con.execute("UPDATE reports SET status = $2 WHERE id = $1", report_id, status)


async def broadcast_ids() -> list[int]:
    """Everyone who finished setup and isn't banned."""
    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT id FROM users
            WHERE NOT banned AND gender IS NOT NULL AND age_bracket IS NOT NULL AND region IS NOT NULL
            """
        )
    return [r["id"] for r in rows]


async def apply_payment(
    user_id: int, plan_id: str, days: int, stars: int, charge_id: str
) -> datetime | None:
    """Record a Stars payment and extend premium. Returns the new expiry,
    or None if this payment was already processed (duplicate delivery)."""
    async with pool.acquire() as con:
        async with con.transaction():
            inserted = await con.fetchval(
                """
                INSERT INTO payments (user_id, plan, stars, telegram_charge_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (telegram_charge_id) DO NOTHING
                RETURNING id
                """,
                user_id,
                plan_id,
                stars,
                charge_id,
            )
            if inserted is None:
                return None
            until = await _extend_vip(con, user_id, days)
    invalidate(user_id)
    return until


# ---------------------------------------------------------------- AI chat stats

async def log_ai_chat(user_id: int, seconds: int, msgs: int) -> None:
    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO ai_chats (user_id, seconds, msgs) VALUES ($1, $2, $3)",
            user_id, seconds, msgs,
        )


async def ai_chat_stats() -> dict:
    """Only chats where the user actually sent something (msgs > 0) count as 'chats'."""
    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT count(*) FILTER (WHERE msgs > 0) AS chats,
                   count(*) FILTER (WHERE msgs > 0 AND created_at > now() - interval '24 hours') AS chats_24h,
                   count(DISTINCT user_id) FILTER (WHERE msgs > 0) AS users,
                   count(DISTINCT user_id) FILTER (WHERE msgs > 0 AND created_at > now() - interval '24 hours') AS users_24h,
                   COALESCE(avg(seconds) FILTER (WHERE msgs > 0), 0) AS avg_sec,
                   COALESCE(avg(msgs) FILTER (WHERE msgs > 0), 0) AS avg_msgs
            FROM ai_chats
            """
        )
    d = dict(row)
    d["avg_sec"], d["avg_msgs"] = float(d["avg_sec"]), float(d["avg_msgs"])
    return d


# ---------------------------------------------------------------- live state (survives redeploys)

async def load_state() -> tuple[str, float] | None:
    async with pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT data, EXTRACT(EPOCH FROM now() - updated_at)::float8 AS age FROM bot_state WHERE key = 'main'"
        )
    return (row["data"], row["age"]) if row else None


async def save_state(boot_id: str, data: str, takeover: bool = False) -> bool:
    async with pool.acquire() as con:
        if takeover:
            await con.execute(
                """
                INSERT INTO bot_state (key, boot_id, data) VALUES ('main', $1, $2)
                ON CONFLICT (key) DO UPDATE SET boot_id = $1, data = $2, updated_at = now()
                """,
                boot_id, data,
            )
            return True
        return bool(await con.fetchval(
            "UPDATE bot_state SET data = $2, updated_at = now() WHERE key = 'main' AND boot_id = $1 RETURNING TRUE",
            boot_id, data,
        ))
