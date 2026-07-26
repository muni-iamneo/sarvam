"""Pydantic response schemas for the dashboard + voice APIs."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class RegionOut(BaseModel):
    id: int
    name: str
    code: str
    zone: Optional[str] = None
    regional_manager: Optional[str] = None
    n_areas: int = 0
    n_outlets: int = 0
    target_paise: int = 0
    achieved_paise: int = 0
    achievement_pct: float = 0.0


class AreaOut(BaseModel):
    id: int
    region_id: int
    region_name: str
    name: str
    code: str
    area_manager: Optional[str] = None
    deputy_area_manager: Optional[str] = None
    n_outlets: int = 0
    target_paise: int = 0
    achieved_paise: int = 0
    achievement_pct: float = 0.0


class OutletOut(BaseModel):
    id: int
    code: str
    name: str
    phone: Optional[str] = None
    language: Optional[str] = None
    owner_name: Optional[str] = None
    outlet_class: Optional[str] = None
    trade_type: str
    category: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    best_call_time: Optional[str] = None
    last_order_at: Optional[datetime] = None
    status: str
    region_name: Optional[str] = None
    area_name: Optional[str] = None
    territory_name: Optional[str] = None
    beat_name: Optional[str] = None
    distributor_name: Optional[str] = None
    sales_rep: Optional[str] = None
    area_manager: Optional[str] = None


class RepOut(BaseModel):
    id: int
    name: str
    employee_code: str
    designation: str
    reporting_manager_id: Optional[int] = None
    reporting_manager: Optional[str] = None
    region_name: Optional[str] = None
    area_name: Optional[str] = None
    territory_name: Optional[str] = None
    phone: Optional[str] = None


class DistributorOut(BaseModel):
    id: int
    name: str
    code: str
    stockist_type: str
    territory_name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    warehouse_lat: Optional[float] = None
    warehouse_lon: Optional[float] = None
    credit_limit_paise: int = 0
    margin_pct: float = 0.0


class BrandOut(BaseModel):
    id: int
    name: str
    code: str
    category: Optional[str] = None
    brand_manager: Optional[str] = None
    n_skus: int = 0


class BrandManagerOut(BaseModel):
    id: int
    name: str
    employee_code: str
    designation: str
    n_brands: int = 0


class ProductOut(BaseModel):
    """A SKU the operator can pick to push on a call."""
    sku_id: int
    name: str
    code: str
    pack_size: Optional[str] = None
    unit_price_rupees: float
    unit_label: str


class LanguageOut(BaseModel):
    """A Sarvam-supported conversation language for the call-start dropdown."""
    code: str
    label: str


class OrderItemOut(BaseModel):
    sku_name: str
    qty: int
    unit_price_paise: int
    line_total_paise: int


class OrderOut(BaseModel):
    id: int
    outlet_name: str
    total_paise: int
    status: str
    source: str
    delivery_date: Optional[date] = None
    created_at: datetime
    n_items: int = 0
    items: list[OrderItemOut] = []


# ------------------------------------------------- Field Ops (rep-facing)
class RepRef(BaseModel):
    """Lightweight reference to the responsible sales rep (DSR) for a group."""
    id: Optional[int] = None
    name: Optional[str] = None
    employee_code: Optional[str] = None
    designation: Optional[str] = None
    phone: Optional[str] = None


class DeliveryOut(BaseModel):
    order_id: int
    outlet_id: int
    outlet_name: str
    outlet_code: str
    area_name: Optional[str] = None
    total_paise: int
    delivery_date: Optional[date] = None
    status: str
    created_at: datetime
    call_id: Optional[int] = None
    n_items: int = 0
    items: list[OrderItemOut] = []


class RepDeliveriesOut(BaseModel):
    """Confirmed voice orders a rep must deliver, grouped under that rep."""
    rep: RepRef
    n_orders: int = 0
    total_paise: int = 0
    orders: list[DeliveryOut] = []


class VisitAlertOut(BaseModel):
    outlet_id: int
    outlet_name: str
    outlet_code: str
    area_name: Optional[str] = None
    language: Optional[str] = None
    urgency: str  # 'urgent' | 'watch'
    signals: list[str] = []  # e.g. ['declined', 'overstock']
    reason: str  # English call summary (or a templated fallback)
    last_call_id: Optional[int] = None
    last_outcome: Optional[str] = None
    last_call_at: Optional[datetime] = None
    n_recent_calls: int = 0


class RepVisitAlertsOut(BaseModel):
    """At-risk outlets needing a visit, grouped under the responsible rep."""
    rep: RepRef
    n_alerts: int = 0
    n_urgent: int = 0
    alerts: list[VisitAlertOut] = []


class RegionAchievement(BaseModel):
    name: str
    target_paise: int
    achieved_paise: int
    achievement_pct: float


class OverviewOut(BaseModel):
    company: str
    total_outlets: int
    active_outlets: int
    coverage_pct: float
    secondary_achievement_pct: float
    calls_today: int
    orders_total: int
    region_achievement: list[RegionAchievement] = []
    recent_orders: list[OrderOut] = []


class CallLogOut(BaseModel):
    id: int
    outlet_name: str
    outlet_code: str
    twilio_call_sid: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    outcome: str
    language_detected: Optional[str] = None
    order_id: Optional[int] = None
    latency_p50_ms: Optional[int] = None
    cost_inr_paise: int = 0
    summary: Optional[str] = None


class CallDetailOut(CallLogOut):
    transcript: list[dict] = []
    order: Optional[OrderOut] = None
    # Backend proxy path for the Twilio recording (auth handled server-side).
    # Present when the call has a Twilio SID; the proxy 404s if none exists yet.
    recording_url: Optional[str] = None
    recording_duration_s: Optional[int] = None


# ---- Call scheduling ----

class ScheduleItemIn(BaseModel):
    outlet_id: int
    to: Optional[str] = None


class ScheduleCreate(BaseModel):
    name: Optional[str] = None
    mode: str = "now"  # now|scheduled
    scheduled_at: Optional[datetime] = None
    items: list[ScheduleItemIn] = []
    # Campaign-level targeting applied to every call in the batch.
    language: str  # required; validated against SUPPORTED_LANGUAGE_CODES
    push_sku_id: Optional[int] = None
    push_discount_pct: Optional[float] = None


class ScheduleItemOut(BaseModel):
    id: int
    outlet_id: int
    outlet_name: str
    outlet_code: str
    to_number: Optional[str] = None
    position: int
    status: str
    call_id: Optional[int] = None
    note: Optional[str] = None
    outcome: Optional[str] = None  # from the linked call_log, once it runs
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class ScheduleOut(BaseModel):
    id: int
    name: Optional[str] = None
    mode: str
    scheduled_at: Optional[datetime] = None
    status: str
    created_at: datetime
    n_items: int = 0
    n_done: int = 0
    active_call_id: Optional[int] = None  # call_id of the item currently 'calling'
    items: list[ScheduleItemOut] = []
