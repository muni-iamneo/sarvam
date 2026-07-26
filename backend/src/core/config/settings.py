"""Application settings loaded from environment / .env via pydantic-settings.

All third-party credentials (Sarvam, Twilio, Supermemory) and the Postgres URL
live here. Values are read from environment variables (case-insensitive) or a
local ``.env`` file. See ``.env.example`` for the full list.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load backend/.env into os.environ (idempotent, does NOT override real env vars),
# resolved relative to this file so it works regardless of the process CWD. This
# makes .env values visible to BOTH pydantic-settings below AND plain
# os.environ.get(...) reads elsewhere (e.g. DEMO_HERO_PHONE in scripts/seed.py).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:  # python-dotenv missing — pydantic still reads .env for its own fields
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ App
    app_name: str = "BharatBeat"
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    cors_origins: str = Field(default="*", description="Comma-separated allowed origins")

    # Public URLs for Twilio webhooks. Set to the ngrok tunnel at run time.
    #   public_url      -> https base for the TwiML/status webhooks (with scheme)
    #   public_ws_host  -> host only for the wss media stream, e.g. "abc.ngrok-free.app"
    public_url: str = Field(default="", description="Public https base URL for Twilio webhooks")
    public_ws_host: str = Field(default="", description="Public host for the wss media stream")

    # ------------------------------------------------------------- Database
    database_url: str = Field(
        default="postgresql+asyncpg://bharatbeat:bharatbeat@localhost:5432/bharatbeat",
        description="Async SQLAlchemy URL (postgresql+asyncpg://...)",
    )
    db_echo: bool = Field(default=False)
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    auto_create_all: bool = Field(default=True, description="Create tables on startup (dev)")

    # Single-company demo tenant; scopes dashboard queries by default.
    default_company_code: str = Field(default="colgate")

    # --------------------------------------------------------------- Sarvam
    sarvam_api_key: str = Field(default="")
    sarvam_base_url: str = Field(default="https://api.sarvam.ai")
    sarvam_stt_model: str = Field(default="saaras:v3")
    sarvam_stt_mode: str = Field(default="transcribe", description="transcribe|codemix|translate")
    sarvam_stt_language: str = Field(default="unknown", description="'unknown' = auto-detect")
    sarvam_sample_rate: int = Field(default=8000, description="Telephony-native 8 kHz")
    endpoint_debounce_s: float = Field(
        default=0.45,
        description="Seconds to wait after a FINAL transcript for more fragments before "
        "generating. Coalesces Sarvam's over-segmented finals into one turn; also the "
        "largest fixed slice of round-trip latency. Lower = snappier turns; too low risks "
        "splitting one utterance. Safe to keep low now that the think phase is barge-proof.",
    )
    sarvam_tts_model: str = Field(default="bulbul:v3")
    sarvam_tts_speaker: str = Field(default="priya", description="Must be a bulbul:v3 speaker")
    sarvam_tts_default_language: str = Field(default="hi-IN", description="Fallback TTS language")
    sarvam_llm_model: str = Field(default="sarvam-105b")
    sarvam_llm_temperature: float = Field(default=0.2)
    sarvam_reasoning_effort: str | None = Field(
        default="low",
        description="null|low|medium|high. sarvam-105b/30b are reasoning models. "
        "'low' is REQUIRED for the live loop: without thinking the model loses track "
        "of call state and just re-greets every turn, never advancing to tools/order "
        "(observed: 0 completed orders with null). null is ~0.5s faster to first token "
        "but breaks the conversation — do not use it for the dialogue loop.",
    )
    sarvam_llm_max_tokens: int = Field(
        default=640,
        description="Bounds a live dialogue turn. Must be generous enough that a "
        "multi-item order read-back (Indic script = more tokens/word) or a "
        "tool-call's streamed JSON args don't get truncated mid-output.",
    )

    # --------------------------------------------------------------- Twilio
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_from_number: str = Field(default="", description="Non-Indian voice-capable caller ID")
    twilio_validate_signature: bool = Field(default=True)
    twilio_record_calls: bool = Field(default=True)

    # ----------------------------------------------------------- Supermemory
    supermemory_api_key: str = Field(default="")
    supermemory_api_url: str = Field(default="https://api.supermemory.ai")

    # ---------------------------------------------------------------- Voice
    # Round-trip latency guardrails for the real-time loop.
    silence_watchdog_s: float = Field(default=8.0)
    max_call_minutes: int = Field(default=8)

    # ------------------------------------------------------------ Scheduler
    # Background batch-call worker (run-now + future-scheduled campaigns).
    scheduler_enabled: bool = Field(default=True)
    scheduler_poll_seconds: float = Field(default=5.0, description="Worker tick interval")

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# Sarvam-supported conversation languages (bulbul:v3 TTS + saaras:v3 STT). Single
# source of truth for the operator's per-call language choice; served to the UI via
# GET /api/config/languages and validated against on both call-start flows.
SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "hi-IN", "label": "Hindi"},
    {"code": "en-IN", "label": "English"},
    {"code": "bn-IN", "label": "Bengali"},
    {"code": "gu-IN", "label": "Gujarati"},
    {"code": "kn-IN", "label": "Kannada"},
    {"code": "ml-IN", "label": "Malayalam"},
    {"code": "mr-IN", "label": "Marathi"},
    {"code": "od-IN", "label": "Odia"},
    {"code": "pa-IN", "label": "Punjabi"},
    {"code": "ta-IN", "label": "Tamil"},
    {"code": "te-IN", "label": "Telugu"},
]
SUPPORTED_LANGUAGE_CODES: frozenset[str] = frozenset(lang["code"] for lang in SUPPORTED_LANGUAGES)
