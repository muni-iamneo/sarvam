"""Probe: measure time-to-first-CONTENT-token for sarvam-105b under different
reasoning-suppression knobs. sarvam-105b is a reasoning model, so it may stream
`reasoning_content` before any user-visible `content` — pure dead air on a voice
call. This finds which knob (if any) the endpoint honors to cut that.

Run: backend/.venv/bin/python -m scripts.llm_latency_probe
"""

import asyncio
import time

from openai import AsyncOpenAI

from src.core.config import settings

MESSAGES = [
    {"role": "system", "content": "You are a friendly FMCG sales agent. Reply in one short sentence."},
    {"role": "system", "content": "Greet the retailer 'Sri Lakshmi Stores' warmly and ask about this week's usual order."},
]

VARIANTS = [
    ("baseline", {}),
    ("enable_thinking=false", {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}),
    ("reasoning_effort=low", {"reasoning_effort": "low"}),
    ("max_tokens=160", {"max_tokens": 160}),
    ("thinking_off+max_tokens", {"max_tokens": 160, "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}),
]


async def run_one(client: AsyncOpenAI, label: str, extra: dict) -> None:
    t0 = time.monotonic()
    t_first_reason = None
    t_first_content = None
    reason_chars = 0
    content = ""
    err = None
    try:
        stream = await client.chat.completions.create(
            model=settings.sarvam_llm_model,
            messages=MESSAGES,
            stream=True,
            temperature=settings.sarvam_llm_temperature,
            **extra,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                if t_first_reason is None:
                    t_first_reason = time.monotonic()
                reason_chars += len(rc)
            if getattr(delta, "content", None):
                if t_first_content is None:
                    t_first_content = time.monotonic()
                content += delta.content
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"

    def ms(t):
        return f"{int((t - t0) * 1000)}ms" if t else "—"

    print(f"\n=== {label} ===")
    if err:
        print(f"  ERROR: {err}")
        return
    print(f"  first reasoning token : {ms(t_first_reason)}  ({reason_chars} reasoning chars)")
    print(f"  first CONTENT token   : {ms(t_first_content)}   <-- time to first spoken word")
    print(f"  total                 : {ms(time.monotonic())}")
    print(f"  content ({len(content)} chars): {content[:160]!r}")


async def main() -> None:
    if not settings.sarvam_api_key:
        print("No SARVAM_API_KEY in env/.env — cannot probe.")
        return
    client = AsyncOpenAI(
        api_key=settings.sarvam_api_key,
        base_url=settings.sarvam_base_url.rstrip("/") + "/v1",
    )
    print(f"model={settings.sarvam_llm_model} base={settings.sarvam_base_url}/v1")
    for label, extra in VARIANTS:
        await run_one(client, label, extra)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
