"""Probe v2: find a way to make Sarvam respond FAST on the voice path.

The reasoning preamble on sarvam-105b costs 11-19s. Standard knobs are ignored.
Try: (1) list models, (2) the `/no_think` prompt convention, (3) alternate
models, (4) chat_template_kwargs variants.
"""

import asyncio
import time

from openai import AsyncOpenAI

from src.core.config import settings

SYS = "You are a friendly FMCG sales agent. Reply in one short sentence, no preamble."
USER = "Greet 'Sri Lakshmi Stores' warmly and ask about this week's usual order."


def _msgs(extra_sys: str = "", user_suffix: str = ""):
    sys = SYS + (("\n" + extra_sys) if extra_sys else "")
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": USER + user_suffix},
    ]


async def timed(client, label, *, model, messages, extra):
    t0 = time.monotonic()
    tf_reason = tf_content = None
    reason_chars = 0
    content = ""
    err = None
    try:
        stream = await client.chat.completions.create(
            model=model, messages=messages, stream=True,
            temperature=settings.sarvam_llm_temperature, **extra,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            d = chunk.choices[0].delta
            rc = getattr(d, "reasoning_content", None)
            if rc:
                tf_reason = tf_reason or time.monotonic()
                reason_chars += len(rc)
            if getattr(d, "content", None):
                tf_content = tf_content or time.monotonic()
                content += d.content
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {str(exc)[:160]}"

    def ms(t):
        return f"{int((t - t0) * 1000)}ms" if t else "—"

    print(f"\n=== {label} (model={model}) ===")
    if err:
        print(f"  ERROR: {err}")
        return
    print(f"  first content: {ms(tf_content)}  | reasoning: {ms(tf_reason)} ({reason_chars} chars) | total {ms(time.monotonic())}")
    print(f"  content: {content[:150]!r}")


async def main():
    client = AsyncOpenAI(api_key=settings.sarvam_api_key,
                         base_url=settings.sarvam_base_url.rstrip("/") + "/v1")
    print(f"base={settings.sarvam_base_url}/v1")
    try:
        models = await client.models.list()
        print("MODELS:", [m.id for m in models.data])
    except Exception as exc:  # noqa: BLE001
        print("models.list failed:", type(exc).__name__, str(exc)[:160])

    M = settings.sarvam_llm_model  # sarvam-105b
    await timed(client, "105b + /no_think suffix", model=M, messages=_msgs(user_suffix=" /no_think"), extra={})
    await timed(client, "105b + /no_think in system", model=M, messages=_msgs(extra_sys="/no_think"), extra={})
    await timed(client, "105b + chat_template thinking=false", model=M, messages=_msgs(),
                extra={"extra_body": {"chat_template_kwargs": {"thinking": False}}})
    # alternate models
    for alt in ("sarvam-m", "sarvam-2b", "sarvam-30b"):
        await timed(client, f"{alt} baseline", model=alt, messages=_msgs(), extra={})
    await timed(client, "sarvam-m + /no_think", model="sarvam-m", messages=_msgs(user_suffix=" /no_think"), extra={})
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
