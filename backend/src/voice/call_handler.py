"""CallHandler — the real-time renewal-call orchestrator.

Transport-agnostic: audio comes in via ``on_audio_in(pcm16)`` and goes out via
the injected ``send_audio(mulaw_bytes)`` callback; conversation/order events are
pushed via ``emit_event(dict)`` (consumed by the frontend live WS). The Twilio
media-stream handler (Phase 6) wires this to a real call.

Loop: STT final transcript → Sarvam-105B stream (tools) → tool exec against
Postgres → sentence-buffered Bulbul TTS → outbound μ-law. Server-VAD
START_SPEECH triggers barge-in (cancel generation, tell transport to flush).
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.domain import models as m
from src.tools.order_tools import TOOL_HANDLERS, ToolContext
from src.tools.tool_specs import ORDER_TOOLS
from src.voice.llm.dialogue_client import DialogueLLMClient
from src.voice.metrics import SessionMetrics
from src.voice.stt.sarvam_client import SarvamSTTClient
from src.voice.tts.sarvam_client import SarvamBulbulTTSClient
from src.voice.tts.sentence_buffer import SentenceBuffer

logger = get_logger(__name__)

MAX_TOOL_HOPS = 6
_TTS_STOP = object()  # sentinel: no more sentences to speak this turn

# After a FINAL transcript, wait this long for another before generating. Sarvam's VAD
# chops halting speech into many short finals ("enakku" / "Colgate Strong" / "100 gram");
# without coalescing, each one cancels the in-flight turn (barge-in storm) so the agent
# never finishes a reply AND only ever sees disconnected scraps it can't act on. A brief
# debounce merges the fragments into one coherent turn. Tune down for snappier turns.
_ENDPOINT_DEBOUNCE_S = 0.6

GREETING_NUDGE = (
    "Begin the call now: greet the retailer warmly by name in their language, "
    "then confirm this week's usual order."
)


class CallHandler:
    def __init__(
        self,
        *,
        db: AsyncSession,
        outlet: m.Outlet,
        system_prompt: str,
        send_audio: Callable[[bytes], Awaitable[None]],
        emit_event: Callable[[dict], Awaitable[None]],
        default_language: Optional[str] = None,
        stt=None,
        tts=None,
        llm=None,
    ) -> None:
        self.db = db
        self.outlet = outlet
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]
        self._send_audio = send_audio
        self._emit = emit_event
        # STT stays on auto-detect ("unknown") so the agent can open in the outlet's
        # default language and follow the caller into whatever language they actually
        # speak. The STT is messy on short 8 kHz turns, but that was always true — a
        # reasoning-capable LLM rides through it (see call #9); the real fix is the LLM.
        self.stt = stt or SarvamSTTClient()
        self.tts = tts or SarvamBulbulTTSClient()
        self.llm = llm or DialogueLLMClient()
        self.ctx = ToolContext(db=db, outlet=outlet)
        self.language = default_language or outlet.language or "hi-IN"
        self.transcript: list[dict] = []
        self.ended = False
        self.metrics = SessionMetrics()
        self._gen_task: Optional[asyncio.Task] = None
        self._tts_task: Optional[asyncio.Task] = None
        self._debounce_task: Optional[asyncio.Task] = None
        self._generating = False
        self._t_user_final = 0.0
        self._await_first_audio = False

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self.stt.on_transcript(self._on_transcript)
        self.stt.on_speech_started(self._on_speech_started)
        await self.stt.connect()
        await self._generate(greeting=True)

    async def on_audio_in(self, pcm16: bytes) -> None:
        await self.stt.send_audio(pcm16)

    async def finalize(self) -> dict:
        outcome = "ordered" if self.ctx.order_id else ("declined" if self.transcript else "no_answer")
        self.metrics.stt_seconds = getattr(self.stt, "audio_seconds_sent", 0.0)
        self.metrics.tts_chars = getattr(self.tts, "characters_synthesized", 0)
        return {
            "outcome": outcome,
            "order_id": self.ctx.order_id,
            "transcript": self.transcript,
            "language": self.language,
            "metrics": self.metrics.summary(),
        }

    async def close(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
        try:
            await self.stt.disconnect()
        except Exception:
            pass
        try:
            await self.tts.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ STT cbs
    async def _on_speech_started(self) -> None:
        if self._generating:
            await self._barge_in()

    async def _on_transcript(self, text: str, is_final: bool, language: Optional[str]) -> None:
        if language:
            self.language = language
        if not is_final:
            await self._emit({"type": "partial_transcript", "text": text})
            return
        if not text.strip():
            return
        self.transcript.append({"role": "user", "text": text})
        await self._emit({"type": "user_transcript", "text": text})
        self.messages.append({"role": "user", "content": text})
        self._t_user_final = time.monotonic()
        self._await_first_audio = True
        # Don't generate yet — (re)arm a short debounce. Each further fragment that
        # lands within the window resets it and is appended above, so a burst of finals
        # coalesces into ONE turn. Generation (and any supersede-in-flight barge-in) is
        # deferred to _debounced_generate once the caller actually pauses.
        self._arm_generation()

    def _arm_generation(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._debounced_generate())

    async def _debounced_generate(self) -> None:
        try:
            await asyncio.sleep(_ENDPOINT_DEBOUNCE_S)
        except asyncio.CancelledError:
            return
        # The caller has paused. If a turn is still in flight (they talked over a
        # reply that had already started), supersede it with the coalesced input.
        if self._gen_task and not self._gen_task.done():
            await self._barge_in()
        self._start_generation()

    # ---------------------------------------------------------------- barge-in
    async def _barge_in(self) -> None:
        # Flush Twilio's playback buffer FIRST so the agent stops talking
        # immediately; only then tear down generation. We do NOT await the
        # cancelled tasks here — awaiting would stall the STT read loop (which
        # drives this callback) while in-flight LLM/TTS requests wind down.
        await self._emit({"type": "barge_in"})
        self._await_first_audio = False  # interrupted turn must not log a latency sample
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
        self._gen_task = None  # let _start_generation spin up the next turn cleanly
        self._generating = False

    # -------------------------------------------------------------- generation
    def _start_generation(self) -> None:
        if self._gen_task and not self._gen_task.done():
            return
        self._gen_task = asyncio.create_task(self._generate())

    async def _generate(self, greeting: bool = False) -> None:
        self._generating = True
        # The greeting nudge is a ONE-SHOT kickoff, not a standing instruction: it's
        # removed in the finally below once the greeting turn is done. Left in the
        # message list it re-fires a full greeting on every later turn — harmless when
        # the model reasons ("I already greeted"), but with reasoning off (the latency
        # fix) the model follows it literally and re-greets forever instead of advancing.
        nudge: Optional[dict] = None
        if greeting:
            nudge = {"role": "system", "content": GREETING_NUDGE}
            self.messages.append(nudge)
        # One ordered TTS pipeline for the whole turn: the LLM keeps streaming and
        # segmenting while a single consumer synthesises + sends audio in FIFO
        # order, so sentence N is spoken while sentence N+1 is still generating.
        tts_queue: asyncio.Queue = asyncio.Queue()
        consumer = asyncio.create_task(self._tts_consumer(tts_queue))
        self._tts_task = consumer

        async def speak(text: str) -> None:
            await tts_queue.put(text)

        try:
            for hop in range(MAX_TOOL_HOPS):
                text_parts: list[str] = []
                pending: list[tuple[str, dict, str]] = []
                buffer = SentenceBuffer(speak)

                async def on_token(t: str) -> None:
                    text_parts.append(t)
                    await buffer.add_token(t)

                async def on_tool(name: str, args: dict, tcid: str) -> None:
                    pending.append((name, args, tcid or f"call_{len(pending)}"))

                async def on_done(_: str) -> None:
                    return None

                # The greeting is a fixed opener — no tool should fire, and
                # withholding tools spares the model any tool deliberation.
                tools = None if (greeting and hop == 0) else ORDER_TOOLS
                await self.llm.stream(self.messages, tools, on_token, on_tool, on_done)
                await buffer.flush()

                text = "".join(text_parts).strip()
                assistant_msg: dict = {"role": "assistant", "content": text}
                if pending:
                    assistant_msg["tool_calls"] = [
                        {"id": tcid, "type": "function",
                         "function": {"name": name, "arguments": json.dumps(args)}}
                        for (name, args, tcid) in pending
                    ]
                self.messages.append(assistant_msg)

                if text:
                    self.transcript.append({"role": "agent", "text": text})
                    await self._emit({"type": "agent_text", "text": text})

                if not pending:
                    break

                for (name, args, tcid) in pending:
                    result = await self._exec_tool(name, args)
                    self.messages.append(
                        {"role": "tool", "tool_call_id": tcid, "content": json.dumps(result)}
                    )
                    await self._emit({"type": "tool", "name": name, "result": result})
                    if name == "place_order" and result.get("order_id"):
                        await self._emit({"type": "order_placed", "order": result})
                    if name == "end_call":
                        self.ended = True
                if self.ended:
                    break
            # All text generated — drain the pipeline so every queued sentence
            # is spoken before the turn is considered complete.
            await tts_queue.put(_TTS_STOP)
            await consumer
        except asyncio.CancelledError:
            consumer.cancel()
        except Exception as exc:  # keep the call alive on a generation error
            logger.error("generation error: %s", exc)
            consumer.cancel()
        finally:
            if nudge is not None:
                try:
                    self.messages.remove(nudge)  # one-shot: never let it drive a later turn
                except ValueError:
                    pass
            if not consumer.done():
                consumer.cancel()
            if self._tts_task is consumer:
                self._tts_task = None
            self._generating = False

        if self.ended:
            await self._emit({"type": "call_end"})

    async def _tts_consumer(self, queue: asyncio.Queue) -> None:
        """Speak queued sentences in FIFO order until the STOP sentinel.

        Runs concurrently with LLM streaming so synthesis of one sentence
        overlaps generation of the next and playback of the previous.
        """
        while True:
            item = await queue.get()
            try:
                if item is _TTS_STOP:
                    return
                await self._speak(item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("tts speak failed: %s", exc)
            finally:
                queue.task_done()

    async def _speak(self, sentence: str) -> None:
        audio = await self.tts.synthesize(sentence, self.language)
        if not audio:
            return
        if self._await_first_audio and self._t_user_final:
            self.metrics.record_response(int((time.monotonic() - self._t_user_final) * 1000))
            self._await_first_audio = False
        await self._send_audio(audio)

    async def _exec_tool(self, name: str, args: dict) -> dict:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return {"error": f"unknown tool {name}"}
        try:
            return await handler(self.ctx, args)
        except Exception as exc:
            logger.warning("tool %s failed: %s", name, exc)
            return {"error": str(exc)}
