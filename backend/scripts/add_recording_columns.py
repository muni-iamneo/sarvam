"""Idempotent, non-destructive migration: add the recording_* columns to
call_logs (Postgres). Lets an already-running DB pick up the recording feature
WITHOUT a full reseed that would wipe call history.

Run: backend/.venv/bin/python -m scripts.add_recording_columns
"""

import asyncio

from sqlalchemy import text

from src.domain.db import engine

DDL = [
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_sid VARCHAR(64)",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_url TEXT",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_duration_s INTEGER",
    "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_status VARCHAR(20)",
]


async def main() -> None:
    async with engine.begin() as conn:
        for stmt in DDL:
            await conn.execute(text(stmt))
            print("ok:", stmt)
        cols = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='call_logs' AND column_name LIKE 'recording%' "
                    "ORDER BY column_name"
                )
            )
        ).scalars().all()
        print("recording columns now present:", cols)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
