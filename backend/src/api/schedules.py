"""Call-scheduling API — create/list/inspect/cancel batch call campaigns.

The background :mod:`src.telephony.scheduler` worker consumes the rows created
here; these endpoints only manage schedule state.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.dashboard import ctx
from src.domain import repository as repo
from src.domain import schemas as s

router = APIRouter(prefix="/api", tags=["schedules"])


@router.post("/schedules", response_model=s.ScheduleOut, status_code=201)
async def create_schedule(payload: s.ScheduleCreate, c=Depends(ctx)):
    db, cid, _ = c
    if payload.mode not in ("now", "scheduled"):
        raise HTTPException(status_code=400, detail="mode must be 'now' or 'scheduled'")
    if payload.mode == "scheduled" and payload.scheduled_at is None:
        raise HTTPException(status_code=400, detail="scheduled_at required when mode='scheduled'")
    if not payload.items:
        raise HTTPException(status_code=400, detail="at least one outlet is required")
    result = await repo.create_schedule(db, cid, payload)
    if result.n_items == 0:
        raise HTTPException(status_code=400, detail="no valid outlets for this company")
    return result


@router.get("/schedules", response_model=list[s.ScheduleOut])
async def list_schedules(limit: int = 50, c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_schedules(db, cid, limit=limit)


@router.get("/schedules/{schedule_id}", response_model=s.ScheduleOut)
async def get_schedule(schedule_id: int, c=Depends(ctx)):
    db, cid, _ = c
    result = await repo.get_schedule(db, cid, schedule_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return result


@router.post("/schedules/{schedule_id}/cancel", response_model=s.ScheduleOut)
async def cancel_schedule(schedule_id: int, c=Depends(ctx)):
    db, cid, _ = c
    result = await repo.cancel_schedule(db, cid, schedule_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return result
