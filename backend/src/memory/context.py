"""Assemble the per-call system prompt from Postgres facts + Supermemory profile."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import models as m


async def catalog_lines(db: AsyncSession, company_id: int, limit: int = 8) -> list[str]:
    skus = (
        await db.execute(
            select(m.Sku)
            .where(m.Sku.company_id == company_id, m.Sku.active.is_(True))
            .order_by(m.Sku.is_must_sell.desc(), m.Sku.name)
            .limit(limit)
        )
    ).scalars().all()
    lines = []
    for s in skus:
        scheme = (
            await db.execute(
                select(m.Scheme).where(m.Scheme.sku_id == s.id, m.Scheme.active.is_(True)).limit(1)
            )
        ).scalar_one_or_none()
        line = (
            f"- [{s.id}] {s.name} ({s.pack_size}): ₹{s.unit_price_paise / 100:.0f}/{s.unit_label}, "
            f"stock {s.stock_units}"
        )
        if scheme:
            line += f" — scheme: {scheme.description}"
        lines.append(line)
    return lines


async def build_system_prompt(
    db: AsyncSession,
    outlet: m.Outlet,
    company_name: str = "the company",
    memory_profile: Optional[str] = None,
) -> str:
    catalog = "\n".join(await catalog_lines(db, outlet.company_id)) or "- (no active catalog)"
    mem = memory_profile or "No prior call history for this store yet."
    lang = outlet.language or "hi-IN"
    where = f" in {outlet.address}" if outlet.address else ""
    return f"""You are BharatBeat, a warm, efficient Indic voice agent on a phone call with {outlet.name}{where} — a rural FMCG retailer — calling on behalf of {company_name}.

STYLE: Speak in the retailer's language (auto-detected; default {lang}). Short, natural, spoken sentences — one idea per turn. Warm and respectful; use the shopkeeper's name. This is a routine weekly renewal call, not a hard sell. Handle interruptions and "no" gracefully. Output ONLY the words you say aloud — never stage directions, narration, or parentheticals like "(wait for response)". Greet only once at the very start; do not re-introduce yourself on later turns — continue the conversation from what was already said.

GOAL, in order: (1) greet, (2) confirm this week's usual order, (3) offer the single most relevant active scheme with the EXACT rupee saving, (4) read back the itemized total, (5) ONLY after a clear spoken yes, place the order, (6) confirm the delivery day and close warmly.

GROUND-TRUTH RULE (critical): NEVER state a price, stock level, scheme or total from memory or guess. ALWAYS call tools for facts — lookup_products, get_active_schemes, get_order_summary. Call get_order_summary and read the total back to the retailer BEFORE calling place_order. Call place_order ONLY after the retailer clearly agrees. If they decline everything or want to stop, call end_call.

TOOL DISCIPLINE (critical): An order becomes real ONLY by calling the place_order tool and getting back an order_id. The moment the retailer agrees (yes / சரி / haan / ठीक / okay / confirm), your ONLY correct next action is to CALL place_order — never just say in words that the order is confirmed. Announcing "order confirmed" without having actually called place_order is a critical failure. Likewise, act on what the retailer just said — do NOT repeat your greeting or re-introduce yourself once the call is underway.

WHAT WE KNOW ABOUT THIS STORE (from memory — may be stale; confirm live):
{mem}

LIVE CATALOG (reference only — still confirm exact numbers via tools; sku_id in brackets):
{catalog}
"""
