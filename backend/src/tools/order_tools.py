"""Postgres-backed implementations of the renewal-call order tools.

Facts (price/stock/schemes) always come from the DB — never the model. Amounts
are computed in paise and surfaced to the model in ₹ (rupees) for speaking.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import models as m
from src.domain.pricing import SchemeSpec, quote_line, scheme_savings_paise


@dataclass
class ToolContext:
    db: AsyncSession
    outlet: m.Outlet
    cart: dict[int, int] = field(default_factory=dict)  # sku_id -> qty
    order_id: Optional[int] = None
    should_end: bool = False


def _rupees(paise: int) -> float:
    return round(paise / 100, 2)


async def _sku(db: AsyncSession, sku_id: int) -> Optional[m.Sku]:
    return (await db.execute(select(m.Sku).where(m.Sku.id == sku_id))).scalar_one_or_none()


async def _best_scheme(db: AsyncSession, sku: m.Sku, qty: int) -> Optional[SchemeSpec]:
    schemes = (
        await db.execute(select(m.Scheme).where(m.Scheme.sku_id == sku.id, m.Scheme.active.is_(True)))
    ).scalars().all()
    best: Optional[SchemeSpec] = None
    best_sav = 0
    for s in schemes:
        spec = SchemeSpec(
            kind=s.kind, min_qty=s.min_qty, discount_pct=s.discount_pct,
            flat_off_paise=s.flat_off_paise, description=s.description,
        )
        sav = scheme_savings_paise(sku.unit_price_paise, qty, spec)
        if sav > best_sav:
            best, best_sav = spec, sav
    return best


async def lookup_products(ctx: ToolContext, args: dict) -> dict:
    q = (args.get("query") or "").strip()
    rows = (
        await ctx.db.execute(
            select(m.Sku)
            .where(m.Sku.company_id == ctx.outlet.company_id, m.Sku.active.is_(True), m.Sku.name.ilike(f"%{q}%"))
            .limit(8)
        )
    ).scalars().all()
    return {
        "products": [
            {
                "sku_id": s.id, "name": s.name, "pack": s.pack_size,
                "price_rupees": _rupees(s.unit_price_paise), "unit": s.unit_label,
                "in_stock": s.stock_units, "must_sell": s.is_must_sell,
            }
            for s in rows
        ]
    }


async def get_active_schemes(ctx: ToolContext, args: dict) -> dict:
    sku_ids = args.get("sku_ids") or list(ctx.cart.keys())
    quantities = args.get("quantities") or []
    out = []
    for i, sid in enumerate(sku_ids):
        sku = await _sku(ctx.db, int(sid))
        if not sku:
            continue
        qty = int(quantities[i]) if i < len(quantities) else ctx.cart.get(int(sid), 1)
        schemes = (
            await ctx.db.execute(select(m.Scheme).where(m.Scheme.sku_id == sku.id, m.Scheme.active.is_(True)))
        ).scalars().all()
        for s in schemes:
            spec = SchemeSpec(kind=s.kind, min_qty=s.min_qty, discount_pct=s.discount_pct,
                              flat_off_paise=s.flat_off_paise, description=s.description)
            out.append({
                "sku_id": sku.id, "sku": sku.name, "description": s.description,
                "min_qty": s.min_qty, "savings_rupees": _rupees(scheme_savings_paise(sku.unit_price_paise, qty, spec)),
                "at_qty": qty,
            })
    return {"schemes": out}


async def add_line_item(ctx: ToolContext, args: dict) -> dict:
    # Validate defensively: a max_tokens-truncated tool call yields empty/partial
    # args, which must fail cleanly (not KeyError) so the item isn't silently lost.
    try:
        sku_id, qty = int(args["sku_id"]), int(args["qty"])
    except (KeyError, TypeError, ValueError):
        return {"error": "add_line_item needs integer sku_id and qty"}
    if qty <= 0:
        return {"error": "qty must be a positive integer"}
    sku = await _sku(ctx.db, sku_id)
    if not sku:
        return {"error": "unknown sku_id"}
    ctx.cart[sku.id] = qty
    return await get_order_summary(ctx, {})


async def remove_line_item(ctx: ToolContext, args: dict) -> dict:
    try:
        sku_id = int(args["sku_id"])
    except (KeyError, TypeError, ValueError):
        return {"error": "remove_line_item needs an integer sku_id"}
    ctx.cart.pop(sku_id, None)
    return await get_order_summary(ctx, {})


async def get_order_summary(ctx: ToolContext, args: dict) -> dict:
    items = []
    total = 0
    savings = 0
    for sid, qty in ctx.cart.items():
        sku = await _sku(ctx.db, sid)
        if not sku:
            continue
        spec = await _best_scheme(ctx.db, sku, qty)
        q = quote_line(sku.unit_price_paise, qty, spec)
        total += q.net_paise
        savings += q.savings_paise
        items.append({
            "sku_id": sid, "name": sku.name, "qty": qty,
            "unit_price_rupees": _rupees(sku.unit_price_paise),
            "line_total_rupees": _rupees(q.net_paise),
            "scheme": q.scheme_description or None,
            "savings_rupees": _rupees(q.savings_paise),
        })
    return {
        "items": items,
        "total_rupees": _rupees(total),
        "total_savings_rupees": _rupees(savings),
        "delivery_date": (date.today() + timedelta(days=1)).isoformat(),
    }


async def place_order(ctx: ToolContext, args: dict) -> dict:
    if not ctx.cart:
        return {"error": "empty order"}
    order = m.Order(
        outlet_id=ctx.outlet.id, source="voice_agent", status="confirmed",
        delivery_date=date.today() + timedelta(days=1),
    )
    ctx.db.add(order)
    await ctx.db.flush()
    total = 0
    for sid, qty in ctx.cart.items():
        sku = await _sku(ctx.db, sid)
        if not sku:
            continue
        spec = await _best_scheme(ctx.db, sku, qty)
        q = quote_line(sku.unit_price_paise, qty, spec)
        total += q.net_paise
        ctx.db.add(m.OrderItem(order_id=order.id, sku_id=sid, qty=qty,
                               unit_price_paise=sku.unit_price_paise, line_total_paise=q.net_paise))
    order.total_paise = total
    ctx.outlet.last_order_at = datetime.now()
    await ctx.db.commit()
    ctx.order_id = order.id
    return {
        "order_id": order.id, "total_rupees": _rupees(total),
        "delivery_date": order.delivery_date.isoformat(), "status": "confirmed",
    }


async def end_call(ctx: ToolContext, args: dict) -> dict:
    ctx.should_end = True
    return {"ended": True, "reason": args.get("reason", "")}


TOOL_HANDLERS = {
    "lookup_products": lookup_products,
    "get_active_schemes": get_active_schemes,
    "add_line_item": add_line_item,
    "remove_line_item": remove_line_item,
    "get_order_summary": get_order_summary,
    "place_order": place_order,
    "end_call": end_call,
}
