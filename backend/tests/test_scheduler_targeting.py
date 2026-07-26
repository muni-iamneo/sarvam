"""Schedule targeting: repo persistence + scheduler forwarding to the dialer."""

from datetime import datetime

from sqlalchemy import select

from src.domain import models as m
from src.domain import repository as repo
from src.domain import schemas as s
from src.telephony.scheduler import CallScheduler


async def test_create_schedule_persists_targeting(db, seeded):
    payload = s.ScheduleCreate(
        name="camp", mode="now",
        items=[s.ScheduleItemIn(outlet_id=seeded["outlet_id"])],
        language="hi-IN", push_sku_id=seeded["sku_a"], push_discount_pct=25.0,
    )
    out = await repo.create_schedule(db, seeded["company_id"], payload)
    row = (await db.execute(select(m.CallSchedule).where(m.CallSchedule.id == out.id))).scalar_one()
    assert row.language == "hi-IN"
    assert row.push_sku_id == seeded["sku_a"]
    assert row.push_discount_pct == 25.0


async def test_scheduler_forwards_targeting_to_dialer(db, seeded):
    # A schedule + one queued item, both persisted to the shared test DB.
    sch = m.CallSchedule(company_id=seeded["company_id"], mode="now", status="running",
                         language="ta-IN", push_sku_id=seeded["sku_a"], push_discount_pct=30.0)
    db.add(sch)
    await db.flush()
    item = m.CallScheduleItem(schedule_id=sch.id, outlet_id=seeded["outlet_id"], position=0, status="queued")
    db.add(item)
    await db.commit()

    captured = {}

    async def fake_dial(dbi, outlet, to=None, *, language=None, push_sku_id=None, push_discount_pct=None):
        captured.update(language=language, push_sku_id=push_sku_id, push_discount_pct=push_discount_pct)
        return 999, "SIDX"

    scheduler = CallScheduler(dial=fake_dial, ready=lambda: True, now_fn=datetime.now)
    await scheduler._start_item(db, sch, item, datetime.now())

    assert captured == {"language": "ta-IN", "push_sku_id": seeded["sku_a"], "push_discount_pct": 30.0}
    assert item.status == "calling"
    assert item.call_id == 999
