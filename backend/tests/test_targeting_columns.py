"""CallLog round-trips the new targeting columns."""

from sqlalchemy import select

from src.domain import models as m


async def test_calllog_roundtrips_targeting(db, seeded):
    cl = m.CallLog(
        outlet_id=seeded["outlet_id"], outcome="initiated",
        initial_language="ta-IN", push_sku_id=seeded["sku_a"], push_discount_pct=15.0,
    )
    db.add(cl)
    await db.commit()
    row = (await db.execute(select(m.CallLog).where(m.CallLog.id == cl.id))).scalar_one()
    assert row.initial_language == "ta-IN"
    assert row.push_sku_id == seeded["sku_a"]
    assert row.push_discount_pct == 15.0


async def test_callschedule_roundtrips_targeting(db, seeded):
    sch = m.CallSchedule(
        company_id=seeded["company_id"], name="camp", mode="now", status="pending",
        language="hi-IN", push_sku_id=seeded["sku_b"], push_discount_pct=20.0,
    )
    db.add(sch)
    await db.commit()
    row = (await db.execute(select(m.CallSchedule).where(m.CallSchedule.id == sch.id))).scalar_one()
    assert row.language == "hi-IN"
    assert row.push_sku_id == seeded["sku_b"]
    assert row.push_discount_pct == 20.0
