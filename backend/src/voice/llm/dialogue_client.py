"""Dialogue LLM client — Sarvam-105B via the OpenAI-compatible endpoint.

Sarvam exposes ``POST https://api.sarvam.ai/v1/chat/completions`` compatible
with the OpenAI SDK, with streaming + tool-calling.
"""

import json
import re
import time
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

TokenCb = Callable[[str], Awaitable[None]]
ToolCb = Callable[[str, dict, str], Awaitable[None]]  # (name, args, tool_call_id)
CompleteCb = Callable[[str], Awaitable[None]]

# Sarvam-105B sometimes emits a tool call as PLAIN-TEXT content in its native
# template instead of via the structured OpenAI ``tool_calls`` field — the
# endpoint's tool-parser fails to convert it and the raw template leaks into the
# content stream, e.g.:
#     get_active_schemes
#     <arg_key>sku_ids</arg_key>
#     <arg_value>[2]</arg_value>
# Unhandled, this gets spoken to the retailer (SentenceBuffer flushes on \n) AND
# the tool never runs. We parse the leak back into a real tool call and suppress
# it from the spoken/transcript stream. `<arg_key>` is the unambiguous marker —
# no natural Indic reply contains it.
_ARG_PAIR = re.compile(
    r"<arg_key>\s*(?P<key>.*?)\s*</arg_key>\s*<arg_value>\s*(?P<val>.*?)\s*</arg_value>",
    re.DOTALL,
)
_LEAK_MARKER = "<arg_key>"


def _coerce_arg(raw: str):
    """Parse a leaked ``<arg_value>`` payload — JSON when it parses (``[2]`` →
    ``[2]``, ``20`` → ``20``), otherwise the raw string."""
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def parse_leaked_tool_calls(text: str, known_names: set[str]) -> list[tuple[str, dict]]:
    """Extract tool calls from Sarvam's leaked ``<arg_key>/<arg_value>`` text.

    Returns ``[(name, args), ...]`` in emission order. A block begins at a bare
    known tool name and owns every arg pair up to the next bare tool name, so
    multiple back-to-back leaked calls parse correctly. Prose with no leak
    marker returns ``[]``.
    """
    if not known_names:
        return []
    # One ordered scanner over BOTH tokens: a bare tool name opens a new call,
    # an arg pair adds to the open call. Arg pairs come first in the alternation
    # so a name appearing inside a value can't be mistaken for a header.
    name_alt = "|".join(re.escape(n) for n in sorted(known_names, key=len, reverse=True))
    token = re.compile(
        r"<arg_key>\s*(?P<key>.*?)\s*</arg_key>\s*<arg_value>\s*(?P<val>.*?)\s*</arg_value>"
        r"|(?P<name>\b(?:" + name_alt + r")\b)",
        re.DOTALL,
    )
    calls: list[tuple[str, dict]] = []
    for match in token.finditer(text):
        if match.group("name"):
            calls.append((match.group("name"), {}))
        elif calls:  # an arg pair with no preceding name has nowhere to attach
            calls[-1][1][match.group("key")] = _coerce_arg(match.group("val"))
    return calls


class _ContentGate:
    """Routes streamed content: prose -> on_token (spoken/transcribed), a leaked
    tool-call template -> held aside for parsing.

    Classifies from the FIRST content so a normal reply forwards with ~zero
    added latency: an Indic/prose opening is neither a tool name nor its prefix,
    so it commits to prose immediately. Only an ambiguous leading ASCII
    tool-name prefix is briefly buffered until ``<arg_key>`` settles it as a
    leak (held, never spoken) or a non-header char settles it as prose.
    """

    _CAP = 48  # a real leak shows <arg_key> within ~25 chars; caps prose held while ambiguous

    def __init__(self, on_token: TokenCb, known_names: set[str]) -> None:
        self._on_token = on_token
        self._known = known_names
        # No tools this turn (greeting) => nothing can leak; forward everything.
        self._mode = "unknown" if known_names else "prose"
        self._buf = ""       # unclassified leading content
        self.text = ""       # forwarded (spoken) prose
        self.leaked = ""     # held leaked tool-call template

    async def _forward(self, s: str) -> None:
        if s:
            self.text += s
            await self._on_token(s)

    async def feed(self, chunk: str) -> None:
        if self._mode == "prose":
            await self._forward(chunk)
            return
        if self._mode == "leak":
            self.leaked += chunk
            return
        self._buf += chunk                       # unknown: buffer and classify
        if _LEAK_MARKER in self._buf:
            self._mode, self.leaked, self._buf = "leak", self._buf, ""
            return
        head = self._buf.lstrip().split("\n", 1)[0]
        # Still (a prefix of) a bare tool name => it could yet become a leak.
        still_maybe = head == "" or any(n.startswith(head) for n in self._known)
        if not still_maybe or len(self._buf) > self._CAP:
            self._mode = "prose"
            await self._forward(self._buf)
            self._buf = ""

    async def finish(self) -> None:
        # Ended while still ambiguous (reply was literally a bare tool-name word,
        # no args) -> it was prose after all; speak it rather than swallow it.
        if self._buf:
            await self._forward(self._buf)
            self._buf = ""


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
        known_names = {t["function"]["name"] for t in tools} if tools else set()
        gate = _ContentGate(on_token, known_names)
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
                    await gate.feed(delta.content)
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

        await gate.finish()

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

        # Recover any tool call Sarvam leaked as plain text instead of via the
        # structured field: execute it (and keep it out of on_complete's text so
        # it's never spoken or stored as the assistant turn).
        if gate.leaked:
            leaked = parse_leaked_tool_calls(gate.leaked, known_names)
            logger.warning(
                "LLM leaked %d tool-call(s) as text (server tool-parser miss); recovered %d",
                gate.leaked.count(_LEAK_MARKER), len(leaked),
            )
            for i, (name, args) in enumerate(leaked):
                await on_tool_call(name, args, f"leaked_{i}")

        await on_complete(gate.text)

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
