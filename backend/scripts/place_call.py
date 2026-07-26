"""Trigger an outbound BharatBeat renewal call via the running API.

The FastAPI server must be running (uvicorn) and reachable by Twilio (ngrok),
with TWILIO_* + PUBLIC_URL/PUBLIC_WS_HOST set in backend/.env.

Examples:
  python -m scripts.place_call --outlet-code OUT0001
  python -m scripts.place_call --outlet-id 1 --to +91XXXXXXXXXX
"""

import argparse
import asyncio

import httpx
from sqlalchemy import select

from src.domain import models as m
from src.domain.db import AsyncSessionLocal, engine


async def _resolve_outlet_id(code: str) -> int | None:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(m.Outlet.id).where(m.Outlet.code == code))).scalar_one_or_none()
    return row


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outlet-id", type=int)
    ap.add_argument("--outlet-code")
    ap.add_argument("--to", help="Override destination phone (E.164, e.g. +91...)")
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()

    outlet_id = args.outlet_id
    if not outlet_id and args.outlet_code:
        outlet_id = await _resolve_outlet_id(args.outlet_code)
    await engine.dispose()
    if not outlet_id:
        raise SystemExit("Provide --outlet-id or a valid --outlet-code")

    payload = {"outlet_id": outlet_id}
    if args.to:
        payload["to"] = args.to
    async with httpx.AsyncClient(base_url=args.api, timeout=45) as c:
        r = await c.post("/calls", json=payload)
        print(r.status_code, r.json())
        if r.status_code < 300:
            body = r.json()
            print(f"\nWatch live:  {args.api.replace('http', 'ws')}{body['live_ws']}")


if __name__ == "__main__":
    asyncio.run(main())
