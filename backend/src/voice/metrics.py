"""Lightweight per-call latency metrics for the real-time voice loop."""

from dataclasses import dataclass, field


@dataclass
class SessionMetrics:
    response_latencies_ms: list[int] = field(default_factory=list)
    tts_chars: int = 0
    stt_seconds: float = 0.0

    def record_response(self, ms: int | None) -> None:
        if ms is not None and ms >= 0:
            self.response_latencies_ms.append(ms)

    def p50_ms(self) -> int | None:
        if not self.response_latencies_ms:
            return None
        s = sorted(self.response_latencies_ms)
        return s[len(s) // 2]

    def summary(self) -> dict:
        return {
            "turns": len(self.response_latencies_ms),
            "p50_response_ms": self.p50_ms(),
            "tts_chars": self.tts_chars,
            "stt_seconds": round(self.stt_seconds, 1),
        }
