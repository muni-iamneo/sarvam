"""Background batch-call worker.

Drives ``call_schedules`` / ``call_schedule_items``: both **run-now** campaigns
(``mode='now'``) and **future-scheduled** batches (``mode='scheduled'`` fired once
``scheduled_at <= now``). To stay safe on a single (possibly trial) Twilio line it
places **one call at a time across all schedules** and only advances to the next
item once the current call has finished.

Completion is detected off the ``call_logs`` row: the media stream sets
``ended_at`` + a real ``outcome`` on answered calls, and the ``/twilio/status``
webhook flips ``outcome`` away from ``initiated`` for no-answer/busy/failed. A
wall-clock timeout is the backstop.

The unit of work is :meth:`CallScheduler.run_once`, which either resolves the
active call, starts the next one, or does nothing — making it directly testable
without the loop.
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from src.core.config import settings
from src.core.logging import get_logger
from src.domain import models as m
from src.domain.db import AsyncSessionLocal
from src.telephony.dialer import DialError, initiate_call, twilio_ready

logger = get_logger(__name__)

_TERMINAL_ITEM = ("done", "failed", "skipped")


def _naive(dt: datetime | None) -> datetime | None:
    """Drop tzinfo so scheduled_at (may be tz-aware from ISO input) compares
    cleanly against naive ``datetime.now()`` (matches the rest of the repo)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


class CallScheduler:
    def __init__(
        self,
        *,
        session_factory=AsyncSessionLocal,
        dial=initiate_call,
        ready=twilio_ready,
        now_fn=datetime.now,
    ) -> None:
        self._session_factory = session_factory
        self._dial = dial
        self._ready = ready
        self._now = now_fn
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="call-scheduler")
        logger.info("Call scheduler started (poll=%ss)", settings.scheduler_poll_seconds)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001 — never let the worker die
                logger.warning("scheduler tick error: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.scheduler_poll_seconds)
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------- one tick
    async def run_once(self) -> None:
        now = self._now()
        async with self._session_factory() as db:
            # 1) If a call is in flight, resolve it (or keep waiting).
            active = (
                await db.execute(
                    select(m.CallScheduleItem).where(m.CallScheduleItem.status == "calling")
                )
            ).scalars().first()
            if active is not None:
                if not await self._resolve_active(db, active, now):
                    return  # still ringing/talking — wait for the next tick

            # 2) No call in flight — start the next runnable item (at most one).
            picked = await self._next_item(db, now)
            if picked is None:
                await self._complete_finished(db, now)
                return
            schedule, item = picked
            if schedule.status == "pending":
                schedule.status = "running"
            await self._start_item(db, schedule, item, now)
            await db.commit()
            await self._complete_finished(db, now)

    async def _resolve_active(self, db, item: m.CallScheduleItem, now: datetime) -> bool:
        """Return True if the active call has finished (item advanced), else False."""
        cl = None
        if item.call_id is not None:
            cl = (
                await db.execute(select(m.CallLog).where(m.CallLog.id == item.call_id))
            ).scalar_one_or_none()
        finished = cl is not None and (cl.ended_at is not None or cl.outcome != "initiated")
        timeout = timedelta(minutes=settings.max_call_minutes + 2)
        timed_out = item.started_at is not None and (now - _naive(item.started_at)) > timeout

        if not finished and not timed_out:
            return False

        if finished and cl.outcome != "failed":
            item.status = "done"
            item.note = cl.outcome
        else:
            item.status = "failed"
            item.note = "timeout" if timed_out and not finished else (cl.outcome if cl else "no call log")
        item.ended_at = now
        await db.commit()
        return True

    async def _next_item(self, db, now: datetime):
        schedules = (
            await db.execute(
                select(m.CallSchedule)
                .where(m.CallSchedule.status.in_(("pending", "running")))
                .order_by(m.CallSchedule.created_at, m.CallSchedule.id)
            )
        ).scalars().all()
        for sch in schedules:
            runnable = sch.mode == "now" or (
                sch.scheduled_at is not None and _naive(sch.scheduled_at) <= now
            )
            if not runnable:
                continue
            item = (
                await db.execute(
                    select(m.CallScheduleItem)
                    .where(
                        m.CallScheduleItem.schedule_id == sch.id,
                        m.CallScheduleItem.status == "queued",
                    )
                    .order_by(m.CallScheduleItem.position, m.CallScheduleItem.id)
                )
            ).scalars().first()
            if item is not None:
                return sch, item
        return None

    async def _start_item(
        self, db, schedule: m.CallSchedule, item: m.CallScheduleItem, now: datetime
    ) -> None:
        outlet = (
            await db.execute(select(m.Outlet).where(m.Outlet.id == item.outlet_id))
        ).scalar_one_or_none()
        if outlet is None:
            item.status = "failed"
            item.note = "outlet not found"
            item.ended_at = now
            return
        if not self._ready():
            item.status = "failed"
            item.note = "Twilio/PUBLIC_URL not configured"
            item.ended_at = now
            return
        try:
            call_id, _sid = await self._dial(
                db, outlet, item.to_number,
                language=schedule.language,
                push_sku_id=schedule.push_sku_id,
                push_discount_pct=schedule.push_discount_pct,
            )
            item.call_id = call_id
            item.status = "calling"
            item.started_at = now
        except DialError as exc:
            item.status = "failed"
            item.note = str(exc)
            item.ended_at = now

    async def _complete_finished(self, db, now: datetime) -> None:
        schedules = (
            await db.execute(
                select(m.CallSchedule).where(m.CallSchedule.status == "running")
            )
        ).scalars().all()
        changed = False
        for sch in schedules:
            items = (
                await db.execute(
                    select(m.CallScheduleItem).where(m.CallScheduleItem.schedule_id == sch.id)
                )
            ).scalars().all()
            if items and all(it.status in _TERMINAL_ITEM for it in items):
                sch.status = "completed"
                changed = True
        if changed:
            await db.commit()


# Module-level singleton wired into the FastAPI lifespan.
scheduler = CallScheduler()
