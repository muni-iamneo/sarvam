"""Pure pricing / scheme-savings helpers (no DB access).

Reused by the LLM order tools (Phase 5) and unit-tested directly. All amounts
are integer paise.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SchemeSpec:
    kind: str  # "pct" | "flat" | "slab"
    min_qty: int
    discount_pct: float = 0.0
    flat_off_paise: int = 0
    description: str = ""


@dataclass
class LineQuote:
    qty: int
    unit_price_paise: int
    gross_paise: int
    savings_paise: int
    net_paise: int
    scheme_applied: bool
    scheme_description: str


def scheme_savings_paise(unit_price_paise: int, qty: int, scheme: Optional[SchemeSpec]) -> int:
    """Savings in paise for applying ``scheme`` to ``qty`` units at ``unit_price_paise``."""
    if scheme is None or qty < scheme.min_qty:
        return 0
    gross = unit_price_paise * qty
    if scheme.kind == "pct":
        return round(gross * (scheme.discount_pct / 100.0))
    if scheme.kind == "flat":
        # flat per-unit discount on every unit
        return scheme.flat_off_paise * qty
    if scheme.kind == "slab":
        # flat_off granted once per full multiple of min_qty
        return scheme.flat_off_paise * (qty // scheme.min_qty)
    return 0


def quote_line(
    unit_price_paise: int, qty: int, scheme: Optional[SchemeSpec] = None
) -> LineQuote:
    """Compute gross/savings/net for a single order line."""
    gross = unit_price_paise * qty
    savings = scheme_savings_paise(unit_price_paise, qty, scheme)
    return LineQuote(
        qty=qty,
        unit_price_paise=unit_price_paise,
        gross_paise=gross,
        savings_paise=savings,
        net_paise=gross - savings,
        scheme_applied=savings > 0,
        scheme_description=scheme.description if (scheme and savings > 0) else "",
    )
