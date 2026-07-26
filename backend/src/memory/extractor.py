"""Post-call extraction: transcript + order → structured retailer profile → Supermemory."""

import json
from datetime import date
from typing import Optional

import httpx

from src.core.config import settings
from src.core.logging import get_logger
from src.memory.retailer_memory import RetailerMemoryClient
from src.voice.llm.dialogue_client import DialogueLLMClient

logger = get_logger(__name__)


async def _translate_to_english(text: str) -> str:
    """Translate an Indic-script note to English via Sarvam's Mayura translate API.

    The chat model (sarvam-105b) reliably mirrors the call's script even when told to
    translate, so the post-call summary is normalised through the dedicated translate
    endpoint instead. Source language is auto-detected. Returns "" on failure.
    """
    try:
        async with httpx.AsyncClient(base_url=settings.sarvam_base_url, timeout=20) as c:
            r = await c.post(
                "/translate",
                headers={"api-subscription-key": settings.sarvam_api_key},
                json={
                    "input": text[:1900],
                    "source_language_code": "auto",
                    "target_language_code": "en-IN",
                    "model": "mayura:v1",
                },
            )
            if r.status_code < 400:
                return (r.json().get("translated_text") or "").strip()
            logger.warning("translate API %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("translate API failed: %s", exc)
    return ""

_EXTRACT_SYS = (
    "You write a concise CRM memory note for a rural FMCG retailer from a sales-call "
    "transcript. Output 4-6 short factual bullet lines covering: the usual/ordered basket, "
    "any items declined and the reason, response to the scheme offered, best call time if "
    "mentioned, and overall sentiment. No preamble, just the bullets. "
    "ALWAYS write the note in English, even when the call was in Kannada, Tamil, Hindi or "
    "any other language — translate what was said; do not output the original script."
)


def _has_non_latin(s: str) -> bool:
    """True if the text contains Indic script (Devanagari/Tamil/Kannada/…) — i.e. not
    translated to English. ₹ and × sit outside this range, so they don't trip it."""
    return any(0x0900 <= ord(c) <= 0x0DFF for c in s)


def _fallback_note(outlet_name: str, transcript: list[dict], order_result: Optional[dict]) -> str:
    lines = [f"Call with {outlet_name} on {date.today().isoformat()}."]
    if order_result and order_result.get("order_id"):
        items = ", ".join(
            f"{it['qty']}× {it['name']}" for it in order_result.get("items", [])
        ) or "order placed"
        lines.append(f"Ordered: {items} (₹{order_result.get('total_rupees', '?')}).")
    else:
        lines.append("No order placed this call.")
    said = " | ".join(t["text"] for t in transcript if t.get("role") == "user")[:400]
    if said:
        lines.append(f"Retailer said: {said}")
    return "\n".join(lines)


async def extract_and_store(
    *,
    llm: DialogueLLMClient,
    memory: RetailerMemoryClient,
    outlet_name: str,
    outlet_code: str,
    transcript: list[dict],
    order_result: Optional[dict] = None,
) -> str:
    """Summarise the call into a memory note and persist it. Returns the note."""
    convo = "\n".join(f"{t.get('role')}: {t.get('text')}" for t in transcript)
    note = ""
    try:
        note = await llm.complete(
            [
                {"role": "system", "content": _EXTRACT_SYS},
                {
                    "role": "user",
                    "content": (
                        f"Transcript:\n{convo}\n\n"
                        f"Order result: {json.dumps(order_result or {})}\n\n"
                        "Write the CRM note now. OUTPUT LANGUAGE: ENGLISH ONLY. The call was "
                        "likely in Kannada/Tamil/Hindi — translate everything into English. "
                        "Do NOT output any Kannada, Tamil, Devanagari or other non-Latin script; "
                        "every word must be in English."
                    ),
                },
            ]
        )
    except Exception as exc:
        logger.warning("extractor LLM failed: %s", exc)
    if not note.strip():
        note = _fallback_note(outlet_name, transcript, order_result)
    if _has_non_latin(note):
        # Sarvam-105B mirrors the call's script (and fallback quotes echo the caller);
        # normalise the final note to English via the Mayura translate API.
        english = await _translate_to_english(note)
        if english:
            note = english
    await memory.store_profile(outlet_code, note, {"type": "call_summary"})
    return note
