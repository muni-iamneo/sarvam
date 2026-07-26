"""Seed synthetic Colgate-themed distribution data for the BharatBeat demo.

Resets the schema (drop_all + create_all) and inserts a coherent FMCG hierarchy:
company -> regions -> areas -> territories -> beats -> outlets, the sales org
(RSM/ASM+deputy/TSO+deputy/DSR), brand managers, distributors, brands/SKUs/
schemes, and monthly targets vs achievements. Also seeds a per-retailer "usual
basket" into Supermemory (skipped gracefully if no API key).

SKU prices are tuned so the deck's demo (Kumar Stores: 3 cases Surf Excel @ 10%
off => ₹450 saved, total ₹4,050) reproduces exactly.

Run:  backend/.venv/bin/python -m scripts.seed
"""

import asyncio
import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from src.core.config import settings
from src.core.logging import get_logger, setup_logging
from src.domain import models as m
from src.domain.db import AsyncSessionLocal, Base, engine

setup_logging()
log = get_logger("seed")

NOW = datetime.now()
YEAR, MONTH = NOW.year, NOW.month
# `or` (not the get default) so a blank `DEMO_*=` line in .env falls back rather
# than seeding an empty phone (dotenv sets blank keys to ""); strip spaces/dashes
# so a formatted .env value (e.g. "+91 83444 87581") becomes valid E.164 for Twilio.
def _e164(v: str) -> str:
    return v.replace(" ", "").replace("-", "")


DEMO_RETAILER_PHONE = _e164(os.environ.get("DEMO_RETAILER_PHONE") or "+910000000000")
# The Bengaluru/Kannada hero outlet — the primary live-demo call. Defaults to the
# same verified handset as DEMO_RETAILER_PHONE so either hero can be dialled live.
DEMO_HERO_PHONE = _e164(os.environ.get("DEMO_HERO_PHONE") or DEMO_RETAILER_PHONE)

# Rough city centroids for retail-map lat/lon (deterministic jitter by index).
CITY_GEO = {
    "Bengaluru": (12.972, 77.595),
    "Salem": (11.664, 78.146),
    "Coimbatore": (11.017, 76.956),
    "Chennai": (13.083, 80.270),
    "Pune": (18.520, 73.856),
    "Delhi": (28.613, 77.209),
}

# Seeded per-city retailer language hint (Sarvam auto-detects the actual language
# on the live call; this drives the greeting + the map/console display).
CITY_LANG = {
    "Bengaluru": "kn-IN",
    "Salem": "ta-IN",
    "Coimbatore": "ta-IN",
    "Chennai": "ta-IN",
}


async def reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    log.info("Schema reset (drop_all + create_all)")


def sanitize_tag(code: str) -> str:
    return "outlet:" + "".join(ch for ch in code if ch.isalnum() or ch in "_:-")


async def seed_supermemory(outlets_basket: list[tuple[str, str]]) -> None:
    if not settings.supermemory_api_key:
        log.info("SUPERMEMORY_API_KEY not set — skipping memory seed (%d outlets)", len(outlets_basket))
        return
    async with httpx.AsyncClient(
        base_url=settings.supermemory_api_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.supermemory_api_key}"},
        timeout=15.0,
    ) as client:
        for code, content in outlets_basket:
            try:
                r = await client.post(
                    "/v4/memories",
                    json={
                        "containerTag": sanitize_tag(code),
                        "memories": [{"content": content, "metadata": {"type": "usual_basket"}}],
                    },
                )
                r.raise_for_status()
                log.info("Seeded Supermemory basket for %s", code)
            except Exception as e:  # graceful — memory is best-effort
                log.warning("Supermemory seed failed for %s: %s", code, e)


async def main() -> None:
    await reset_schema()
    async with AsyncSessionLocal() as db:
        # ---------------- Company ----------------
        company = m.Company(code=settings.default_company_code, name="Colgate-Palmolive (India) — demo", hq_city="Mumbai")
        db.add(company)
        await db.flush()
        cid = company.id

        # ---------------- Brand managers ----------------
        bms = [
            m.BrandManager(company_id=cid, name="Ananya Rao", employee_code="BM01", designation="Category"),
            m.BrandManager(company_id=cid, name="Vikram Shah", employee_code="BM02", designation="Brand"),
            m.BrandManager(company_id=cid, name="Neha Kapoor", employee_code="BM03", designation="Brand"),
        ]
        db.add_all(bms)
        await db.flush()

        # ---------------- Brands + SKUs ----------------
        # (Surf Excel / Vim included so the deck's Kumar Stores demo reproduces.)
        brand_defs = [
            ("Colgate", "COL", "Oral Care", bms[1].id),
            ("Palmolive", "PAL", "Personal Care", bms[2].id),
            ("Surf Excel", "SRF", "Home Care", bms[0].id),
            ("Vim", "VIM", "Home Care", bms[0].id),
        ]
        brands: dict[str, m.Brand] = {}
        for name, code, cat, bm_id in brand_defs:
            b = m.Brand(company_id=cid, name=name, code=code, category=cat, brand_manager_id=bm_id)
            db.add(b)
            brands[code] = b
        await db.flush()

        sku_defs = [
            # (brand_code, name, code, pack_size, unit_price_paise(per case), mrp_paise, stock, must_sell)
            ("COL", "Colgate MaxFresh Gel 100g", "COL-MF-100", "48-case", 240000, 288000, 320, True),
            ("COL", "Colgate Strong Teeth 100g", "COL-ST-100", "48-case", 200000, 240000, 260, True),
            ("PAL", "Palmolive Soap 100g", "PAL-SP-100", "72-case", 180000, 216000, 180, False),
            ("SRF", "Surf Excel Easy Wash 1kg", "SRF-EW-1K", "12-case", 150000, 180000, 210, True),
            ("VIM", "Vim Dishwash Bar 300g", "VIM-DB-300", "48-case", 60000, 72000, 140, False),
        ]
        skus: dict[str, m.Sku] = {}
        for bc, name, code, pack, up, mrp, stock, must in sku_defs:
            s = m.Sku(
                brand_id=brands[bc].id, company_id=cid, name=name, code=code, pack_size=pack,
                unit_price_paise=up, mrp_paise=mrp, unit_label="case", stock_units=stock,
                is_must_sell=must, active=True,
            )
            db.add(s)
            skus[code] = s
        await db.flush()

        # ---------------- Schemes ----------------
        today = NOW.date()
        db.add_all([
            m.Scheme(sku_id=skus["SRF-EW-1K"].id, description="10% off on 3+ cases", kind="pct",
                     min_qty=3, discount_pct=10.0, valid_from=today - timedelta(days=10),
                     valid_to=today + timedelta(days=20), active=True),
            m.Scheme(sku_id=skus["COL-MF-100"].id, description="5% off on 2+ cases", kind="pct",
                     min_qty=2, discount_pct=5.0, valid_from=today - timedelta(days=5),
                     valid_to=today + timedelta(days=25), active=True),
            m.Scheme(sku_id=skus["VIM-DB-300"].id, description="₹40 off per case on 2+ cases", kind="flat",
                     min_qty=2, flat_off_paise=4000, valid_from=today - timedelta(days=5),
                     valid_to=today + timedelta(days=25), active=True),
        ])

        # ---------------- Geography + org ----------------
        # region -> areas(city) -> territories -> beats ; reps attached as we go.
        region_plan = {
            "South": {"zone": "South", "areas": ["Bengaluru", "Salem", "Coimbatore", "Chennai"]},
            "West": {"zone": "West", "areas": ["Pune"]},
            "North": {"zone": "North", "areas": ["Delhi"]},
        }
        basket_seed: list[tuple[str, str]] = []
        outlet_counter = 0
        rep_counter = 0

        def next_emp() -> str:
            nonlocal rep_counter
            rep_counter += 1
            return f"E{rep_counter:03d}"

        for r_idx, (rname, rmeta) in enumerate(region_plan.items(), start=1):
            region = m.Region(company_id=cid, name=f"{rname} Region", code=f"R{r_idx}", zone=rmeta["zone"])
            db.add(region)
            await db.flush()
            rsm = m.SalesRep(company_id=cid, name=f"{rname} RSM", employee_code=next_emp(),
                             designation="RSM", region_id=region.id, phone="+919000000000")
            db.add(rsm)
            await db.flush()
            region.regional_manager_id = rsm.id

            for a_idx, city in enumerate(rmeta["areas"], start=1):
                area = m.Area(region_id=region.id, name=f"{city}", code=f"A{r_idx}{a_idx}")
                db.add(area)
                await db.flush()
                asm = m.SalesRep(company_id=cid, name=f"{city} ASM", employee_code=next_emp(),
                                 designation="ASM", reporting_manager_id=rsm.id, area_id=area.id)
                db.add(asm)
                await db.flush()  # need asm.id before the deputy can report to it
                dep_asm = m.SalesRep(company_id=cid, name=f"{city} Dy. ASM", employee_code=next_emp(),
                                     designation="DeputyASM", reporting_manager_id=asm.id, area_id=area.id)
                db.add(dep_asm)
                await db.flush()
                area.area_manager_id = asm.id
                area.deputy_area_manager_id = dep_asm.id

                base_lat, base_lon = CITY_GEO.get(city, (20.0, 78.0))
                n_terr = 2 if city in ("Bengaluru", "Salem", "Coimbatore", "Chennai") else 1
                for t_idx in range(1, n_terr + 1):
                    terr = m.Territory(area_id=area.id, name=f"{city} T{t_idx}", code=f"T{r_idx}{a_idx}{t_idx}")
                    db.add(terr)
                    await db.flush()
                    tso = m.SalesRep(company_id=cid, name=f"{city} TSO {t_idx}", employee_code=next_emp(),
                                     designation="TSO", reporting_manager_id=asm.id, area_id=area.id,
                                     territory_id=terr.id)
                    db.add(tso)
                    await db.flush()
                    terr.tso_id = tso.id

                    dist = m.Distributor(company_id=cid, name=f"{city} Distributors {t_idx}",
                                         code=f"D{r_idx}{a_idx}{t_idx}", stockist_type="Distributor",
                                         territory_id=terr.id, contact_person=f"{city} Stockist",
                                         phone="+918000000000", warehouse_lat=base_lat, warehouse_lon=base_lon,
                                         credit_limit_paise=5_000_000, margin_pct=8.0)
                    db.add(dist)
                    await db.flush()
                    terr.distributor_id = dist.id

                    n_beats = 2
                    for b_idx in range(1, n_beats + 1):
                        beat = m.Beat(territory_id=terr.id, name=f"{city} Beat {t_idx}.{b_idx}",
                                      code=f"B{r_idx}{a_idx}{t_idx}{b_idx}", visit_frequency_days=7,
                                      day_of_week=["Mon", "Wed", "Fri"][b_idx % 3])
                        db.add(beat)
                        await db.flush()
                        dsr = m.SalesRep(company_id=cid, name=f"{city} DSR {t_idx}.{b_idx}",
                                         employee_code=next_emp(), designation="DSR",
                                         reporting_manager_id=tso.id, territory_id=terr.id)
                        db.add(dsr)
                        await db.flush()
                        beat.sales_rep_id = dsr.id

                        n_outlets = 6 if city in ("Bengaluru", "Salem") else 4
                        for o_idx in range(1, n_outlets + 1):
                            outlet_counter += 1
                            is_kumar = city == "Salem" and t_idx == 1 and b_idx == 1 and o_idx == 1
                            is_hero = city == "Bengaluru" and t_idx == 1 and b_idx == 1 and o_idx == 1
                            if is_hero:
                                name = "Sri Lakshmi Stores"
                            elif is_kumar:
                                name = "Kumar Stores"
                            else:
                                name = f"{city} Store {outlet_counter}"
                            code = f"OUT{outlet_counter:04d}"
                            cls = "A" if (is_hero or is_kumar) else ["A", "B", "C", "D"][o_idx % 4]
                            trade = "MT" if (o_idx == 1 and city == "Chennai") else "GT"
                            lat = base_lat + ((outlet_counter % 10) - 5) * 0.004
                            lon = base_lon + ((outlet_counter % 7) - 3) * 0.004
                            if is_hero:
                                phone = DEMO_HERO_PHONE
                            elif is_kumar:
                                phone = DEMO_RETAILER_PHONE
                            else:
                                phone = "+910000000001"
                            outlet = m.Outlet(
                                company_id=cid, name=name, code=code,
                                phone=phone,
                                language=CITY_LANG.get(city, "hi-IN"),
                                owner_name="Ramesh" if is_hero else ("Kumar" if is_kumar else None),
                                beat_id=beat.id, distributor_id=dist.id, territory_id=terr.id,
                                area_id=area.id, region_id=region.id,
                                address=f"{name}, {city}", lat=lat, lon=lon,
                                outlet_class=cls, trade_type=trade,
                                category="Kirana" if trade == "GT" else "Supermarket",
                                best_call_time="Morning", status="active",
                            )
                            db.add(outlet)
                            if is_hero:
                                basket_seed.append((
                                    code,
                                    "Sri Lakshmi Stores (Bengaluru) usual weekly order: Surf Excel Easy Wash 3 cases, "
                                    "Vim Dishwash 2 cases. Prefers morning calls (before 11am). Regular on the "
                                    "Surf Excel 10%-off-3-cases scheme. Speaks Kannada / code-mix.",
                                ))
                            if is_kumar:
                                basket_seed.append((
                                    code,
                                    "Kumar Stores (Salem) usual weekly order: Surf Excel Easy Wash 2 cases, "
                                    "Vim Dishwash 1 case. Prefers morning calls (before 11am). Last month "
                                    "declined extra Vim once (overstocked). Speaks Tamil / code-mix.",
                                ))
        await db.flush()

        # ---------------- Targets + achievements (current month, Secondary) ----------------
        regions = (await db.execute(select(m.Region).where(m.Region.company_id == cid))).scalars().all()
        areas = (await db.execute(select(m.Area))).scalars().all()
        for i, region in enumerate(regions):
            target = 50_00_000 + i * 15_00_000  # ₹50L, 65L, 80L in paise-ish scale (already paise-large)
            db.add(m.SalesTarget(company_id=cid, year=YEAR, month=MONTH, target_type="Secondary",
                                 region_id=region.id, target_amount_paise=target))
            db.add(m.SalesAchievement(company_id=cid, year=YEAR, month=MONTH, sales_type="Secondary",
                                      region_id=region.id, achieved_amount_paise=int(target * (0.72 + 0.06 * i))))
        for i, area in enumerate(areas):
            target = 12_00_000 + (i % 4) * 3_00_000
            db.add(m.SalesTarget(company_id=cid, year=YEAR, month=MONTH, target_type="Secondary",
                                 area_id=area.id, target_amount_paise=target))
            db.add(m.SalesAchievement(company_id=cid, year=YEAR, month=MONTH, sales_type="Secondary",
                                      area_id=area.id, achieved_amount_paise=int(target * (0.65 + 0.07 * (i % 5)))))

        await db.commit()
        counts = {
            "regions": len(regions), "areas": len(areas),
            "outlets": outlet_counter, "reps": rep_counter,
            "skus": len(skus), "brands": len(brands),
        }
        log.info("Seed committed: %s", counts)

    await seed_supermemory(basket_seed)
    await engine.dispose()
    log.info("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
