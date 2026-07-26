"""Headless multi-turn conversation sim — compares reasoning ON vs OFF.

Drives the REAL CallHandler (nudge fix, tool loop, language switching) against the
REAL Sarvam LLM + Postgres, with fake STT/TTS. Replays a realistic messy
multilingual ordering sequence (agent opens in the outlet's kn-IN default, caller
answers in Tamil, then orders) and reports, per config:
  - did the agent SWITCH into the caller's language,
  - did it ADVANCE (tool calls) and place an order,
  - how many times it RE-GREETED (repeated its opener), and
  - first-token latency per turn.

Run: backend/.venv/bin/python -m scripts.convo_sim [on|off|both]
"""

import asyncio
import json
import os
import sys
import time

from sqlalchemy import select

from src.core.config import settings
from src.domain.db import AsyncSessionLocal
from src.domain import models as m
from src.memory.context import build_system_prompt
from src.voice.call_handler import CallHandler

# Caller turns mimicking the real (messy, code-switched) STT from calls #9/#18:
# opens in Tamil to test the language switch, then drives a Surf Excel order.
TURNS = [
    ("ஹலோ வணக்கம்", "ta-IN"),                              # Tamil hello (switch test)
    ("எனக்கு சர்ஃப் எக்ஸல் வேணும்", "ta-IN"),               # I want Surf Excel
    ("100 கேஸ் பண்ணுங்க", "ta-IN"),                         # make it 100 cases
    ("ஏதாவது ஆஃபர் இருக்கா?", "ta-IN"),                     # any offer?
    ("சரி, ஆர்டரை கன்ஃபார்ம் பண்ணுங்க", "ta-IN"),           # ok, confirm the order
]


# Prompt variants (appended to the system prompt) to close the reasoning-off gap where
# the model verbally "confirms" without calling place_order. Selected via CONVO_VARIANT.
RULES = {
    "": "",
    "B": (
        "TOOL DISCIPLINE (critical): An order becomes real ONLY by calling the place_order "
        "tool and getting back an order_id. When the retailer agrees (yes / சரி / ठीक / haan / "
        "confirm), your ONLY correct next action is to CALL place_order — never just say in "
        "words that the order is confirmed. Claiming 'order confirmed' without having called "
        "place_order is a critical failure."
    ),
    "C": (
        "ORDER TOOL SEQUENCE (follow every time): (1) add_line_item for each item; (2) "
        "get_order_summary and read the total aloud; (3) the moment the retailer clearly says "
        "yes / சரி / confirm, CALL the place_order tool — do not announce confirmation without "
        "it; (4) then state the delivery day. If they have agreed and you have not yet called "
        "place_order, call it NOW instead of replying."
    ),
}


class FakeSTT:
    audio_seconds_sent = 0.0
    def on_transcript(self, cb): self._t = cb
    def on_speech_started(self, cb): self._s = cb
    async def connect(self): return True
    async def disconnect(self): pass
    async def send_audio(self, pcm): pass


class FakeTTS:
    characters_synthesized = 0
    def __init__(self): self.spoken = []            # (text, language)
    async def synthesize(self, text, lang):
        self.spoken.append((text, lang)); return b"\xff" * 160
    async def close(self): pass


async def run(mode: str):
    settings.sarvam_reasoning_effort = None if mode == "off" else "low"
    # Stub place_order so the sim NEVER commits a test order to the live DB — we only
    # care whether the model *decides* to call it (i.e. advances to the close).
    from src.tools import order_tools
    async def _fake_place_order(ctx, args):
        return {"order_id": 99999, "total_rupees": 135000, "items": [], "note": "sim (not persisted)"}
    order_tools.TOOL_HANDLERS["place_order"] = _fake_place_order

    async with AsyncSessionLocal() as db:
        outlet = (await db.execute(select(m.Outlet).where(m.Outlet.code == "OUT0001"))).scalar_one()
        company = (await db.execute(select(m.Company).where(m.Company.id == outlet.company_id))).scalar_one()
        prompt = await build_system_prompt(db, outlet, company.name, None)
        extra = RULES.get(os.environ.get("CONVO_VARIANT", ""), "")
        if extra:
            prompt += "\n\n" + extra

        events = []
        async def emit(evt): events.append(evt)
        async def send(_): pass
        tts = FakeTTS()
        h = CallHandler(db=db, outlet=outlet, system_prompt=prompt,
                        send_audio=send, emit_event=emit, stt=FakeSTT(), tts=tts)

        t0 = time.monotonic()
        await h.start()                                # greeting
        greet = h.transcript[-1]["text"] if h.transcript else ""
        opener = greet[:40]
        per_turn = [("<greeting>", greet[:70], h.language, round((time.monotonic() - t0) * 1000))]

        for text, lang in TURNS:
            ts = time.monotonic()
            await h._on_transcript(text, True, lang)
            if h._gen_task:
                await h._gen_task
            agent_text = next((t["text"] for t in reversed(h.transcript) if t["role"] == "agent"), "")
            per_turn.append((text[:24], agent_text[:70], h.language, round((time.monotonic() - ts) * 1000)))

        tools = [e.get("name") for e in events if e.get("type") == "tool"]
        order = any(e.get("type") == "order_placed" for e in events)
        agent_texts = [t["text"] for t in h.transcript if t["role"] == "agent"]
        regreets = sum(1 for a in agent_texts[1:] if a[:40] == opener)
        spoke_ta = any(l and l.startswith("ta") for _, l in tts.spoken)

        print(f"\n================ REASONING {mode.upper()} ================")
        for u, a, lang, ms in per_turn:
            print(f"  [{ms:>6}ms] ({lang}) user={u!r}\n            agent={a!r}")
        print(f"  --> tools={tools} order_placed={order} regreets={regreets} agent_spoke_tamil={spoke_ta}")
        result = {"mode": mode, "tools": tools, "order": order, "regreets": regreets,
                  "switched": spoke_ta, "turn_ms": [t[3] for t in per_turn]}
        print("RESULT=" + json.dumps(result))
        return result


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    modes = ["off", "on"] if which == "both" else [which]
    results = [await run(mode) for mode in modes]
    print("\n================ SUMMARY ================")
    for r in results:
        print(f"  reasoning={r['mode']:>3}: order_placed={r['order']} "
              f"tool_calls={len(r['tools'])} regreets={r['regreets']} switched_to_tamil={r['switched']}")


if __name__ == "__main__":
    asyncio.run(main())
