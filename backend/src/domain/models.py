"""SQLAlchemy models for the BharatBeat FMCG + voice-agent domain.

Money is stored as integer **paise** (no floats). To stay portable between
Postgres (prod) and SQLite (tests) and to avoid circular-FK DDL cycles, the
strict downward hierarchy + catalog + orders use real ``ForeignKey`` columns,
while "assignment/manager pointer" columns (e.g. area→manager, rep→territory,
distributor→territory) are plain indexed integers (soft references).
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.db import Base


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hq_city: Mapped[str | None] = mapped_column(String(80), default=None)
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), index=True)
    zone: Mapped[str | None] = mapped_column(String(20), default=None)  # North/South/East/West
    regional_manager_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Area(Base):
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), index=True)
    area_manager_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    deputy_area_manager_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Territory(Base):
    __tablename__ = "territories"
    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), index=True)
    tso_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    deputy_tso_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    distributor_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Beat(Base):
    __tablename__ = "beats"
    id: Mapped[int] = mapped_column(primary_key=True)
    territory_id: Mapped[int] = mapped_column(ForeignKey("territories.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), index=True)
    sales_rep_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    visit_frequency_days: Mapped[int] = mapped_column(Integer, default=7)
    day_of_week: Mapped[str | None] = mapped_column(String(40), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalesRep(Base):
    __tablename__ = "sales_reps"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    employee_code: Mapped[str] = mapped_column(String(30), index=True)
    designation: Mapped[str] = mapped_column(String(40))  # DSR|PSR|TSO|ASM|DeputyASM|RSM
    reporting_manager_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    region_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    area_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    territory_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    email: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrandManager(Base):
    __tablename__ = "brand_managers"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    employee_code: Mapped[str] = mapped_column(String(30), index=True)
    designation: Mapped[str] = mapped_column(String(40))  # Brand|Category|Product
    reporting_manager_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    email: Mapped[str | None] = mapped_column(String(120), default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Distributor(Base):
    __tablename__ = "distributors"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(30), index=True)
    stockist_type: Mapped[str] = mapped_column(String(30), default="Distributor")  # CFA|SuperStockist|Distributor|Stockist
    territory_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    contact_person: Mapped[str | None] = mapped_column(String(120), default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    email: Mapped[str | None] = mapped_column(String(120), default=None)
    warehouse_address: Mapped[str | None] = mapped_column(Text, default=None)
    warehouse_lat: Mapped[float | None] = mapped_column(Float, default=None)
    warehouse_lon: Mapped[float | None] = mapped_column(Float, default=None)
    credit_limit_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outlet(Base):
    """A retailer — the entity the voice agent calls."""

    __tablename__ = "outlets"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(30), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    language: Mapped[str | None] = mapped_column(String(10), default=None)  # preferred-language hint (e.g. ta-IN)
    owner_name: Mapped[str | None] = mapped_column(String(120), default=None)
    # geo chain (denormalised for fast dashboard filters)
    beat_id: Mapped[int | None] = mapped_column(ForeignKey("beats.id"), index=True, default=None)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("distributors.id"), index=True, default=None)
    territory_id: Mapped[int | None] = mapped_column(ForeignKey("territories.id"), index=True, default=None)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), index=True, default=None)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), index=True, default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)
    outlet_class: Mapped[str | None] = mapped_column(String(2), default=None)  # A|B|C|D
    trade_type: Mapped[str] = mapped_column(String(4), default="GT")  # GT|MT
    category: Mapped[str | None] = mapped_column(String(40), default=None)  # Kirana|Supermarket|...
    best_call_time: Mapped[str | None] = mapped_column(String(40), default=None)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), index=True)
    category: Mapped[str | None] = mapped_column(String(60), default=None)
    brand_manager_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Sku(Base):
    __tablename__ = "skus"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(30), index=True)
    pack_size: Mapped[str | None] = mapped_column(String(40), default=None)
    mrp_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, default=0)  # price to retailer per unit (e.g. per case)
    unit_label: Mapped[str] = mapped_column(String(20), default="case")
    stock_units: Mapped[int] = mapped_column(Integer, default=0)
    is_must_sell: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scheme(Base):
    __tablename__ = "schemes"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), index=True)
    description: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(10), default="pct")  # pct|flat|slab
    min_qty: Mapped[int] = mapped_column(Integer, default=1)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)  # for kind=pct
    flat_off_paise: Mapped[int] = mapped_column(BigInteger, default=0)  # for kind=flat (per unit)
    valid_from: Mapped[date | None] = mapped_column(Date, default=None)
    valid_to: Mapped[date | None] = mapped_column(Date, default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalesTarget(Base):
    __tablename__ = "sales_targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    target_type: Mapped[str] = mapped_column(String(12), default="Secondary")  # Primary|Secondary|Tertiary
    region_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    area_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    territory_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    sales_rep_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    distributor_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    brand_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    target_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalesAchievement(Base):
    __tablename__ = "sales_achievement"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    sales_type: Mapped[str] = mapped_column(String(12), default="Secondary")
    region_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    area_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    territory_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    sales_rep_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    distributor_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    brand_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    achieved_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    delivery_date: Mapped[date | None] = mapped_column(Date, default=None)
    source: Mapped[str] = mapped_column(String(20), default="voice_agent")
    call_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)  # soft ref to call_logs
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    line_total_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    order: Mapped["Order"] = relationship(back_populates="items")


class CallSchedule(Base):
    """A batch of outbound calls — either run-now (sequential) or future-scheduled."""

    __tablename__ = "call_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str | None] = mapped_column(String(160), default=None)
    mode: Mapped[str] = mapped_column(String(12), default="now")  # now|scheduled
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Campaign-level call targeting applied to every outlet in the batch.
    language: Mapped[str | None] = mapped_column(String(10), default=None)  # seeds turn-1 language
    push_sku_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)  # soft ref to skus.id
    push_discount_pct: Mapped[float | None] = mapped_column(Float, default=None)  # extra % off the pushed SKU
    # pending -> running -> completed ; also canceled|failed
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["CallScheduleItem"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", lazy="selectin",
        order_by="CallScheduleItem.position",
    )


class CallScheduleItem(Base):
    __tablename__ = "call_schedule_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("call_schedules.id"), index=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)
    to_number: Mapped[str | None] = mapped_column(String(20), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # queued -> calling -> done ; also failed|skipped
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    call_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)  # soft ref to call_logs
    note: Mapped[str | None] = mapped_column(String(240), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    schedule: Mapped["CallSchedule"] = relationship(back_populates="items")


class CallLog(Base):
    __tablename__ = "call_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    outcome: Mapped[str] = mapped_column(String(30), default="initiated")  # initiated|ordered|declined|no_answer|failed
    transcript: Mapped[str | None] = mapped_column(Text, default=None)  # JSON-encoded turns
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    language_detected: Mapped[str | None] = mapped_column(String(10), default=None)
    # Operator-chosen call targeting (set at dial time; read by the media stream).
    initial_language: Mapped[str | None] = mapped_column(String(10), default=None)  # seeds turn-1 language
    push_sku_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)  # soft ref to skus.id
    push_discount_pct: Mapped[float | None] = mapped_column(Float, default=None)  # extra % off the pushed SKU
    order_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    latency_p50_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    cost_inr_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    # Twilio call recording (captured via the recordingStatusCallback on hangup).
    recording_sid: Mapped[str | None] = mapped_column(String(64), default=None)
    recording_url: Mapped[str | None] = mapped_column(Text, default=None)  # Twilio media URL (auth-gated)
    recording_duration_s: Mapped[int | None] = mapped_column(Integer, default=None)
    recording_status: Mapped[str | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
