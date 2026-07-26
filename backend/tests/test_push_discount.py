"""Pushed-product discount: pure better-of logic + DB-backed order totals."""

from src.domain.pricing import SchemeSpec, better_scheme
from src.tools.order_tools import ToolContext, get_order_summary, place_order

PCT5 = SchemeSpec(kind="pct", min_qty=1, discount_pct=5.0, description="5%")
PCT15 = SchemeSpec(kind="pct", min_qty=1, discount_pct=15.0, description="15%")


# ---- pure better_scheme ----

def test_push_wins_when_it_saves_more():
    assert better_scheme(PCT5, PCT15, 100000, 3) is PCT15


def test_base_kept_when_it_saves_more():
    assert better_scheme(PCT15, PCT5, 100000, 3) is PCT15


def test_none_base_returns_push():
    assert better_scheme(None, PCT15, 100000, 3) is PCT15


def test_none_push_returns_base():
    assert better_scheme(PCT5, None, 100000, 3) is PCT5


# ---- DB-backed: discount reflected in order totals ----

async def _outlet(db, seeded):
    from sqlalchemy import select
    from src.domain import models as m
    return (await db.execute(select(m.Outlet).where(m.Outlet.id == seeded["outlet_id"]))).scalar_one()


async def test_push_discount_beats_base_scheme_in_summary(db, seeded):
    outlet = await _outlet(db, seeded)
    ctx = ToolContext(db=db, outlet=outlet, push_sku_id=seeded["sku_a"], push_discount_pct=50.0)
    ctx.cart[seeded["sku_a"]] = 1  # unit_price 1500.00, base scheme 5%
    summary = await get_order_summary(ctx, {})
    # 50% push beats the 5% base -> ₹750.00 net on a ₹1500 case.
    assert summary["items"][0]["line_total_rupees"] == 750.0
    assert summary["total_rupees"] == 750.0


async def test_no_push_uses_base_scheme(db, seeded):
    outlet = await _outlet(db, seeded)
    ctx = ToolContext(db=db, outlet=outlet)  # no push
    ctx.cart[seeded["sku_a"]] = 1
    summary = await get_order_summary(ctx, {})
    # base 5% off ₹1500 -> ₹1425.00
    assert summary["items"][0]["line_total_rupees"] == 1425.0


async def test_push_discount_flows_into_placed_order(db, seeded):
    outlet = await _outlet(db, seeded)
    ctx = ToolContext(db=db, outlet=outlet, push_sku_id=seeded["sku_a"], push_discount_pct=50.0)
    ctx.cart[seeded["sku_a"]] = 1
    result = await place_order(ctx, {})
    assert result["total_rupees"] == 750.0
