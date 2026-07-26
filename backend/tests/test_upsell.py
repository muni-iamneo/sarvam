"""Upsell selection logic — pure `_best_upsell` + the once-per-call guard."""

from src.domain.pricing import SchemeSpec
from src.tools.order_tools import ToolContext, _best_upsell, suggest_upsell


def _cand(sku_id, name, price, stock, must_sell, scheme):
    return {
        "sku_id": sku_id, "name": name, "pack_size": "48-case",
        "unit_price_paise": price, "stock_units": stock,
        "is_must_sell": must_sell, "scheme": scheme,
    }


PCT10 = SchemeSpec(kind="pct", min_qty=3, discount_pct=10.0, description="10% off on 3+")
FLAT40 = SchemeSpec(kind="flat", min_qty=2, flat_off_paise=4000, description="₹40 off/case on 2+")


def test_picks_highest_saving_not_in_cart():
    cands = [
        _cand(1, "Surf", 150000, 210, True, PCT10),   # at qty 3 -> ₹450
        _cand(2, "Vim", 60000, 140, False, FLAT40),   # at qty 2 -> ₹80
    ]
    best = _best_upsell(cands, cart_sku_ids=set())
    assert best["sku_id"] == 1
    assert best["suggested_qty"] == 3
    assert best["savings_rupees"] == 450.0
    assert best["offer"] == "10% off on 3+"


def test_excludes_skus_already_in_cart():
    cands = [
        _cand(1, "Surf", 150000, 210, True, PCT10),
        _cand(2, "Vim", 60000, 140, False, FLAT40),
    ]
    # Surf already ordered -> should fall through to Vim.
    best = _best_upsell(cands, cart_sku_ids={1})
    assert best["sku_id"] == 2
    assert best["savings_rupees"] == 80.0


def test_excludes_out_of_stock_at_unlock_qty():
    # Only 1 case of Vim left, but the offer needs 2 -> not pitchable.
    cands = [_cand(2, "Vim", 60000, 1, False, FLAT40)]
    assert _best_upsell(cands, cart_sku_ids=set()) is None


def test_prefers_must_sell_on_tie():
    same = SchemeSpec(kind="flat", min_qty=1, flat_off_paise=5000, description="₹50 off")
    cands = [
        _cand(1, "Plain", 100000, 50, False, same),      # ₹50
        _cand(2, "Priority", 100000, 50, True, same),    # ₹50, must-sell
    ]
    best = _best_upsell(cands, cart_sku_ids=set())
    assert best["sku_id"] == 2


def test_none_when_every_offer_is_in_cart():
    cands = [
        _cand(1, "Surf", 150000, 210, True, PCT10),
        _cand(2, "Vim", 60000, 140, False, FLAT40),
    ]
    assert _best_upsell(cands, cart_sku_ids={1, 2}) is None


def test_none_when_saving_is_zero():
    dead = SchemeSpec(kind="pct", min_qty=1, discount_pct=0.0, description="0%")
    cands = [_cand(1, "Surf", 150000, 210, True, dead)]
    assert _best_upsell(cands, cart_sku_ids=set()) is None


async def test_suggest_upsell_fires_only_once():
    # Second call must short-circuit to None without touching the DB (db=None proves it).
    ctx = ToolContext(db=None, outlet=None, upsell_offered=True)
    assert await suggest_upsell(ctx, {}) == {"suggestion": None}
