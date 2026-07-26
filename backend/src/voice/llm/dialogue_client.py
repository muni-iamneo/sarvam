"""Dialogue LLM client — Sarvam-105B via the OpenAI-compatible endpoint.

Sarvam exposes ``POST https://api.sarvam.ai/v1/chat/completions`` compatible
with the OpenAI SDK, with streaming + tool-calling.
"""

import json
import time
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

TokenCb = Callable[[str], Awaitable[None]]
ToolCb = Callable[[str, dict, str], Awaitable[None]]  # (name, args, tool_call_id)
CompleteCb = Callable[[str], Awaitable[None]]


class DialogueLLMClient:
    def __init__(self, model: str | None = None) -> None:
        # Empty key would make AsyncOpenAI raise at construction; fall back to a
        # placeholder so the client builds (real calls fail gracefully + log).
        self._client = AsyncOpenAI(
            api_key=settings.sarvam_api_key or "not-set",
            base_url=settings.sarvam_base_url.rstrip("/") + "/v1",
        )
        self._model = model or settings.sarvam_llm_model
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        on_token: TokenCb,
        on_tool_call: ToolCb,
        on_complete: CompleteCb,
    ) -> None:
        """Stream a completion, forwarding text tokens, tool calls, and completion."""
        text = ""
        tool_acc: dict[int, dict] = {}
        t0 = time.monotonic()
        first_content_logged = False
        finish_reason: str | None = None
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                stream=True,
                temperature=settings.sarvam_llm_temperature,
                max_tokens=settings.sarvam_llm_max_tokens,
                extra_body={"reasoning_effort": settings.sarvam_reasoning_effort},
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    if not first_content_logged:
                        first_content_logged = True
                        logger.info("LLM first content token: %d ms", int((time.monotonic() - t0) * 1000))
                    text += delta.content
                    await on_token(delta.content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    acc = tool_acc.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            acc["name"] = tc.function.name
                        if tc.function.arguments:
                            acc["args"] += tc.function.arguments
        except Exception as exc:
            logger.error("Dialogue LLM stream failed: %s", exc)

        if finish_reason == "length":
            # Hit max_tokens — the reply (or a tool call's JSON args) was cut off.
            # Surfacing it makes truncated turns diagnosable rather than silent.
            logger.warning(
                "LLM turn truncated (finish_reason=length): raise sarvam_llm_max_tokens "
                "(now %d) if this recurs; %d tool-call(s) may have partial args",
                settings.sarvam_llm_max_tokens, len(tool_acc),
            )

        for acc in tool_acc.values():
            if not acc["name"]:
                continue
            try:
                args = json.loads(acc["args"] or "{}")
            except ValueError:
                args = {}
            await on_tool_call(acc["name"], args, acc["id"])

        await on_complete(text)

    async def complete(self, messages: list[dict], max_tokens: int = 400) -> str:
        """Non-streaming completion (used for post-call extraction)."""
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=settings.sarvam_llm_temperature,
                stream=False,
                max_tokens=max_tokens,
                extra_body={"reasoning_effort": settings.sarvam_reasoning_effort},
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error("Dialogue LLM complete failed: %s", exc)
            return ""
