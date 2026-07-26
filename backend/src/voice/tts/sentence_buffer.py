"""Buffers streaming LLM tokens and flushes sentence-sized chunks to TTS.

Sentence-level chunking keeps latency low (we synthesize the first sentence
while the LLM is still generating the rest) while staying under Bulbul's
per-request character limit.
"""

import re
from collections.abc import Awaitable, Callable

# Include the Devanagari danda (।) as a sentence terminator for Indic text.
_SENTENCE_END = re.compile(r"[.!?।](?:[\"')\]]*)\s*$|\n")
_ABBREVIATIONS = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Rs|No|etc|vs|approx)\.\s*$", re.IGNORECASE)
# Clause boundaries let us speak the opening fragment early (first chunk only).
_CLAUSE_END = re.compile(r"[,;:—–](?:[\"')\]]*)\s*$")


class SentenceBuffer:
    """Buffers streaming tokens into speakable chunks.

    The FIRST chunk of a turn is flushed early — on a clause boundary or a small
    char cap — so the first audio starts while the LLM is still generating the
    rest. Subsequent chunks use full-sentence boundaries for natural prosody.
    """

    def __init__(
        self,
        on_sentence: Callable[[str], Awaitable[None]],
        max_chars: int = 160,
        first_chunk_max_chars: int = 64,
    ) -> None:
        self._on_sentence = on_sentence
        self._buf = ""
        self._max = max_chars
        self._first_max = first_chunk_max_chars
        self._closed = False
        self._first_done = False

    async def add_token(self, token: str) -> None:
        if self._closed or not token:
            return
        self._buf += token
        stripped = self._buf.rstrip()
        if _SENTENCE_END.search(stripped) and not _ABBREVIATIONS.search(stripped):
            await self._emit()
            return
        n = len(self._buf.strip())
        if not self._first_done:
            # Speak the opening clause ASAP to cut time-to-first-audio.
            if (_CLAUSE_END.search(stripped) and n >= 12) or n >= self._first_max:
                await self._emit()
        elif n >= self._max:
            await self._emit()

    async def flush(self) -> None:
        await self._emit()

    def close(self) -> None:
        self._closed = True
        self._buf = ""

    async def _emit(self) -> None:
        text = self._buf.strip()
        self._buf = ""
        if text and not self._closed:
            self._first_done = True
            await self._on_sentence(text)
