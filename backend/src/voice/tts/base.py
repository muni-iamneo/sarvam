"""Abstract TTS client interface for the BharatBeat voice loop."""

from abc import ABC, abstractmethod


class BaseTTSClient(ABC):
    @abstractmethod
    async def synthesize(self, text: str, language_code: str) -> bytes:
        """Synthesize ``text`` and return **μ-law 8 kHz** audio bytes (Twilio-ready)."""

    async def close(self) -> None:  # pragma: no cover - trivial
        return None

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__
