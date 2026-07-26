"""Smoke-test Sarvam TTS (Bulbul) + LLM (Sarvam-105B) against the live API.

Requires SARVAM_API_KEY (set it in backend/.env). Validates the two HTTP-based
providers; streaming STT is exercised end-to-end during a real call.

Run:  backend/.venv/bin/python -m scripts.smoke_sarvam
"""

import asyncio

from src.core.config import settings
from src.core.logging import get_logger, setup_logging
from src.voice.llm.dialogue_client import DialogueLLMClient
from src.voice.tts.sarvam_client import SarvamBulbulTTSClient

setup_logging()
log = get_logger("smoke")


async def main() -> None:
    if not settings.sarvam_api_key:
        log.warning("SARVAM_API_KEY not set — add it to backend/.env to run this smoke test.")
        return

    # --- TTS (Bulbul) -> μ-law 8k bytes ---
    tts = SarvamBulbulTTSClient()
    audio = await tts.synthesize("Vanakkam! This is a BharatBeat test call.", "ta-IN")
    log.info("Bulbul TTS returned %d μ-law bytes", len(audio))
    if audio:
        with open("/tmp/bulbul_test.ulaw", "wb") as f:
            f.write(audio)
        log.info("Wrote /tmp/bulbul_test.ulaw")
    await tts.close()

    # --- LLM (Sarvam-105B) streaming, no tools ---
    llm = DialogueLLMClient()
    tokens: list[str] = []

    async def on_token(t: str):
        tokens.append(t)

    async def on_tool(name, args, tcid):
        log.info("tool_call: %s %s", name, args)

    async def on_done(text: str):
        log.info("LLM complete (%d chars)", len(text))

    await llm.stream(
        [{"role": "user", "content": "Reply with one short Tamil sentence greeting a shopkeeper."}],
        None,
        on_token,
        on_tool,
        on_done,
    )
    print("LLM says:", "".join(tokens))


if __name__ == "__main__":
    asyncio.run(main())
