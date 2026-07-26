"""Dashboard REST API — company-scoped reads of the FMCG hierarchy."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domain import models as m
from src.domain import repository as repo
from src.domain import schemas as s
from src.domain.db import get_db

router = APIRouter(prefix="/api", tags=["dashboard"])


async def ctx(db: AsyncSession = Depends(get_db)) -> tuple[AsyncSession, int, str]:
    row = (
        await db.execute(select(m.Company).where(m.Company.code == settings.default_company_code))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=503, detail="No company seeded — run scripts/seed.py")
    return db, row.id, row.name


@router.get("/overview", response_model=s.OverviewOut)
async def overview(c=Depends(ctx)):
    db, cid, name = c
    return await repo.get_overview(db, cid, name)


@router.get("/regions", response_model=list[s.RegionOut])
async def regions(c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_regions(db, cid)


@router.get("/areas", response_model=list[s.AreaOut])
async def areas(region_id: Optional[int] = None, c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_areas(db, cid, region_id)


@router.get("/outlets", response_model=list[s.OutletOut])
async def outlets(
    region_id: Optional[int] = None,
    area_id: Optional[int] = None,
    q: Optional[str] = None,
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = 500,
    c=Depends(ctx),
):
    db, cid, _ = c
    return await repo.list_outlets(db, cid, region_id=region_id, area_id=area_id, q=q, bbox=bbox, limit=limit)


@router.get("/outlets/{outlet_id}", response_model=s.OutletOut)
async def outlet_detail(outlet_id: int, c=Depends(ctx)):
    db, cid, _ = c
    out = await repo.get_outlet(db, cid, outlet_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Outlet not found")
    return out


@router.get("/reps", response_model=list[s.RepOut])
async def reps(c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_reps(db, cid)


@router.get("/distributors", response_model=list[s.DistributorOut])
async def distributors(c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_distributors(db, cid)


@router.get("/brands", response_model=list[s.BrandOut])
async def brands(c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_brands(db, cid)


@router.get("/brand-managers", response_model=list[s.BrandManagerOut])
async def brand_managers(c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_brand_managers(db, cid)


@router.get("/orders", response_model=list[s.OrderOut])
async def orders(limit: int = 50, c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_orders(db, cid, limit=limit)


@router.get("/deliveries", response_model=list[s.RepDeliveriesOut])
async def deliveries(c=Depends(ctx)):
    """Confirmed voice orders to deliver, grouped by the responsible sales rep."""
    db, cid, _ = c
    return await repo.list_deliveries(db, cid)


@router.get("/visit-alerts", response_model=list[s.RepVisitAlertsOut])
async def visit_alerts(days: int = 30, c=Depends(ctx)):
    """At-risk outlets needing a rep visit, derived from recent calls, grouped by rep."""
    db, cid, _ = c
    return await repo.list_visit_alerts(db, cid, days=days)
