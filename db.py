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
        return await con.fetchrow(
            """
            INSERT INTO users (id) VALUES ($1)
            ON CONFLICT (id) DO UPDATE SET last_seen = now()
            RETURNING *
            """,
            user_id,
        )


async def set_field(user_id: int, field: str, value: str) -> None:
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Field not editable: {field}")
    async with pool.acquire() as con:
        await con.execute(f"UPDATE users SET {field} = $1 WHERE id = $2", value, user_id)
