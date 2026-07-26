"""Guard against Sarvam-105B leaking tool calls as plain text.

The model sometimes emits a tool call in its native ``<arg_key>/<arg_value>``
template as ``delta.content`` instead of via the structured ``tool_calls``
field. Left unhandled it gets spoken to the retailer AND the tool never runs
(see the "let me check the schemes" loop on call #30). The client must parse
the leak into a real tool call and keep it out of the spoken/transcript stream.
"""

import types

from src.tools.tool_specs import ORDER_TOOLS
from src.voice.llm.dialogue_client import DialogueLLMClient, parse_leaked_tool_calls

KNOWN = {t["function"]["name"] for t in ORDER_TOOLS}

LEAK_TOKENS = [
    "get_active_schemes", "\n",
    "<arg_key>", "sku_ids", "</arg_key>", "\n",
    "<arg_value>", "[2]", "</arg_value>", "\n",
    "<arg_key>", "quantities", "</arg_key>", "\n",
    "<arg_value>", "[20]", "</arg_value>",
]


# ------------------------------------------------------------------ pure parser
def test_parse_single_leaked_call():
    text = "".join(LEAK_TOKENS)
    calls = parse_leaked_tool_calls(text, KNOWN)
    assert calls == [("get_active_schemes", {"sku_ids": [2], "quantities": [20]})]


def test_parse_ignores_prose():
    assert parse_leaked_tool_calls("வணக்கம், ஸ்ரீ லட்சுமி ஸ்டோர்ஸ்!", KNOWN) == []


def test_parse_multiple_leaked_calls():
    text = (
        "add_line_item\n<arg_key>sku_id</arg_key>\n<arg_value>2</arg_value>\n"
        "<arg_key>qty</arg_key>\n<arg_value>20</arg_value>\n"
        "get_order_summary\n"
    )
    calls = parse_leaked_tool_calls(text, KNOWN)
    assert calls == [
        ("add_line_item", {"sku_id": 2, "qty": 20}),
        ("get_order_summary", {}),
    ]


# ------------------------------------------------------------------ stream glue
def _chunk(content=None, tool_calls=None, finish_reason=None):
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = types.SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return types.SimpleNamespace(choices=[choice])


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def _gen():
            for c in self._chunks:
                yield c

        return _gen()


def _client_streaming(chunks):
    llm = DialogueLLMClient()

    async def _fake_create(**kwargs):
        return _FakeStream(chunks)

    llm._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=_fake_create)
        )
    )
    return llm


async def _run(llm):
    tokens, tool_calls, completed = [], [], []

    async def on_token(t):
        tokens.append(t)

    async def on_tool(name, args, tcid):
        tool_calls.append((name, args, tcid))

    async def on_complete(text):
        completed.append(text)

    await llm.stream(
        [{"role": "user", "content": "20"}], ORDER_TOOLS, on_token, on_tool, on_complete
    )
    return tokens, tool_calls, completed


async def test_leaked_call_is_not_spoken_and_executes():
    llm = _client_streaming([_chunk(content=t) for t in LEAK_TOKENS])
    tokens, tool_calls, completed = await _run(llm)

    spoken = "".join(tokens)
    assert "<arg_key>" not in spoken
    assert "get_active_schemes" not in spoken
    assert spoken.strip() == ""            # nothing spoken this turn
    assert completed == [""]               # no leaked text in the assistant turn
    assert tool_calls == [("get_active_schemes", {"sku_ids": [2], "quantities": [20]}, "leaked_0")]


async def test_prose_still_streams_to_tts():
    parts = ["வணக்கம்", ", ஸ்ரீ ", "லட்சுமி!", " ஆர்டரை உறுதி செய்யலாமா?"]
    llm = _client_streaming([_chunk(content=t) for t in parts])
    tokens, tool_calls, completed = await _run(llm)

    assert "".join(tokens) == "".join(parts)   # every prose token forwarded
    assert tool_calls == []


async def test_structured_tool_calls_still_work():
    tc = types.SimpleNamespace(
        index=0,
        id="call_1",
        function=types.SimpleNamespace(name="get_order_summary", arguments="{}"),
    )
    llm = _client_streaming([_chunk(tool_calls=[tc], finish_reason="tool_calls")])
    tokens, tool_calls, completed = await _run(llm)

    assert tool_calls == [("get_order_summary", {}, "call_1")]
