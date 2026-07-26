"""build_system_prompt injects a PRIORITY PUSH block + honors the chosen language."""

from sqlalchemy import select

from src.domain import models as m
from src.memory.context import build_system_prompt


async def _outlet(db, seeded):
    return (await db.execute(select(m.Outlet).where(m.Outlet.id == seeded["outlet_id"]))).scalar_one()


async def test_prompt_includes_push_block(db, seeded):
    outlet = await _outlet(db, seeded)
    prompt = await build_system_prompt(
        db, outlet, "Colgate", None,
        language="ta-IN",
        pushed_product={"name": "Surf Excel", "pack": "48-case"},
        push_discount_pct=15.0,
    )
    assert "PRIORITY PUSH" in prompt
    assert "Surf Excel" in prompt
    assert "15%" in prompt


async def test_prompt_omits_push_block_when_not_set(db, seeded):
    outlet = await _outlet(db, seeded)
    prompt = await build_system_prompt(db, outlet, "Colgate", None, language="ta-IN")
    assert "PRIORITY PUSH" not in prompt
