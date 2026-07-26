"""Async query helpers powering the dashboard API.

Because manager/assignment links are soft integer columns, we resolve names
via small per-request lookup maps rather than SQL joins on FKs.
"""

import json
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import models as m
from src.domain import schemas as s


def _pct(achieved: int, target: int) -> float:
    return round(achieved / target * 100, 1) if target else 0.0


async def company_id_for_code(db: AsyncSession, code: str) -> Optional[int]:
    return (
        await db.execute(select(m.Company.id).where(m.Company.code == code))
    ).scalar_one_or_none()


async def _rep_names(db: AsyncSession, cid: int) -> dict[int, str]:
    rows = (
        await db.execute(select(m.SalesRep.id, m.SalesRep.name).where(m.SalesRep.company_id == cid))
    ).all()
    return {r[0]: r[1] for r in rows}


async def _sum_by(db: AsyncSession, model, col, cid: int, year: int, month: int, type_col, type_val, amount_col):
    rows = (
        await db.execute(
            select(col, func.sum(amount_col))
            .where(
                model.company_id == cid,
                model.year == year,
                model.month == month,
                type_col == type_val,
                col.is_not(None),
            )
            .group_by(col)
        )
    ).all()
    return {r[0]: int(r[1] or 0) for r in rows}


async def _counts_by(db: AsyncSession, col, cid: int):
    rows = (
        await db.execute(
            select(col, func.count()).where(m.Outlet.company_id == cid).group_by(col)
        )
    ).all()
    return {r[0]: int(r[1]) for r in rows}


# ---------------------------------------------------------------- regions
async def list_regions(db: AsyncSession, cid: int) -> list[s.RegionOut]:
    now = datetime.now()
    regions = (await db.execute(select(m.Region).where(m.Region.company_id == cid))).scalars().all()
    reps = await _rep_names(db, cid)
    areas_per = {
        r[0]: int(r[1])
        for r in (
            await db.execute(select(m.Area.region_id, func.count()).group_by(m.Area.region_id))
        ).all()
    }
    outlets_per = await _counts_by(db, m.Outlet.region_id, cid)
    tgt = await _sum_by(db, m.SalesTarget, m.SalesTarget.region_id, cid, now.year, now.month,
                        m.SalesTarget.target_type, "Secondary", m.SalesTarget.target_amount_paise)
    ach = await _sum_by(db, m.SalesAchievement, m.SalesAchievement.region_id, cid, now.year, now.month,
                        m.SalesAchievement.sales_type, "Secondary", m.SalesAchievement.achieved_amount_paise)
    out = []
    for r in regions:
        t, a = tgt.get(r.id, 0), ach.get(r.id, 0)
        out.append(s.RegionOut(
            id=r.id, name=r.name, code=r.code, zone=r.zone,
            regional_manager=reps.get(r.regional_manager_id),
            n_areas=areas_per.get(r.id, 0), n_outlets=outlets_per.get(r.id, 0),
            target_paise=t, achieved_paise=a, achievement_pct=_pct(a, t),
        ))
    return out


# ------------------------------------------------------------------ areas
async def list_areas(db: AsyncSession, cid: int, region_id: Optional[int] = None) -> list[s.AreaOut]:
    now = datetime.now()
    q = select(m.Area).join(m.Region, m.Area.region_id == m.Region.id).where(m.Region.company_id == cid)
    if region_id:
        q = q.where(m.Area.region_id == region_id)
    areas = (await db.execute(q)).scalars().all()
    reps = await _rep_names(db, cid)
    region_names = {
        r[0]: r[1] for r in (await db.execute(select(m.Region.id, m.Region.name))).all()
    }
    outlets_per = await _counts_by(db, m.Outlet.area_id, cid)
    tgt = await _sum_by(db, m.SalesTarget, m.SalesTarget.area_id, cid, now.year, now.month,
                        m.SalesTarget.target_type, "Secondary", m.SalesTarget.target_amount_paise)
    ach = await _sum_by(db, m.SalesAchievement, m.SalesAchievement.area_id, cid, now.year, now.month,
                        m.SalesAchievement.sales_type, "Secondary", m.SalesAchievement.achieved_amount_paise)
    out = []
    for a in areas:
        t, ac = tgt.get(a.id, 0), ach.get(a.id, 0)
        out.append(s.AreaOut(
            id=a.id, region_id=a.region_id, region_name=region_names.get(a.region_id, ""),
            name=a.name, code=a.code,
            area_manager=reps.get(a.area_manager_id),
            deputy_area_manager=reps.get(a.deputy_area_manager_id),
            n_outlets=outlets_per.get(a.id, 0),
            target_paise=t, achieved_paise=ac, achievement_pct=_pct(ac, t),
        ))
    return out


# ---------------------------------------------------------------- outlets
async def list_outlets(
    db: AsyncSession, cid: int, *, region_id=None, area_id=None, q=None, bbox=None, limit=500
) -> list[s.OutletOut]:
    query = select(m.Outlet).where(m.Outlet.company_id == cid)
    if region_id:
        query = query.where(m.Outlet.region_id == region_id)
    if area_id:
        query = query.where(m.Outlet.area_id == area_id)
    if q:
        query = query.where(m.Outlet.name.ilike(f"%{q}%"))
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(x) for x in bbox.split(","))
            query = query.where(
                m.Outlet.lon >= min_lon, m.Outlet.lon <= max_lon,
                m.Outlet.lat >= min_lat, m.Outlet.lat <= max_lat,
            )
        except ValueError:
            pass
    query = query.order_by(m.Outlet.id).limit(limit)
    outlets = (await db.execute(query)).scalars().all()

    reps = await _rep_names(db, cid)
    region_names = {r[0]: r[1] for r in (await db.execute(select(m.Region.id, m.Region.name))).all()}
    area_rows = (await db.execute(select(m.Area.id, m.Area.name, m.Area.area_manager_id))).all()
    area_names = {r[0]: r[1] for r in area_rows}
    area_mgr = {r[0]: r[2] for r in area_rows}
    terr_names = {r[0]: r[1] for r in (await db.execute(select(m.Territory.id, m.Territory.name))).all()}
    beat_rows = (await db.execute(select(m.Beat.id, m.Beat.name, m.Beat.sales_rep_id))).all()
    beat_names = {r[0]: r[1] for r in beat_rows}
    beat_rep = {r[0]: r[2] for r in beat_rows}
    dist_names = {r[0]: r[1] for r in (await db.execute(select(m.Distributor.id, m.Distributor.name))).all()}

    out = []
    for o in outlets:
        out.append(s.OutletOut(
            id=o.id, code=o.code, name=o.name, phone=o.phone, language=o.language,
            owner_name=o.owner_name, outlet_class=o.outlet_class, trade_type=o.trade_type,
            category=o.category, lat=o.lat, lon=o.lon, best_call_time=o.best_call_time,
            last_order_at=o.last_order_at, status=o.status,
            region_name=region_names.get(o.region_id), area_name=area_names.get(o.area_id),
            territory_name=terr_names.get(o.territory_id), beat_name=beat_names.get(o.beat_id),
            distributor_name=dist_names.get(o.distributor_id),
            sales_rep=reps.get(beat_rep.get(o.beat_id)),
            area_manager=reps.get(area_mgr.get(o.area_id)),
        ))
    return out


async def get_outlet(db: AsyncSession, cid: int, outlet_id: int) -> Optional[s.OutletOut]:
    o = (
        await db.execute(
            select(m.Outlet).where(m.Outlet.company_id == cid, m.Outlet.id == outlet_id)
        )
    ).scalar_one_or_none()
    if not o:
        return None
    rows = await list_outlets(db, cid, limit=100000)
    for r in rows:
        if r.id == outlet_id:
            return r
    return None


# ------------------------------------------------------------------- reps
async def list_reps(db: AsyncSession, cid: int) -> list[s.RepOut]:
    reps_objs = (await db.execute(select(m.SalesRep).where(m.SalesRep.company_id == cid))).scalars().all()
    names = {r.id: r.name for r in reps_objs}
    region_names = {r[0]: r[1] for r in (await db.execute(select(m.Region.id, m.Region.name))).all()}
    area_names = {r[0]: r[1] for r in (await db.execute(select(m.Area.id, m.Area.name))).all()}
    terr_names = {r[0]: r[1] for r in (await db.execute(select(m.Territory.id, m.Territory.name))).all()}
    return [
        s.RepOut(
            id=r.id, name=r.name, employee_code=r.employee_code, designation=r.designation,
            reporting_manager_id=r.reporting_manager_id,
            reporting_manager=names.get(r.reporting_manager_id),
            region_name=region_names.get(r.region_id), area_name=area_names.get(r.area_id),
            territory_name=terr_names.get(r.territory_id), phone=r.phone,
        )
        for r in reps_objs
    ]


async def list_distributors(db: AsyncSession, cid: int) -> list[s.DistributorOut]:
    dists = (await db.execute(select(m.Distributor).where(m.Distributor.company_id == cid))).scalars().all()
    terr_names = {r[0]: r[1] for r in (await db.execute(select(m.Territory.id, m.Territory.name))).all()}
    return [
        s.DistributorOut(
            id=d.id, name=d.name, code=d.code, stockist_type=d.stockist_type,
            territory_name=terr_names.get(d.territory_id), contact_person=d.contact_person,
            phone=d.phone, warehouse_lat=d.warehouse_lat, warehouse_lon=d.warehouse_lon,
            credit_limit_paise=d.credit_limit_paise, margin_pct=d.margin_pct,
        )
        for d in dists
    ]


async def list_brands(db: AsyncSession, cid: int) -> list[s.BrandOut]:
    brands = (await db.execute(select(m.Brand).where(m.Brand.company_id == cid))).scalars().all()
    bm_names = {r[0]: r[1] for r in (await db.execute(select(m.BrandManager.id, m.BrandManager.name))).all()}
    sku_counts = {
        r[0]: int(r[1])
        for r in (await db.execute(select(m.Sku.brand_id, func.count()).group_by(m.Sku.brand_id))).all()
    }
    return [
        s.BrandOut(
            id=b.id, name=b.name, code=b.code, category=b.category,
            brand_manager=bm_names.get(b.brand_manager_id), n_skus=sku_counts.get(b.id, 0),
        )
        for b in brands
    ]


async def list_brand_managers(db: AsyncSession, cid: int) -> list[s.BrandManagerOut]:
    bms = (await db.execute(select(m.BrandManager).where(m.BrandManager.company_id == cid))).scalars().all()
    brand_counts = {
        r[0]: int(r[1])
        for r in (await db.execute(select(m.Brand.brand_manager_id, func.count()).group_by(m.Brand.brand_manager_id))).all()
    }
    return [
        s.BrandManagerOut(
            id=b.id, name=b.name, employee_code=b.employee_code, designation=b.designation,
            n_brands=brand_counts.get(b.id, 0),
        )
        for b in bms
    ]


# ----------------------------------------------------------------- orders
async def list_orders(db: AsyncSession, cid: int, limit: int = 50) -> list[s.OrderOut]:
    outlet_names = {r[0]: r[1] for r in (await db.execute(select(m.Outlet.id, m.Outlet.name).where(m.Outlet.company_id == cid))).all()}
    sku_names = {r[0]: r[1] for r in (await db.execute(select(m.Sku.id, m.Sku.name))).all()}
    orders = (
        await db.execute(select(m.Order).order_by(m.Order.created_at.desc()).limit(limit))
    ).scalars().all()
    out = []
    for o in orders:
        if o.outlet_id not in outlet_names:
            continue
        items = [
            s.OrderItemOut(sku_name=sku_names.get(it.sku_id, "?"), qty=it.qty,
                           unit_price_paise=it.unit_price_paise, line_total_paise=it.line_total_paise)
            for it in o.items
        ]
        out.append(s.OrderOut(
            id=o.id, outlet_name=outlet_names.get(o.outlet_id, "?"), total_paise=o.total_paise,
            status=o.status, source=o.source, delivery_date=o.delivery_date, created_at=o.created_at,
            n_items=len(items), items=items,
        ))
    return out


# ------------------------------------------------------------------ calls
async def _outlet_names(db: AsyncSession, cid: int) -> dict[int, tuple[str, str]]:
    rows = (
        await db.execute(select(m.Outlet.id, m.Outlet.name, m.Outlet.code).where(m.Outlet.company_id == cid))
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def list_calls(db: AsyncSession, cid: int, limit: int = 50) -> list[s.CallLogOut]:
    names = await _outlet_names(db, cid)
    rows = (
        await db.execute(select(m.CallLog).order_by(m.CallLog.started_at.desc()).limit(limit))
    ).scalars().all()
    out = []
    for cl in rows:
        if cl.outlet_id not in names:
            continue
        name, code = names[cl.outlet_id]
        out.append(s.CallLogOut(
            id=cl.id, outlet_name=name, outlet_code=code, twilio_call_sid=cl.twilio_call_sid,
            started_at=cl.started_at, ended_at=cl.ended_at, outcome=cl.outcome,
            language_detected=cl.language_detected, order_id=cl.order_id,
            latency_p50_ms=cl.latency_p50_ms, cost_inr_paise=cl.cost_inr_paise, summary=cl.summary,
        ))
    return out


async def get_call(db: AsyncSession, cid: int, call_id: int) -> Optional[s.CallDetailOut]:
    cl = (await db.execute(select(m.CallLog).where(m.CallLog.id == call_id))).scalar_one_or_none()
    if not cl:
        return None
    names = await _outlet_names(db, cid)
    if cl.outlet_id not in names:
        return None
    name, code = names[cl.outlet_id]
    try:
        transcript = json.loads(cl.transcript) if cl.transcript else []
    except ValueError:
        transcript = []
    order = None
    if cl.order_id:
        orders = await list_orders(db, cid, limit=100000)
        order = next((o for o in orders if o.id == cl.order_id), None)
    # Expose the recording via our auth-proxy path when Twilio has (or can have)
    # a recording for this call — i.e. once it has a Call SID. The proxy resolves
    # the actual media (stored SID, else a lazy lookup) and 404s if none exists.
    recording_url = f"/api/calls/{cl.id}/recording" if (cl.recording_sid or cl.twilio_call_sid) else None
    return s.CallDetailOut(
        id=cl.id, outlet_name=name, outlet_code=code, twilio_call_sid=cl.twilio_call_sid,
        started_at=cl.started_at, ended_at=cl.ended_at, outcome=cl.outcome,
        language_detected=cl.language_detected, order_id=cl.order_id,
        latency_p50_ms=cl.latency_p50_ms, cost_inr_paise=cl.cost_inr_paise, summary=cl.summary,
        transcript=transcript, order=order,
        recording_url=recording_url, recording_duration_s=cl.recording_duration_s,
    )


# -------------------------------------------------------------- field ops
async def _rep_refs(db: AsyncSession, cid: int) -> dict[int, s.RepRef]:
    rows = (
        await db.execute(
            select(m.SalesRep.id, m.SalesRep.name, m.SalesRep.employee_code,
                   m.SalesRep.designation, m.SalesRep.phone)
            .where(m.SalesRep.company_id == cid)
        )
    ).all()
    return {
        r[0]: s.RepRef(id=r[0], name=r[1], employee_code=r[2], designation=r[3], phone=r[4])
        for r in rows
    }


async def _outlet_rep(db: AsyncSession, cid: int) -> dict[int, Optional[int]]:
    """outlet_id -> responsible sales_rep_id, resolved via the outlet's beat."""
    beat_rep = {r[0]: r[1] for r in (await db.execute(select(m.Beat.id, m.Beat.sales_rep_id))).all()}
    rows = (await db.execute(select(m.Outlet.id, m.Outlet.beat_id).where(m.Outlet.company_id == cid))).all()
    return {r[0]: beat_rep.get(r[1]) for r in rows}


async def list_deliveries(db: AsyncSession, cid: int) -> list[s.RepDeliveriesOut]:
    """Confirmed voice orders awaiting delivery, grouped under the responsible rep."""
    outlet_rows = {
        r[0]: (r[1], r[2], r[3])
        for r in (
            await db.execute(
                select(m.Outlet.id, m.Outlet.name, m.Outlet.code, m.Outlet.area_id)
                .where(m.Outlet.company_id == cid)
            )
        ).all()
    }
    area_names = {r[0]: r[1] for r in (await db.execute(select(m.Area.id, m.Area.name))).all()}
    sku_names = {r[0]: r[1] for r in (await db.execute(select(m.Sku.id, m.Sku.name))).all()}
    outlet_rep = await _outlet_rep(db, cid)
    rep_refs = await _rep_refs(db, cid)

    today = date.today()
    orders = (
        await db.execute(
            select(m.Order)
            .where(
                m.Order.status.in_(("confirmed", "pending")),
                (m.Order.delivery_date.is_(None)) | (m.Order.delivery_date >= today),
            )
            .order_by(m.Order.delivery_date, m.Order.created_at)
        )
    ).scalars().all()

    groups: dict[Optional[int], list[s.DeliveryOut]] = {}
    for o in orders:
        if o.outlet_id not in outlet_rows:
            continue
        name, code, area_id = outlet_rows[o.outlet_id]
        items = [
            s.OrderItemOut(sku_name=sku_names.get(it.sku_id, "?"), qty=it.qty,
                           unit_price_paise=it.unit_price_paise, line_total_paise=it.line_total_paise)
            for it in o.items
        ]
        groups.setdefault(outlet_rep.get(o.outlet_id), []).append(s.DeliveryOut(
            order_id=o.id, outlet_id=o.outlet_id, outlet_name=name, outlet_code=code,
            area_name=area_names.get(area_id), total_paise=o.total_paise,
            delivery_date=o.delivery_date, status=o.status, created_at=o.created_at,
            call_id=o.call_id, n_items=len(items), items=items,
        ))

    result = [
        s.RepDeliveriesOut(
            rep=rep_refs.get(rid) or s.RepRef(),
            n_orders=len(ds), total_paise=sum(d.total_paise for d in ds), orders=ds,
        )
        for rid, ds in groups.items()
    ]
    result.sort(key=lambda g: g.total_paise, reverse=True)
    return result


# Signals detected in the (English) call summary → churn / visit reasons. A retailer
# explicitly asking for an in-person visit is the strongest "go here" signal there is,
# so it lives here alongside the churn cues rather than being inferred from an outcome.
_ALERT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "visit_requested": ("requested a visit", "request a visit", "asked for a visit", "wants a visit",
                        "want a visit", "visit request", "asked the rep to visit", "asked us to visit",
                        "visit the shop", "visit the store", "come to the shop", "come to the store",
                        "come and visit", "in-person visit", "in person visit", "physical visit",
                        "meet in person", "send a rep", "send someone", "wants someone to come"),
    "complaint": ("complaint", "complain", "damaged", "damage", "expired", "unhappy",
                  "angry", "frustrat", "poor service", "credit", "payment", "not paid", "dispute"),
    "competitor": ("competitor", "competing", "other brand", "switch", "switching", "rival",
                   "hul", "hindustan", "wipro", "p&g", "patanjali"),
    "overstock": ("overstock", "excess stock", "too much stock", "already stocked",
                  "enough stock", "stock is high", "high inventory", "surplus", "not selling"),
}
_SIGNAL_TEXT = {
    "declined": "Declined the renewal on the last call",
    "unreachable": "Repeatedly unreachable (no answer / failed calls)",
    "visit_requested": "Asked for an in-person visit from the sales rep",
    "complaint": "Raised a complaint or a service / payment issue",
    "competitor": "Mentioned a competitor or considering switching brands",
    "overstock": "Overstocked — holding back on ordering",
}


async def list_visit_alerts(db: AsyncSession, cid: int, days: int = 30) -> list[s.RepVisitAlertsOut]:
    """Derive at-risk outlets from recent calls (rules + English summary), grouped by rep."""
    outlet_rows = {
        r[0]: (r[1], r[2], r[3], r[4])
        for r in (
            await db.execute(
                select(m.Outlet.id, m.Outlet.name, m.Outlet.code, m.Outlet.area_id, m.Outlet.language)
                .where(m.Outlet.company_id == cid)
            )
        ).all()
    }
    area_names = {r[0]: r[1] for r in (await db.execute(select(m.Area.id, m.Area.name))).all()}
    outlet_rep = await _outlet_rep(db, cid)
    rep_refs = await _rep_refs(db, cid)

    since = datetime.now() - timedelta(days=days)
    calls = (
        await db.execute(
            select(m.CallLog).where(m.CallLog.started_at >= since).order_by(m.CallLog.started_at.desc())
        )
    ).scalars().all()

    by_outlet: dict[int, list] = {}
    for cl in calls:
        if cl.outlet_id in outlet_rows:
            by_outlet.setdefault(cl.outlet_id, []).append(cl)  # newest-first (query desc)

    alerts_by_rep: dict[Optional[int], list[s.VisitAlertOut]] = {}
    for oid, cls in by_outlet.items():
        last = cls[0]
        outcomes = [c.outcome for c in cls]
        blob = " ".join((c.summary or "") for c in cls).lower()
        unreachable = sum(1 for o in outcomes if o in ("no_answer", "failed"))
        # If the most recent call landed an order, the outlet has recovered — don't raise
        # a churn flag for older declines / missed calls (a live complaint still counts).
        recovered = last.outcome == "ordered" or last.order_id is not None

        signals: list[str] = []
        if "declined" in outcomes and not recovered:
            signals.append("declined")
        if unreachable >= 2 and not recovered:
            signals.append("unreachable")
        for sig, kws in _ALERT_KEYWORDS.items():
            if any(k in blob for k in kws):
                signals.append(sig)
        if not signals:
            continue  # healthy (e.g. ordered, no negatives) — no visit needed

        urgent = any(s in ("complaint", "competitor", "visit_requested") for s in signals) or unreachable >= 3
        reason = (last.summary or "").strip() or "; ".join(_SIGNAL_TEXT.get(s, s) for s in signals)
        name, code, area_id, lang = outlet_rows[oid]
        alerts_by_rep.setdefault(outlet_rep.get(oid), []).append(s.VisitAlertOut(
            outlet_id=oid, outlet_name=name, outlet_code=code, area_name=area_names.get(area_id),
            language=lang, urgency="urgent" if urgent else "watch", signals=signals, reason=reason,
            last_call_id=last.id, last_outcome=last.outcome, last_call_at=last.started_at,
            n_recent_calls=len(cls),
        ))

    result = []
    for rid, alerts in alerts_by_rep.items():
        alerts.sort(key=lambda a: (0 if a.urgency == "urgent" else 1, a.outlet_name))
        result.append(s.RepVisitAlertsOut(
            rep=rep_refs.get(rid) or s.RepRef(),
            n_alerts=len(alerts), n_urgent=sum(1 for a in alerts if a.urgency == "urgent"), alerts=alerts,
        ))
    result.sort(key=lambda g: (g.n_urgent, g.n_alerts), reverse=True)
    return result


# -------------------------------------------------------------- schedules
_TERMINAL_ITEM = ("done", "failed", "skipped")


async def _call_outcomes(db: AsyncSession, call_ids: list[int]) -> dict[int, str]:
    ids = [i for i in call_ids if i is not None]
    if not ids:
        return {}
    rows = (
        await db.execute(select(m.CallLog.id, m.CallLog.outcome).where(m.CallLog.id.in_(ids)))
    ).all()
    return {r[0]: r[1] for r in rows}


def _schedule_out(sch, names, outcomes, *, include_items: bool) -> s.ScheduleOut:
    items = list(sch.items)
    active = next((it for it in items if it.status == "calling"), None)
    item_outs: list[s.ScheduleItemOut] = []
    if include_items:
        for it in items:
            name, code = names.get(it.outlet_id, ("?", "?"))
            item_outs.append(s.ScheduleItemOut(
                id=it.id, outlet_id=it.outlet_id, outlet_name=name, outlet_code=code,
                to_number=it.to_number, position=it.position, status=it.status,
                call_id=it.call_id, note=it.note, outcome=outcomes.get(it.call_id),
                started_at=it.started_at, ended_at=it.ended_at,
            ))
    return s.ScheduleOut(
        id=sch.id, name=sch.name, mode=sch.mode, scheduled_at=sch.scheduled_at,
        status=sch.status, created_at=sch.created_at,
        n_items=len(items),
        n_done=sum(1 for it in items if it.status in _TERMINAL_ITEM),
        active_call_id=active.call_id if active else None,
        items=item_outs,
    )


async def list_schedules(db: AsyncSession, cid: int, limit: int = 50) -> list[s.ScheduleOut]:
    schs = (
        await db.execute(
            select(m.CallSchedule)
            .where(m.CallSchedule.company_id == cid)
            .order_by(m.CallSchedule.created_at.desc(), m.CallSchedule.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    names = await _outlet_names(db, cid)
    outcomes = await _call_outcomes(db, [it.call_id for sch in schs for it in sch.items])
    return [_schedule_out(sch, names, outcomes, include_items=False) for sch in schs]


async def get_schedule(db: AsyncSession, cid: int, schedule_id: int) -> Optional[s.ScheduleOut]:
    sch = (
        await db.execute(
            select(m.CallSchedule).where(
                m.CallSchedule.id == schedule_id, m.CallSchedule.company_id == cid
            )
        )
    ).scalar_one_or_none()
    if sch is None:
        return None
    names = await _outlet_names(db, cid)
    outcomes = await _call_outcomes(db, [it.call_id for it in sch.items])
    return _schedule_out(sch, names, outcomes, include_items=True)


async def create_schedule(db: AsyncSession, cid: int, payload: s.ScheduleCreate) -> s.ScheduleOut:
    names = await _outlet_names(db, cid)
    sch = m.CallSchedule(
        company_id=cid, name=payload.name,
        mode="scheduled" if payload.mode == "scheduled" else "now",
        scheduled_at=payload.scheduled_at if payload.mode == "scheduled" else None,
        status="pending",
    )
    db.add(sch)
    await db.flush()
    pos = 0
    for it in payload.items:
        if it.outlet_id not in names:  # skip outlets outside this tenant
            continue
        db.add(m.CallScheduleItem(
            schedule_id=sch.id, outlet_id=it.outlet_id, to_number=it.to,
            position=pos, status="queued",
        ))
        pos += 1
    await db.commit()
    await db.refresh(sch)
    result = await get_schedule(db, cid, sch.id)
    assert result is not None
    return result


async def cancel_schedule(db: AsyncSession, cid: int, schedule_id: int) -> Optional[s.ScheduleOut]:
    sch = (
        await db.execute(
            select(m.CallSchedule).where(
                m.CallSchedule.id == schedule_id, m.CallSchedule.company_id == cid
            )
        )
    ).scalar_one_or_none()
    if sch is None:
        return None
    for it in sch.items:
        if it.status == "queued":
            it.status = "skipped"
            it.note = "canceled"
    if sch.status in ("pending", "running"):
        # leave a live call to finish; the worker completes/closes the schedule
        sch.status = "canceled"
    await db.commit()
    return await get_schedule(db, cid, schedule_id)


# --------------------------------------------------------------- overview
async def get_overview(db: AsyncSession, cid: int, company_name: str) -> s.OverviewOut:
    now = datetime.now()
    total = (await db.execute(select(func.count()).select_from(m.Outlet).where(m.Outlet.company_id == cid))).scalar() or 0
    active = (await db.execute(select(func.count()).select_from(m.Outlet).where(m.Outlet.company_id == cid, m.Outlet.status == "active"))).scalar() or 0
    ordered = (await db.execute(select(func.count()).select_from(m.Outlet).where(m.Outlet.company_id == cid, m.Outlet.last_order_at.is_not(None)))).scalar() or 0
    orders_total = (await db.execute(select(func.count()).select_from(m.Order))).scalar() or 0
    calls_today = (
        await db.execute(
            select(func.count()).select_from(m.CallLog).where(func.date(m.CallLog.started_at) == now.date())
        )
    ).scalar() or 0

    regions = await list_regions(db, cid)
    region_ach = [
        s.RegionAchievement(name=r.name, target_paise=r.target_paise, achieved_paise=r.achieved_paise, achievement_pct=r.achievement_pct)
        for r in regions
    ]
    tot_t = sum(r.target_paise for r in regions)
    tot_a = sum(r.achieved_paise for r in regions)

    return s.OverviewOut(
        company=company_name,
        total_outlets=total, active_outlets=active,
        coverage_pct=_pct(ordered, active),
        secondary_achievement_pct=_pct(tot_a, tot_t),
        calls_today=calls_today, orders_total=orders_total,
        region_achievement=region_ach,
        recent_orders=await list_orders(db, cid, limit=5),
    )
