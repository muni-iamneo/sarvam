"""Preflight the Twilio setup before a live BharatBeat demo call.

Catches the four things that silently break an India (+91) outbound call:
  1. Credentials / config present (TWILIO_*, PUBLIC_URL, PUBLIC_WS_HOST).
  2. The Twilio auth actually works, and whether the account is on Trial.
  3. TWILIO_FROM_NUMBER is a number you own, is voice-capable, and is
     NON-Indian (a +91 caller ID cannot dial +91 handsets).
  4. India geo-permissions are enabled, and — on Trial — the destination
     handset(s) are Verified Caller IDs (Trial only connects to verified numbers).

Reads config from backend/.env (via settings) + DEMO_HERO_PHONE /
DEMO_RETAILER_PHONE from the environment. Nothing is dialed — read-only checks.

Run:
  backend/.venv/bin/python -m scripts.twilio_preflight
  backend/.venv/bin/python -m scripts.twilio_preflight --to +91XXXXXXXXXX
"""

import argparse
import os
import sys

import httpx

from src.core.config import settings

# ANSI marks (fall back to ASCII if not a TTY)
_TTY = sys.stdout.isatty()
OK = "\033[32m✓\033[0m" if _TTY else "[ OK ]"
WARN = "\033[33m⚠\033[0m" if _TTY else "[WARN]"
ERR = "\033[31m✗\033[0m" if _TTY else "[FAIL]"

_errors = 0
_warns = 0


def ok(msg: str) -> None:
    print(f"  {OK} {msg}")


def warn(msg: str) -> None:
    global _warns
    _warns += 1
    print(f"  {WARN} {msg}")


def fail(msg: str) -> None:
    global _errors
    _errors += 1
    print(f"  {ERR} {msg}")


def _norm(num: str | None) -> str:
    return (num or "").replace(" ", "").replace("-", "").strip()


def check_config() -> bool:
    """Required env/config. Returns False if we can't even build a Twilio client."""
    print("\nConfiguration (backend/.env)")
    sid = settings.twilio_account_sid
    token = settings.twilio_auth_token
    from_ = _norm(settings.twilio_from_number)

    have_creds = bool(sid and token)
    if have_creds:
        ok(f"TWILIO_ACCOUNT_SID / AUTH_TOKEN set (SID {sid[:6]}…)")
    else:
        fail("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN missing")

    if from_:
        ok(f"TWILIO_FROM_NUMBER = {from_}")
    else:
        fail("TWILIO_FROM_NUMBER missing (needs a non-Indian voice number)")

    if settings.public_url.startswith("https://"):
        ok(f"PUBLIC_URL = {settings.public_url}")
    else:
        fail(f"PUBLIC_URL must be an https URL (got '{settings.public_url or 'empty'}') — run ngrok")

    if settings.public_ws_host and "://" not in settings.public_ws_host:
        ok(f"PUBLIC_WS_HOST = {settings.public_ws_host}")
    else:
        fail(
            "PUBLIC_WS_HOST must be a bare host (no scheme), e.g. abc.ngrok-free.app "
            f"(got '{settings.public_ws_host or 'empty'}')"
        )

    return have_creds and bool(from_)


def check_public_url() -> None:
    """Best-effort: is the ngrok tunnel actually reachable right now?"""
    if not settings.public_url.startswith("https://"):
        return
    print("\nPublic tunnel reachability")
    try:
        r = httpx.get(settings.public_url.rstrip("/") + "/health", timeout=6.0)
        if r.status_code < 500:
            ok(f"{settings.public_url}/health responded ({r.status_code})")
        else:
            warn(f"/health returned {r.status_code} — is the backend running?")
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not reach {settings.public_url} ({type(exc).__name__}) — start ngrok + uvicorn")


def check_twilio(destinations: list[str]) -> None:
    print("\nTwilio account")
    try:
        from twilio.base.exceptions import TwilioRestException
        from twilio.rest import Client
    except ImportError:
        fail("twilio SDK not installed in this venv")
        return

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    # 1) Auth + trial status
    try:
        acct = client.api.accounts(settings.twilio_account_sid).fetch()
    except TwilioRestException as exc:
        fail(f"Auth failed ({exc.status} {exc.code}): check SID/token")
        return
    except Exception as exc:  # noqa: BLE001
        fail(f"Could not reach Twilio API ({type(exc).__name__})")
        return

    is_trial = (acct.type or "").lower() == "trial"
    ok(f"Authenticated — account '{acct.friendly_name}' ({acct.type}, status={acct.status})")
    if is_trial:
        warn("Trial account — calls only connect to VERIFIED destinations (checked below)")

    from_ = _norm(settings.twilio_from_number)

    # 2) from_ number: owned + voice-capable + non-Indian
    print("\nCaller ID (from_ number)")
    if from_.startswith("+91"):
        fail(f"{from_} is an Indian (+91) number — cannot be used to call +91 handsets")
    else:
        ok(f"{from_} is non-Indian — valid caller ID for +91 destinations")

    try:
        owned = client.incoming_phone_numbers.list(phone_number=from_, limit=20)
        match = next((n for n in owned if _norm(n.phone_number) == from_), None)
        if not match:
            # list(phone_number=...) is a filter; fall back to scanning all
            match = next(
                (n for n in client.incoming_phone_numbers.list(limit=100) if _norm(n.phone_number) == from_),
                None,
            )
        if not match:
            fail(f"{from_} is not owned by this account — buy it or fix TWILIO_FROM_NUMBER")
        elif not getattr(match.capabilities, "get", lambda *_: None)("voice"):
            fail(f"{from_} is not voice-capable")
        else:
            ok(f"{from_} is owned and voice-capable")
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not verify number ownership ({type(exc).__name__})")

    # 3) India geo-permissions
    print("\nGeo permissions (India / +91)")
    try:
        india = client.voice.v1.dialing_permissions.countries("IN").fetch()
        if getattr(india, "low_risk_numbers_enabled", False):
            ok("India low-risk dialing is ENABLED")
        else:
            fail(
                "India dialing is DISABLED — enable it at "
                "Console → Voice → Settings → Geo Permissions"
            )
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not read dialing permissions ({type(exc).__name__}) — check Geo Permissions manually")

    # 4) Destination verification (Trial only)
    print("\nDestination handset(s)")
    if not destinations:
        warn("No destination given (--to / DEMO_HERO_PHONE / DEMO_RETAILER_PHONE) — skipping verify check")
        return
    for d in destinations:
        if not d.startswith("+91"):
            warn(f"{d} is not a +91 number — sure this is the India demo handset?")
    if not is_trial:
        ok("Full account — any destination is callable (no verification needed)")
        return
    try:
        verified = {_norm(v.phone_number) for v in client.outgoing_caller_ids.list(limit=100)}
        for d in destinations:
            if d in verified:
                ok(f"{d} is a Verified Caller ID")
            else:
                fail(
                    f"{d} is NOT verified — add it at Console → Phone Numbers → "
                    "Verified Caller IDs (Trial won't connect otherwise)"
                )
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not list Verified Caller IDs ({type(exc).__name__})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preflight Twilio for a live BharatBeat call.")
    ap.add_argument(
        "--to",
        action="append",
        default=[],
        help="Destination handset to check (E.164, e.g. +91...). Repeatable. "
        "Defaults to DEMO_HERO_PHONE + DEMO_RETAILER_PHONE from the env.",
    )
    args = ap.parse_args()

    destinations = [_norm(d) for d in args.to] or [
        _norm(p)
        for p in (os.environ.get("DEMO_HERO_PHONE"), os.environ.get("DEMO_RETAILER_PHONE"))
        if p
    ]
    # de-dup, preserve order
    seen: set[str] = set()
    destinations = [d for d in destinations if d and not (d in seen or seen.add(d))]

    print("BharatBeat — Twilio preflight")
    print("=" * 40)

    can_call_api = check_config()
    check_public_url()
    if can_call_api:
        check_twilio(destinations)
    else:
        print("\nSkipping Twilio API checks — fix the config above first.")

    print("\n" + "=" * 40)
    if _errors:
        print(f"{ERR} {_errors} blocker(s), {_warns} warning(s) — fix blockers before the live call.")
        sys.exit(1)
    if _warns:
        print(f"{WARN} 0 blockers, {_warns} warning(s) — likely fine, review the warnings above.")
    else:
        print(f"{OK} All checks passed — you're clear to place the live call.")


if __name__ == "__main__":
    main()
