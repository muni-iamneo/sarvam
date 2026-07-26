"""Idempotent, non-destructive migration: add per-call targeting columns
(starting language + pushed product/discount) to call_logs and call_schedules
(Postgres). Lets an already-running DB pick up the targeting feature WITHOUT a
full reseed that would wipe call history.

Run: backend/.venv/bin/python -m scripts.add_call_targeting_columns
"""

import asyncio

from sqlalchemy import text

from src.domain.db import engine

DDL = [
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS initial_language VARCHAR(10)",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS push_sku_id INTEGER",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS push_discount_pct DOUBLE PRECISION",
    "ALTER TABLE call_schedules ADD COLUMN IF NOT EXISTS language VARCHAR(10)",
    "ALTER TABLE call_schedules ADD COLUMN IF NOT EXISTS push_sku_id INTEGER",
    "ALTER TABLE call_schedules ADD COLUMN IF NOT EXISTS push_discount_pct DOUBLE PRECISION",
]


async def main() -> None:
    async with engine.begin() as conn:
        for stmt in DDL:
            await conn.execute(text(stmt))
            print("ok:", stmt)
        for table in ("call_logs", "call_schedules"):
            cols = (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name=:t AND column_name IN "
                        "('initial_language','push_sku_id','push_discount_pct','language') "
                        "ORDER BY column_name"
                    ),
                    {"t": table},
                )
            ).scalars().all()
            print(f"{table} targeting columns now present:", cols)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
