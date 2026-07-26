"""CallHandler + media_stream carry the per-call targeting into the live loop."""

from sqlalchemy import select

from src.domain import models as m
from src.telephony.media_stream import _default_handler_factory
from src.voice.call_handler import CallHandler


async def _noop_send(_: bytes) -> None:
    return None


async def _noop_emit(_: dict) -> None:
    return None


async def _outlet(db, seeded):
    return (await db.execute(select(m.Outlet).where(m.Outlet.id == seeded["outlet_id"]))).scalar_one()


async def test_callhandler_stores_targeting(db, seeded):
    outlet = await _outlet(db, seeded)
    h = CallHandler(
        db=db, outlet=outlet, system_prompt="sys",
        send_audio=_noop_send, emit_event=_noop_emit,
        default_language="ta-IN", push_sku_id=seeded["sku_a"], push_discount_pct=15.0,
    )
    assert h.language == "ta-IN"
    assert h.ctx.push_sku_id == seeded["sku_a"]
    assert h.ctx.push_discount_pct == 15.0


async def test_default_handler_factory_passes_targeting(db, seeded):
    outlet = await _outlet(db, seeded)
    h = await _default_handler_factory(
        db, outlet, "sys", _noop_send, _noop_emit,
        language="kn-IN", push_sku_id=seeded["sku_b"], push_discount_pct=20.0,
    )
    assert h.language == "kn-IN"
    assert h.ctx.push_sku_id == seeded["sku_b"]
    assert h.ctx.push_discount_pct == 20.0
