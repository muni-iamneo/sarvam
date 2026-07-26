"""Abstract STT client interface for the BharatBeat voice loop.

The call handler talks to STT only through this interface, so providers are
swappable. ``on_transcript`` reports ``(text, is_final, language_code)``;
``on_speech_started`` fires on server VAD START_SPEECH (used for barge-in).
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Optional

TranscriptCb = Callable[[str, bool, Optional[str]], Awaitable[None]]
SpeechStartedCb = Callable[[], Awaitable[None]]


class BaseSTTClient(ABC):
    _transcript_cb: Optional[TranscriptCb] = None
    _speech_cb: Optional[SpeechStartedCb] = None
    _audio_seconds: float = 0.0

    @abstractmethod
    async def connect(self) -> bool:
        """Open the streaming transport."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the transport."""

    @abstractmethod
    async def send_audio(self, pcm16: bytes) -> None:
        """Send a PCM16 (8 kHz mono) chunk to the provider."""

    @abstractmethod
    async def force_endpoint(self) -> None:
        """Flush/finalize the current utterance (e.g. after agent TTS ends)."""

    def on_transcript(self, cb: TranscriptCb) -> None:
        self._transcript_cb = cb

    def on_speech_started(self, cb: SpeechStartedCb) -> None:
        self._speech_cb = cb

    @property
    def audio_seconds_sent(self) -> float:
        return self._audio_seconds

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__
