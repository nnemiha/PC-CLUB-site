import os
import asyncpg

async def connect():
    pool = await asyncpg.create_pool(
        host="db", user="marinovani", database="marinovani",
        password=os.environ["POSTGRES_PASSWORD"], min_size=1, max_size=4,
    )
    async with pool.acquire() as c:
        # Serialize initialization when bot and API start together.
        async with c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(8100)")
            await c.execute('''
                CREATE TABLE IF NOT EXISTS zones (
                    code TEXT PRIMARY KEY, title TEXT NOT NULL, price INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS drafts (
                    user_id BIGINT PRIMARY KEY, step TEXT NOT NULL, data JSONB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookings (
                    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL,
                    username TEXT, zone TEXT NOT NULL REFERENCES zones(code),
                    customer_name TEXT NOT NULL, starts_at TIMESTAMPTZ NOT NULL,
                    hours INTEGER NOT NULL CHECK(hours BETWEEN 1 AND 12),
                    contact TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    notified BOOLEAN NOT NULL DEFAULT FALSE
                );
            ''')
            await c.executemany('''INSERT INTO zones VALUES ($1,$2,$3)
                ON CONFLICT (code) DO NOTHING''', [
                ("standard_pc", "Стандарт PC", 120),
                ("vip_pc", "VIP PC", 200),
                ("ps5", "PS5 — зал до 4 человек", 250),
                ("vip_ps5_shower", "VIP PS5 + душ", 450),
            ])
    return pool
