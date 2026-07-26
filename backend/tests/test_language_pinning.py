"""The call language is PINNED at start and never follows Sarvam's per-utterance
auto-detect — regression for the bug where a Kannada store's call was hijacked
into Odia by a single 8 kHz mis-detection. Also covers the new prompt guardrails:
pinned-language wording, first-call catalog listing, and catalog/offer discipline.
"""

import types

from sqlalchemy import select

from src.domain import models as m
from src.domain.db import AsyncSessionLocal
from src.memory.context import build_system_prompt
from src.voice.call_handler import CallHandler


def _handler(default_language):
    async def emit(_e):
        pass

    async def send(_b):
        pass

    outlet = types.SimpleNamespace(id=1, company_id=1, language="hi-IN", name="Test")
    return CallHandler(
        db=None, outlet=outlet, system_prompt="sys",
        send_audio=send, emit_event=emit,
        stt=None, tts=object(), llm=object(),  # real STT so we can check it's pinned
        default_language=default_language,
    )


def test_stt_is_pinned_to_the_chosen_language():
    h = _handler("kn-IN")
    assert h.language == "kn-IN"
    assert h.stt._language == "kn-IN"  # decodes Kannada — NOT 'unknown' auto-detect


async def test_language_never_switches_on_misdetect():
    h = _handler("kn-IN")
    # Sarvam mis-reads a Kannada utterance as Odia — must be IGNORED, not adopted.
    await h._on_transcript("ಹಾಂ", True, "od-IN")
    assert h.language == "kn-IN"
    if h._debounce_task:
        h._debounce_task.cancel()


async def test_prompt_pins_language_and_lists_catalog_on_first_call():
    async with AsyncSessionLocal() as db:
        outlet = (
            await db.execute(select(m.Outlet).where(m.Outlet.code == "OUT0001"))
        ).scalar_one()
        prompt = await build_system_prompt(db, outlet, "Colgate", None, language="kn-IN")
    assert "Speak ONLY in kn-IN" in prompt
    assert "auto-detected" not in prompt
    assert "NO order history" in prompt            # first-call: present the catalog
    assert "SCHEME & CATALOG DISCIPLINE" in prompt   # no invented products/discounts
