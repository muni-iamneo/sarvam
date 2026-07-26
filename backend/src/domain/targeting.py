"""Pure validation for operator-chosen call targeting (language + product push).

Kept DB-free so both the start-call and schedule-call endpoints share one rule set
and it is trivially unit-testable. The pushed-SKU tenant check is DB-bound and lives
in the endpoints.
"""

from typing import Optional

from src.core.config.settings import SUPPORTED_LANGUAGE_CODES


class TargetingError(ValueError):
    """Invalid call-targeting input (endpoints map this to HTTP 400)."""


def validate_targeting(
    language: str, push_sku_id: Optional[int], push_discount_pct: Optional[float]
) -> None:
    if language not in SUPPORTED_LANGUAGE_CODES:
        raise TargetingError(f"unsupported language '{language}'")
    if push_sku_id is not None:
        if push_discount_pct is None:
            raise TargetingError("push_discount_pct required when a product is pushed")
        if not (0 < push_discount_pct <= 100):
            raise TargetingError("push_discount_pct must be between 0 and 100")
