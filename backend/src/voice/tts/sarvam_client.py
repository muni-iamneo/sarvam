"""Sarvam Bulbul v3 TTS client.

POST https://api.sarvam.ai/text-to-speech with ``output_audio_codec="mulaw"``
and ``speech_sample_rate=8000`` returns base64 μ-law 8 kHz audio — Twilio-ready
after stripping any WAV header. Auth header: ``api-subscription-key``.
"""

import base64
from typing import Optional

import httpx

from src.audio.telephony import strip_wav_header
from src.core.config import settings
from src.core.logging import get_logger
from src.voice.tts.base import BaseTTSClient

logger = get_logger(__name__)


class SarvamBulbulTTSClient(BaseTTSClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: Optional[str] = None,
        speaker: Optional[str] = None,
        sample_rate: Optional[int] = None,
    ) -> None:
        self._model = model or settings.sarvam_tts_model
        self._speaker = speaker or settings.sarvam_tts_speaker
        self._sample_rate = sample_rate or settings.sarvam_sample_rate
        self._client = httpx.AsyncClient(
            base_url=settings.sarvam_base_url.rstrip("/"),
            headers={
                "api-subscription-key": api_key or settings.sarvam_api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._chars = 0

    async def synthesize(self, text: str, language_code: str) -> bytes:
        if not text or not text.strip():
            return b""
        # Bulbul rejects text with no letter/digit ("...", "—", a lone emoji) with a 400
        # ("must contain at least one character from the allowed languages"). The sentence
        # buffer's early clause-flush can hand us exactly such a fragment — there's nothing
        # to speak, so skip it silently instead of burning a failed request.
        if not any(c.isalnum() for c in text):
            return b""
        # Hard v3 limit is 2500 chars; the buffer caps chunks well below this, but guard
        # anyway so an oversized string degrades to truncated speech, not a 400.
        if len(text) > 2500:
            logger.warning("Bulbul TTS text %d chars > 2500 limit; truncating", len(text))
            text = text[:2500]
        self._chars += len(text)
        payload = {
            "text": text,
            "target_language_code": language_code or settings.sarvam_tts_default_language,
            "model": self._model,
            "speaker": self._speaker,
            "speech_sample_rate": self._sample_rate,
            "output_audio_codec": "mulaw",
        }
        try:
            resp = await self._client.post("/text-to-speech", json=payload)
            resp.raise_for_status()
            audios = resp.json().get("audios") or []
            if not audios:
                return b""
            return strip_wav_header(base64.b64decode(audios[0]))
        except httpx.HTTPStatusError as exc:
            # Surface Sarvam's error body — the bare exception hides why it 400'd.
            logger.warning("Bulbul TTS failed (%s) %s: %s", language_code,
                           exc.response.status_code, exc.response.text[:300])
            return b""
        except Exception as exc:
            logger.warning("Bulbul TTS failed (%s): %s", language_code, exc)
            return b""

    @property
    def characters_synthesized(self) -> int:
        return self._chars

    async def close(self) -> None:
        await self._client.aclose()
