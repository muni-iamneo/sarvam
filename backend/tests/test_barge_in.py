"""Barge-in gating: START_SPEECH must interrupt the agent only while it is
audibly SPEAKING — never during the LLM 'think' phase, where a hypersensitive
VAD blip (the caller's trailing word / breath) would otherwise kill the reply
before it is ever spoken.
"""

import types

from src.voice.call_handler import CallHandler


def _handler():
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    async def send(_b: bytes) -> None:
        pass

    outlet = types.SimpleNamespace(id=1, company_id=1, language="hi-IN")
    h = CallHandler(
        db=None, outlet=outlet, system_prompt="sys",
        send_audio=send, emit_event=emit,
        stt=object(), tts=object(), llm=object(),
    )
    return h, events


async def test_no_barge_in_during_think_phase():
    # Agent is generating (LLM streaming) but has not emitted audio yet.
    h, events = _handler()
    h._generating = True
    h._speaking = False
    await h._on_speech_started()
    assert not any(e["type"] == "barge_in" for e in events)


async def test_barge_in_while_agent_is_speaking():
    # Audio is going out — a real interruption; must barge.
    h, events = _handler()
    h._generating = True
    h._speaking = True
    await h._on_speech_started()
    assert any(e["type"] == "barge_in" for e in events)


async def test_no_barge_in_when_idle():
    h, events = _handler()
    h._generating = False
    h._speaking = False
    await h._on_speech_started()
    assert not any(e["type"] == "barge_in" for e in events)
