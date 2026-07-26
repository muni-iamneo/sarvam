"""Sarvam streaming STT client (Saaras v3 real-time WebSocket).

Endpoint: wss://api.sarvam.ai/speech-to-text/ws
Auth header: ``api-subscription-key``. Accepts 8 kHz PCM (telephony-native),
auto-detects language (``language-code=unknown``), and emits server VAD
signals (START_SPEECH / END_SPEECH) used for barge-in + endpointing.

Wire protocol (confirmed live 2026-07-26 against api.sarvam.ai):
- audio chunk: ``{"audio": {"data": <b64 pcm_s16le>, "sample_rate": "8000",
  "encoding": "audio/wav"}}`` — ``encoding`` is a strict enum whose only accepted
  value is ``audio/wav``; the *actual* codec (raw PCM16) is declared with the
  ``input_audio_codec=pcm_s16le`` query param. Sending ``audio/x-raw`` makes
  Sarvam close the socket with code 1000.
- VAD: ``{"type":"events","data":{"signal_type":"START_SPEECH"|"END_SPEECH"}}``.
- transcript: ``{"type":"data","data":{"transcript":..,"language_code":..}}`` —
  each ``data`` message is a VAD-endpointed utterance, i.e. already FINAL.
"""

import asyncio
import base64
import json
from typing import Optional

import websockets

from src.core.config import settings
from src.core.logging import get_logger
from src.voice.stt.base import BaseSTTClient

logger = get_logger(__name__)


async def _ws_connect(url: str, headers: dict):
    """Connect across websockets versions (additional_headers vs extra_headers)."""
    try:
        return await websockets.connect(url, additional_headers=headers, max_size=None)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers, max_size=None)


class SarvamSTTClient(BaseSTTClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        language: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        sample_rate: Optional[int] = None,
    ) -> None:
        self._api_key = api_key or settings.sarvam_api_key
        self._language = language or settings.sarvam_stt_language
        self._model = model or settings.sarvam_stt_model
        self._mode = mode or settings.sarvam_stt_mode
        self._sample_rate = sample_rate or settings.sarvam_sample_rate
        self._ws = None
        self._listen_task: Optional[asyncio.Task] = None
        self._connected = False
        self._send_failed = False  # DIAGNOSTIC: log the FIRST send failure only, not every frame

    def _url(self) -> str:
        base = settings.sarvam_base_url.replace("https://", "wss://").replace("http://", "ws://")
        return (
            f"{base}/speech-to-text/ws"
            f"?language-code={self._language}"
            f"&model={self._model}"
            f"&mode={self._mode}"
            f"&sample_rate={self._sample_rate}"
            f"&input_audio_codec=pcm_s16le"
            f"&vad_signals=true&high_vad_sensitivity=true"
        )

    async def connect(self) -> bool:
        if self._connected:
            return True
        try:
            self._ws = await _ws_connect(self._url(), {"api-subscription-key": self._api_key})
            self._connected = True
            self._listen_task = asyncio.create_task(self._listen())
            logger.info("SarvamSTT connected (model=%s mode=%s rate=%s)", self._model, self._mode, self._sample_rate)
            return True
        except Exception as exc:
            logger.error("SarvamSTT connect failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        self._connected = False
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

    async def send_audio(self, pcm16: bytes) -> None:
        if not self._connected or not self._ws or not pcm16:
            return
        self._audio_seconds += len(pcm16) / 2 / self._sample_rate
        msg = {
            "audio": {
                "data": base64.b64encode(pcm16).decode("ascii"),
                "sample_rate": str(self._sample_rate),
                # Strict enum: 'audio/wav' is the only accepted value. The real
                # codec (raw PCM16) is declared via input_audio_codec in _url().
                "encoding": "audio/wav",
            }
        }
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as exc:
            # DIAGNOSTIC: swallowed today (call limps on silently). Surface the FIRST failure
            # loudly — it marks the exact moment audio stopped reaching STT (socket gone).
            if not self._send_failed:
                self._send_failed = True
                logger.warning(
                    "SarvamSTT send FAILED — audio no longer reaching STT (socket likely "
                    "closed); no reconnect exists, so transcripts stop here: %s", exc,
                )

    async def force_endpoint(self) -> None:
        if self._ws and self._connected:
            try:
                await self._ws.send(json.dumps({"type": "flush"}))
            except Exception:
                pass

    async def _listen(self) -> None:
        logger.info("SarvamSTT listen loop started")
        try:
            async for raw in self._ws:
                await self._handle(raw)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("SarvamSTT listen ended (error): %s", exc)
            return
        # DIAGNOSTIC: normal async-for completion = the SERVER closed the socket. This is the
        # prime suspect for 'greeting + one reply + silence': after this line no transcript can
        # ever fire again and there is no reconnect. If you see this right after the first reply,
        # that's the root cause.
        logger.warning("SarvamSTT listen loop ENDED — server closed the socket; NO further transcripts")

    async def _handle(self, raw) -> None:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return

        mtype = msg.get("type")
        data = msg.get("data") if isinstance(msg.get("data"), dict) else {}

        # VAD events: {"type":"events","data":{"signal_type":"START_SPEECH"|"END_SPEECH"}}
        if mtype == "events":
            signal = data.get("signal_type") or data.get("event_type")
            logger.info("SarvamSTT VAD event: %s", signal)  # DIAGNOSTIC: confirms STT still hears audio after turn 1
            if signal == "START_SPEECH" and self._speech_cb:
                await self._speech_cb()  # barge-in
            return

        # Transcript: each 'data' message is a VAD-endpointed utterance → FINAL.
        if mtype == "data":
            transcript = data.get("transcript")
            # DIAGNOSTIC: every FINAL the STT emits. If only ONE of these prints per call, the
            # agent's silence is upstream of the handler (STT stopped), exactly as the repro showed.
            logger.info("SarvamSTT FINAL transcript: %r (lang=%s)",
                        (transcript or "")[:80], data.get("language_code"))
            if transcript and self._transcript_cb:
                await self._transcript_cb(transcript.strip(), True, data.get("language_code"))
            return

        if mtype == "error":
            logger.warning("SarvamSTT server error: %s", data)
            return
