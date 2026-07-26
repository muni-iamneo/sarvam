"""The live-call system prompt carries the conversation-polish guardrails:
net-price-only mid-call verbosity, a single itemized read-back, PROACTIVE scheme
discipline (never volunteer an un-fetched scheme), light-touch human warmth, and a
graceful decline when the retailer pushes for a bigger discount. Pure prompt-string
checks — no telephony/STT/TTS/LLM.
"""

from sqlalchemy import select

from src.domain import models as m
from src.memory.context import build_system_prompt


async def _prompt(db, seeded):
    outlet = (
        await db.execute(select(m.Outlet).where(m.Outlet.id == seeded["outlet_id"]))
    ).scalar_one()
    return await build_system_prompt(db, outlet, "Colgate", None, language="ta-IN")


async def test_prompt_speaks_the_net_not_the_math(db, seeded):
    prompt = await _prompt(db, seeded)
    # Dedicated verbosity block: state the net figure, never narrate arithmetic.
    assert "NUMBERS — SPEAK THE NET, NOT THE MATH" in prompt
    # The full breakdown is spoken exactly once, at a REQUIRED final read-back.
    assert "this final read-back is REQUIRED" in prompt
    # The old "read back the itemized total" phrasing is gone (relocated to step 6).
    assert "read back the itemized total" not in prompt


async def test_scheme_discipline_is_proactive(db, seeded):
    prompt = await _prompt(db, seeded)
    # The reactive rule is replaced by a proactive, tool-gated one.
    assert "SCHEME & CATALOG DISCIPLINE" in prompt
    assert "CATALOG & OFFER DISCIPLINE" not in prompt
    assert "AT MOST ONE scheme" in prompt
    # A scheme printed in the prompt is stale reference, not licence to speak it.
    assert "NOT permission to speak it" in prompt


async def test_prompt_has_light_touch_warmth(db, seeded):
    prompt = await _prompt(db, seeded)
    # Open with a genuine human beat before the order.
    assert "how business or their week is going" in prompt


async def test_prompt_declines_extra_discount_gracefully(db, seeded):
    prompt = await _prompt(db, seeded)
    # No hard "no", no invented offer — acknowledge and pass feedback up.
    assert "pass the feedback on to the team" in prompt
