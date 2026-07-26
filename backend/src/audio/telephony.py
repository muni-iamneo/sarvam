"""Telephony audio helpers: μ-law ↔ PCM16, resampling, and frame chunking.

Twilio Media Streams carry base64-encoded **μ-law (PCMU) 8 kHz mono** in
~20 ms / 160-byte frames. Sarvam STT accepts PCM16 at 8 kHz; Sarvam Bulbul TTS
can emit μ-law 8 kHz directly. So the hot path is just μ-law→PCM16 (inbound to
STT) and re-framing Bulbul's μ-law (outbound to Twilio) — minimal transcoding.

Python 3.12 ships stdlib ``audioop``; on 3.13+ install the ``audioop-lts``
backport (same import name).
"""

import audioop
import base64
from collections.abc import Iterator

MULAW_RATE = 8000
FRAME_BYTES = 160  # 20 ms of 8 kHz μ-law (1 byte/sample)


def mulaw_to_pcm16(mulaw: bytes) -> bytes:
    """Decode μ-law bytes to 16-bit linear PCM."""
    return audioop.ulaw2lin(mulaw, 2)


def pcm16_to_mulaw(pcm16: bytes) -> bytes:
    """Encode 16-bit linear PCM to μ-law bytes."""
    return audioop.lin2ulaw(pcm16, 2)


def b64_mulaw_to_pcm16(payload_b64: str) -> bytes:
    """Twilio inbound ``media.payload`` (base64 μ-law) → PCM16 bytes."""
    return mulaw_to_pcm16(base64.b64decode(payload_b64))


def resample_pcm16(pcm16: bytes, src_rate: int, dst_rate: int, state=None) -> tuple[bytes, object]:
    """Resample mono PCM16 between rates via ``audioop.ratecv`` (carries state)."""
    if src_rate == dst_rate:
        return pcm16, state
    converted, new_state = audioop.ratecv(pcm16, 2, 1, src_rate, dst_rate, state)
    return converted, new_state


def strip_wav_header(data: bytes) -> bytes:
    """Return the PCM/μ-law payload from a WAV container, if present."""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        idx = data.find(b"data")
        if idx != -1:
            return data[idx + 8 :]
    return data


def frame_bytes(data: bytes, size: int = FRAME_BYTES) -> Iterator[bytes]:
    """Yield fixed-size frames from a byte string (last frame may be shorter)."""
    for i in range(0, len(data), size):
        yield data[i : i + size]


def mulaw_to_twilio_frames(mulaw: bytes, size: int = FRAME_BYTES) -> Iterator[str]:
    """Yield base64-encoded μ-law frames ready for Twilio ``media`` messages."""
    for frame in frame_bytes(mulaw, size):
        yield base64.b64encode(frame).decode("ascii")
