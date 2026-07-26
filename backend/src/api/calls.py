"""Telephony + live-call API: outbound trigger, Twilio webhooks, media & live WS."""

import asyncio

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dashboard import ctx
from src.core.config import settings
from src.core.logging import get_logger
from src.domain import models as m
from src.domain import repository as repo
from src.domain import schemas as s
from src.domain.db import get_db
from src.telephony.dialer import DialError, initiate_call
from src.telephony.media_stream import LiveHub, run_media_stream
from src.telephony.twiml import build_stream_twiml
from src.telephony.twilio_client import validate_signature

logger = get_logger(__name__)
router = APIRouter(tags=["calls"])
hub = LiveHub()


class StartCallReq(BaseModel):
    outlet_id: int
    to: str | None = None


async def _require_twilio_signature(request: Request, form) -> None:
    """Reject forged Twilio webhook POSTs. Twilio signs over the exact public URL
    it called (built from settings.public_url) + the POST params — so we must
    reconstruct that URL rather than trust request.url (uvicorn sees the proxied
    localhost host behind ngrok). Gated by settings.twilio_validate_signature;
    set TWILIO_VALIDATE_SIGNATURE=false to disable if a URL mismatch ever 403s a
    legitimate callback."""
    if not (settings.twilio_validate_signature and settings.twilio_auth_token and settings.public_url):
        return
    url = settings.public_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    ok = validate_signature(url, {k: v for k, v in form.items()}, request.headers.get("X-Twilio-Signature"))
    if not ok:
        logger.warning("Twilio signature validation FAILED for %s (reconstructed url=%s)", request.url.path, url)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@router.post("/calls")
async def start_call(req: StartCallReq, db: AsyncSession = Depends(get_db)):
    outlet = (
        await db.execute(select(m.Outlet).where(m.Outlet.id == req.outlet_id))
    ).scalar_one_or_none()
    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")
    try:
        call_id, sid = await initiate_call(db, outlet, req.to)
    except DialError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    to = req.to or outlet.phone
    return {"call_id": call_id, "twilio_call_sid": sid, "to": to, "live_ws": f"/calls/{call_id}/live"}


@router.api_route("/twilio/voice", methods=["GET", "POST"])
async def twilio_voice(request: Request, call_id: int):
    if settings.twilio_validate_signature and settings.twilio_auth_token:
        if not request.headers.get("X-Twilio-Signature"):
            logger.warning("Missing X-Twilio-Signature on %s", request.url.path)
    ws_host = settings.public_ws_host or (request.url.hostname or "")
    twiml = build_stream_twiml(call_id, ws_host)
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    await _require_twilio_signature(request, form)
    status = form.get("CallStatus")
    cl = (await db.execute(select(m.CallLog).where(m.CallLog.id == call_id))).scalar_one_or_none()
    if cl and status in ("no-answer", "busy", "failed", "canceled") and cl.outcome == "initiated":
        cl.outcome = "no_answer"
        await db.commit()
    await hub.publish(str(call_id), {"type": "call_status", "status": status})
    return Response(status_code=204)


@router.post("/twilio/recording")
async def twilio_recording(request: Request, call_id: int, db: AsyncSession = Depends(get_db)):
    """Twilio POSTs here once a call recording is ready — persist its SID/URL."""
    form = await request.form()
    await _require_twilio_signature(request, form)
    cl = (await db.execute(select(m.CallLog).where(m.CallLog.id == call_id))).scalar_one_or_none()
    if cl:
        cl.recording_sid = form.get("RecordingSid") or cl.recording_sid
        cl.recording_url = form.get("RecordingUrl") or cl.recording_url
        cl.recording_status = form.get("RecordingStatus") or cl.recording_status
        dur = form.get("RecordingDuration")
        if dur and str(dur).isdigit():
            cl.recording_duration_s = int(dur)
        await db.commit()
        await hub.publish(str(call_id), {"type": "recording_ready", "recording_sid": cl.recording_sid})
    return Response(status_code=204)


@router.websocket("/twilio/media")
async def twilio_media(ws: WebSocket):
    await run_media_stream(ws, hub)


@router.websocket("/calls/{call_id}/live")
async def calls_live(ws: WebSocket, call_id: str):
    await ws.accept()
    for event in hub.history(call_id):
        await ws.send_json(event)
    hub.subscribe(call_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(call_id, ws)


@router.get("/api/calls", response_model=list[s.CallLogOut])
async def api_calls(limit: int = 50, c=Depends(ctx)):
    db, cid, _ = c
    return await repo.list_calls(db, cid, limit=limit)


@router.get("/api/calls/{call_id}", response_model=s.CallDetailOut)
async def api_call_detail(call_id: int, c=Depends(ctx)):
    db, cid, _ = c
    detail = await repo.get_call(db, cid, call_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Call not found")
    return detail


async def _resolve_recording_sid(cl: m.CallLog, db: AsyncSession) -> str | None:
    """Recording SID from the stored value, else a lazy Twilio lookup by Call SID
    (covers a delayed/missed recordingStatusCallback). Persists what it finds."""
    if cl.recording_sid:
        return cl.recording_sid
    if not cl.twilio_call_sid:
        return None

    def _list() -> str | None:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        recs = client.recordings.list(call_sid=cl.twilio_call_sid, limit=1)
        return recs[0].sid if recs else None

    try:
        sid = await asyncio.to_thread(_list)
    except Exception as exc:  # noqa: BLE001
        logger.warning("recording lookup failed for call %s: %s", cl.id, exc)
        return None
    if sid:
        cl.recording_sid = sid
        await db.commit()
    return sid


@router.get("/api/calls/{call_id}/recording")
async def api_call_recording(call_id: int, request: Request, c=Depends(ctx)):
    """Stream the Twilio call recording, proxying Twilio's Basic-auth media so the
    account credentials never reach the browser. Tenant-scoped; supports Range."""
    db, cid, _ = c
    cl = (await db.execute(select(m.CallLog).where(m.CallLog.id == call_id))).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Call not found")
    outlet = (
        await db.execute(select(m.Outlet).where(m.Outlet.id == cl.outlet_id))
    ).scalar_one_or_none()
    if not outlet or outlet.company_id != cid:
        raise HTTPException(status_code=404, detail="Call not found")
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        raise HTTPException(status_code=503, detail="Twilio not configured")

    sid = await _resolve_recording_sid(cl, db)
    if not sid:
        raise HTTPException(status_code=404, detail="Recording not available yet")

    media_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        f"/Recordings/{sid}.mp3"
    )
    fwd_headers = {}
    if request.headers.get("range"):
        fwd_headers["Range"] = request.headers["range"]

    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=None))
    req = client.build_request("GET", media_url, headers=fwd_headers)
    upstream = await client.send(
        req, stream=True,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
    )
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=404, detail="Recording not available yet")

    passthrough = {"content-type": upstream.headers.get("content-type", "audio/mpeg"),
                   "accept-ranges": "bytes"}
    for h in ("content-length", "content-range"):
        if h in upstream.headers:
            passthrough[h] = upstream.headers[h]

    async def body_iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(body_iter(), status_code=upstream.status_code, headers=passthrough)
