"""Shared test fixtures: an in-memory SQLite DB (single shared connection via
StaticPool), a seeded single-tenant catalog, and an httpx client bound to the
FastAPI app with ``get_db`` overridden to the test session.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain import models as m
from src.domain.db import Base, get_db


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_engine):
    Session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db):
    """One company (code 'colgate'), a brand, two SKUs (A is must-sell with a 5%
    scheme), and an outlet. Returns the ids the tests reference."""
    company = m.Company(code="colgate", name="Colgate")
    db.add(company)
    await db.flush()
    brand = m.Brand(company_id=company.id, name="Surf", code="SURF")
    db.add(brand)
    await db.flush()
    sku_a = m.Sku(
        brand_id=brand.id, company_id=company.id, name="Surf Excel", code="SURF-EXCEL",
        pack_size="48-case", mrp_paise=200000, unit_price_paise=150000, unit_label="case",
        stock_units=500, is_must_sell=True, active=True,
    )
    sku_b = m.Sku(
        brand_id=brand.id, company_id=company.id, name="Vim Bar", code="VIM-BAR",
        pack_size="60-case", mrp_paise=80000, unit_price_paise=60000, unit_label="case",
        stock_units=300, is_must_sell=False, active=True,
    )
    db.add_all([sku_a, sku_b])
    await db.flush()
    db.add(m.Scheme(sku_id=sku_a.id, description="5% off", kind="pct",
                    min_qty=1, discount_pct=5.0, active=True))
    outlet = m.Outlet(company_id=company.id, name="Bengaluru Store 17",
                      code="BLR-17", phone="+910000000000", language="kn-IN")
    db.add(outlet)
    await db.commit()
    return {
        "company_id": company.id, "sku_a": sku_a.id, "sku_b": sku_b.id,
        "sku_a_name": "Surf Excel", "outlet_id": outlet.id,
    }


@pytest_asyncio.fixture
async def client(_engine, seeded):
    """httpx AsyncClient against the FastAPI app, with get_db pointed at the test DB.
    ASGITransport does not run the lifespan, so the real engine/scheduler stay idle."""
    from main import app

    Session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
