"""Runtime smoke for the latency changes (stands in for the missing test suite).

Checks: (1) all changed modules import; (2) SentenceBuffer flushes the opening
clause early then whole sentences; (3) CallHandler's TTS pipeline speaks every
sentence in FIFO order on a normal turn; (4) barge-in stops generation cleanly.

Run: backend/.venv/bin/python -m scripts.smoke_latency
"""

import asyncio

# (1) imports
from src.api import calls as _calls  # noqa: F401
from src.domain import models as _models, repository as _repo, schemas as _schemas  # noqa: F401
from src.telephony import twilio_client as _tw  # noqa: F401
from src.voice.call_handler import CallHandler
from src.voice.tts.sentence_buffer import SentenceBuffer

failures = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)


async def test_sentence_buffer():
    chunks = []
    buf = SentenceBuffer(lambda t: chunks.append(t) or asyncio.sleep(0), first_chunk_max_chars=64)
    # tokens with an early clause then a full sentence
    for tok in ["Namaste ", "Ramesh ", "ji, ", "aap ka is hafte ka usual order theek hai? ", "Dhanyavaad."]:
        await buf.add_token(tok)
    await buf.flush()
    check("early-clause first chunk", chunks and chunks[0] == "Namaste Ramesh ji,")
    check("later chunk is full sentence", any("theek hai?" in c for c in chunks))
    check("no text dropped", "Dhanyavaad." in " ".join(chunks))


class FakeSTT:
    audio_seconds_sent = 0.0
    def on_transcript(self, cb): self._t = cb
    def on_speech_started(self, cb): self._s = cb
    async def connect(self): pass
    async def disconnect(self): pass
    async def send_audio(self, pcm): pass


class FakeTTS:
    characters_synthesized = 0
    def __init__(self): self.spoken = []
    async def synthesize(self, text, lang):
        self.spoken.append(text)
        await asyncio.sleep(0.01)
        return b"\xff" * 160
    async def close(self): pass


class FakeLLM:
    """Streams a scripted reply token-by-token, no tools."""
    def __init__(self, text, delay=0.0):
        self.text = text
        self.delay = delay
    async def stream(self, messages, tools, on_token, on_tool, on_complete):
        for ch in self.text:
            if self.delay:
                await asyncio.sleep(self.delay)
            await on_token(ch)
        await on_complete(self.text)


class FakeOutlet:
    id = 1
    code = "OUT0001"
    name = "Sri Lakshmi Stores"
    language = "kn-IN"
    company_id = 1


def make_handler(llm, tts):
    async def noop_emit(evt): pass
    async def noop_send(audio): pass
    return CallHandler(
        db=None, outlet=FakeOutlet(), system_prompt="sys",
        send_audio=noop_send, emit_event=noop_emit,
        stt=FakeSTT(), tts=tts, llm=llm,
    )


async def test_pipeline_order():
    tts = FakeTTS()
    h = make_handler(FakeLLM("First sentence here. Second one follows. Third and last."), tts)
    await h._generate()
    joined = " ".join(tts.spoken)
    check("all three sentences spoken", tts.spoken and "First" in joined and "Second" in joined and "Third" in joined)
    # FIFO: 'First' spoken before 'Second' before 'Third'
    idx = [next((i for i, s in enumerate(tts.spoken) if w in s), -1) for w in ("First", "Second", "Third")]
    check("spoken in FIFO order", idx == sorted(idx) and -1 not in idx)


async def test_barge_in():
    tts = FakeTTS()
    # slow LLM so we can interrupt mid-generation
    h = make_handler(FakeLLM("A long reply. " * 20, delay=0.02), tts)
    h._start_generation()
    await asyncio.sleep(0.05)
    await h._barge_in()
    await asyncio.sleep(0.1)
    check("gen task cleared after barge-in", h._gen_task is None)
    check("not generating after barge-in", h._generating is False)


async def test_overlap_supersedes():
    # Two FINAL transcripts arrive back-to-back with no barge-in between them
    # (second VAD segment). The second must supersede the first, not be dropped.
    tts = FakeTTS()
    h = make_handler(FakeLLM("Reply one. ", delay=0.02), tts)
    await h._on_transcript("ten cases", True, "hi-IN")   # spawns gen 1
    await h._on_transcript("of Surf Excel", True, "hi-IN")  # must barge-in + respawn
    if h._gen_task:
        await h._gen_task
    users = [m for m in h.messages if m.get("role") == "user"]
    check("both user segments kept", len(users) == 2)
    check("superseding turn produced speech", len(tts.spoken) >= 1)
    check("metric not poisoned (<=1 sample)", len(h.metrics.response_latencies_ms) <= 1)


async def test_greeting_nudge_one_shot():
    # The greeting nudge must kick off ONLY the first turn. If it lingers in the
    # message list it re-fires a full greeting every turn (the "agent keeps
    # re-greeting, never advances" regression) — worse once reasoning is off.
    from src.voice.call_handler import GREETING_NUDGE
    tts = FakeTTS()

    class RecordingLLM(FakeLLM):
        def __init__(self):
            super().__init__("Vanakkam! Usual order confirm panra?")
            self.saw_nudge = []

        async def stream(self, messages, tools, on_token, on_tool, on_complete):
            self.saw_nudge.append(any(m.get("content") == GREETING_NUDGE for m in messages))
            await super().stream(messages, tools, on_token, on_tool, on_complete)

    llm = RecordingLLM()
    h = make_handler(llm, tts)
    await h._generate(greeting=True)          # turn 0 (greeting)
    h.messages.append({"role": "user", "content": "Okay"})
    await h._generate()                        # turn 1 (reply)
    check("greeting turn sees the nudge", llm.saw_nudge[0] is True)
    check("later turn does NOT see the nudge", llm.saw_nudge[1] is False)
    check("nudge removed from messages", not any(m.get("content") == GREETING_NUDGE for m in h.messages))
    check("greeting kept in history", any(m.get("role") == "assistant" for m in h.messages))


async def test_order_tools_arg_validation():
    from src.tools.order_tools import add_line_item, remove_line_item
    from src.tools.order_tools import ToolContext
    ctx = ToolContext(db=None, outlet=FakeOutlet())
    r1 = await add_line_item(ctx, {})            # truncated/empty args
    r2 = await add_line_item(ctx, {"sku_id": "x", "qty": "y"})
    r3 = await remove_line_item(ctx, {})
    check("add_line_item empty args → clean error", isinstance(r1, dict) and "error" in r1)
    check("add_line_item bad ints → clean error", isinstance(r2, dict) and "error" in r2)
    check("remove_line_item empty args → clean error", isinstance(r3, dict) and "error" in r3)


async def main():
    check("modules import", True)
    await test_sentence_buffer()
    await test_pipeline_order()
    await test_barge_in()
    await test_overlap_supersedes()
    await test_greeting_nudge_one_shot()
    await test_order_tools_arg_validation()
    print("\n" + ("ALL SMOKE CHECKS PASSED" if not failures else f"FAILURES: {failures}"))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
