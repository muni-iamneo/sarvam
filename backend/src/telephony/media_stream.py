"""Twilio Media Streams ⇄ CallHandler bridge + a live-event hub for the console.

Handles the WS protocol (connected/start/media/stop): decodes inbound base64
μ-law → PCM16 → CallHandler; frames CallHandler's μ-law TTS back out as Twilio
``media`` messages; forwards ``barge_in`` as a Twilio ``clear``; and on hangup
finalises the call_log row + writes a Supermemory note.
"""

import json
import time
from datetime import datetime

from sqlalchemy import select

from src.audio.telephony import b64_mulaw_to_pcm16, mulaw_to_twilio_frames
from src.core.config import settings
from src.core.logging import get_logger
from src.domain import models as m
from src.domain.db import AsyncSessionLocal
from src.memory.context import build_system_prompt
from src.memory.extractor import extract_and_store
from src.memory.retailer_memory import RetailerMemoryClient
from src.voice.call_handler import CallHandler
from src.voice.llm.dialogue_client import DialogueLLMClient

logger = get_logger(__name__)


class LiveHub:
    """In-memory pub/sub keyed by call_id (string). Buffers history for replay."""

    def __init__(self) -> None:
        self._subs: dict[str, set] = {}
        self._history: dict[str, list[dict]] = {}

    async def publish(self, call_id: str, event: dict) -> None:
        self._history.setdefault(call_id, []).append(event)
        for ws in list(self._subs.get(call_id, set())):
            try:
                await ws.send_json(event)
            except Exception:
                self._subs.get(call_id, set()).discard(ws)

    def subscribe(self, call_id: str, ws) -> None:
        self._subs.setdefault(call_id, set()).add(ws)

    def unsubscribe(self, call_id: str, ws) -> None:
        self._subs.get(call_id, set()).discard(ws)

    def history(self, call_id: str) -> list[dict]:
        return list(self._history.get(call_id, []))


class _NullLLM:
    async def complete(self, messages, max_tokens: int = 400) -> str:  # offline / no-key path
        return ""


async def _default_handler_factory(
    db, outlet, system_prompt, send_audio, emit,
    *, language=None, push_sku_id=None, push_discount_pct=None,
):
    return CallHandler(
        db=db, outlet=outlet, system_prompt=system_prompt, send_audio=send_audio, emit_event=emit,
        default_language=language, push_sku_id=push_sku_id, push_discount_pct=push_discount_pct,
    )


async def run_media_stream(ws, hub: LiveHub, *, session_factory=AsyncSessionLocal, handler_factory=_default_handler_factory) -> None:
    await ws.accept()
    call_id: str | None = None
    stream_sid: str | None = None
    handler = None
    db = None
    outlet = None
    memory = None
    frames_in = 0  # DIAGNOSTIC: inbound Twilio media frames actually pumped to STT

    async def send_audio(mulaw: bytes) -> None:
        if not stream_sid:
            return
        for frame in mulaw_to_twilio_frames(mulaw):
            await ws.send_text(
                json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": frame}})
            )

    try:
        async for raw in ws.iter_text():
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            event = data.get("event")

            if event == "start":
                start = data.get("start", {})
                stream_sid = start.get("streamSid")
                params = start.get("customParameters") or {}
                call_id = str(params.get("call_id") or stream_sid)
                db = session_factory()
                cl = None
                if str(params.get("call_id") or "").isdigit():
                    cl = (
                        await db.execute(select(m.CallLog).where(m.CallLog.id == int(params["call_id"])))
                    ).scalar_one_or_none()
                if cl:
                    outlet = (
                        await db.execute(select(m.Outlet).where(m.Outlet.id == cl.outlet_id))
                    ).scalar_one_or_none()
                if not outlet:
                    await hub.publish(call_id, {"type": "error", "message": "outlet not found for call"})
                    break

                memory = RetailerMemoryClient()
                profile = await memory.get_profile(outlet.code)
                company = (
                    await db.execute(select(m.Company).where(m.Company.id == outlet.company_id))
                ).scalar_one()
                # Operator-chosen targeting persisted on the call_logs row at dial time.
                push_sku = None
                if cl and cl.push_sku_id:
                    push_sku = (
                        await db.execute(select(m.Sku).where(m.Sku.id == cl.push_sku_id))
                    ).scalar_one_or_none()
                prompt = await build_system_prompt(
                    db, outlet, company.name, profile,
                    language=(cl.initial_language if cl else None),
                    pushed_product=({"name": push_sku.name, "pack": push_sku.pack_size} if push_sku else None),
                    push_discount_pct=(cl.push_discount_pct if cl else None),
                )

                async def emit(evt: dict) -> None:
                    if evt.get("type") == "barge_in" and stream_sid:
                        try:
                            await ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                        except Exception:
                            pass
                    await hub.publish(call_id, evt)

                handler = await handler_factory(
                    db, outlet, prompt, send_audio, emit,
                    language=(cl.initial_language if cl else None),
                    push_sku_id=(cl.push_sku_id if cl else None),
                    push_discount_pct=(cl.push_discount_pct if cl else None),
                )
                await hub.publish(call_id, {"type": "call_started", "outlet": outlet.name})
                # DIAGNOSTIC: the greeting is generated INLINE here, so this await blocks the
                # single media-reading loop for its whole duration — during which NO inbound
                # Twilio audio is read and the Sarvam STT socket is starved. Timing the block
                # shows how long the pump is stalled at call open.
                _t_greet = time.monotonic()
                logger.info("[mediastream] greeting begin — media loop BLOCKED until it returns")
                await handler.start()
                logger.info(
                    "[mediastream] greeting done in %d ms — media pump resuming",
                    int((time.monotonic() - _t_greet) * 1000),
                )

            elif event == "media" and handler:
                payload = (data.get("media") or {}).get("payload")
                if payload:
                    await handler.on_audio_in(b64_mulaw_to_pcm16(payload))
                    # DIAGNOSTIC: confirms the inbound pump is still alive AFTER the first reply.
                    # If these lines stop, no audio is reaching STT → no transcripts → silence.
                    frames_in += 1
                    if frames_in % 250 == 0:  # ~5 s of 8 kHz audio
                        logger.info("[mediastream] inbound frames pumped to STT: %d", frames_in)

            elif event == "stop":
                break
    except Exception as exc:
        # DIAGNOSTIC: if THIS fires shortly after the first reply, the Twilio WS loop itself
        # died (prime suspect: concurrent ws.send_text from the TTS task + a barge-in 'clear'),
        # which stops the inbound pump and silences the agent. Full traceback to disambiguate.
        logger.exception("media stream loop CRASHED — inbound audio pump stopped: %s", exc)
    finally:
        if handler and outlet is not None and db is not None:
            await _finalize(hub, call_id, handler, outlet, memory, db)


async def _finalize(hub, call_id, handler, outlet, memory, db) -> None:
    try:
        result = await handler.finalize()
        cl = (
            await db.execute(select(m.CallLog).where(m.CallLog.id == int(call_id)))
        ).scalar_one_or_none() if str(call_id).isdigit() else None

        ext_llm = DialogueLLMClient() if settings.sarvam_api_key else _NullLLM()
        note = await extract_and_store(
            llm=ext_llm,
            memory=memory or RetailerMemoryClient(),
            outlet_name=outlet.name,
            outlet_code=outlet.code,
            transcript=result["transcript"],
            order_result={"order_id": result.get("order_id")},
        )
        if cl:
            cl.ended_at = datetime.now()
            cl.outcome = result["outcome"]
            cl.order_id = result.get("order_id")
            cl.transcript = json.dumps(result["transcript"])
            cl.language_detected = result.get("language")
            cl.latency_p50_ms = (result.get("metrics") or {}).get("p50_response_ms")
            cl.summary = note
            await db.commit()
        await hub.publish(
            call_id,
            {"type": "call_finalized", "outcome": result["outcome"],
             "order_id": result.get("order_id"), "summary": note, "metrics": result.get("metrics")},
        )
    except Exception as exc:
        logger.warning("finalize failed: %s", exc)
    finally:
        try:
            await handler.close()
        except Exception:
            pass
        if memory:
            await memory.close()
        try:
            await db.close()
        except Exception:
            pass
