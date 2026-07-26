"""Shared outbound-call initiation used by both the ad-hoc `POST /calls`
endpoint and the batch scheduler.

Creates the ``call_logs`` row, places the Twilio call, and records the Call SID.
Raises ``DialError`` (with an HTTP-ish ``status`` hint) on any failure so callers
can surface a precise reason.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domain import models as m
from src.telephony.twilio_client import start_outbound_call


class DialError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def twilio_ready() -> bool:
    return bool(
        settings.twilio_account_sid and settings.twilio_from_number and settings.public_url
    )


async def initiate_call(db: AsyncSession, outlet: m.Outlet, to: str | None = None) -> tuple[int, str]:
    """Place an outbound call to ``outlet`` (or an override ``to`` number).

    Returns ``(call_id, twilio_call_sid)``. Persists a ``call_logs`` row first so
    the id is available for the TwiML/media-stream wiring and the live view.
    """
    dest = to or outlet.phone
    if not dest:
        raise DialError("No destination phone number", status=400)
    if not twilio_ready():
        raise DialError("Twilio/PUBLIC_URL not configured (see .env)", status=503)

    cl = m.CallLog(outlet_id=outlet.id, outcome="initiated")
    db.add(cl)
    await db.commit()
    try:
        sid = await start_outbound_call(dest, cl.id)
        cl.twilio_call_sid = sid
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — surface the reason to the caller
        cl.outcome = "failed"
        await db.commit()
        raise DialError(f"Twilio call failed: {exc}", status=502)
    return cl.id, sid
