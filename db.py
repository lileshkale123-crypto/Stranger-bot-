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


async def get_or_create_user(user_id: int) -> asyncpg.Record:
    async with pool.acquire() as con:
        rec = await con.fetchrow(
            """
            INSERT INTO users (id) VALUES ($1)
            ON CONFLICT (id) DO UPDATE SET last_seen = now()
            RETURNING *
            """,
            user_id,
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
            # Extend from the current expiry if still active, otherwise from now
            until = await con.fetchval(
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
    invalidate(user_id)
    return until
