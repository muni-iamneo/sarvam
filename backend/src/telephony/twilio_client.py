"""Twilio outbound-call initiation + webhook signature validation.

NOTE: to call an Indian (+91) handset the ``from_`` number must be a
**non-Indian** voice-capable Twilio number, India geo-permissions must be
enabled, and (on trial) the destination must be verified.
"""

import asyncio

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def _client():
    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


async def start_outbound_call(to: str, call_id: int) -> str:
    """Create an outbound call whose TwiML connects to our media stream. Returns the Call SID."""

    def _create() -> str:
        call = _client().calls.create(
            to=to,
            from_=settings.twilio_from_number,
            url=f"{settings.public_url}/twilio/voice?call_id={call_id}",
            method="POST",
            status_callback=f"{settings.public_url}/twilio/status?call_id={call_id}",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            record=settings.twilio_record_calls,
            recording_channels="dual",
            # Twilio POSTs RecordingSid/RecordingUrl/RecordingDuration here once
            # the recording is ready (a few seconds after hangup).
            recording_status_callback=f"{settings.public_url}/twilio/recording?call_id={call_id}",
            recording_status_callback_event=["completed"],
        )
        return call.sid

    return await asyncio.to_thread(_create)


def validate_signature(url: str, params: dict, signature: str | None) -> bool:
    """Validate an inbound Twilio webhook via X-Twilio-Signature."""
    try:
        from twilio.request_validator import RequestValidator

        return RequestValidator(settings.twilio_auth_token).validate(url, params, signature or "")
    except Exception as exc:
        logger.warning("Twilio signature validation error: %s", exc)
        return False
