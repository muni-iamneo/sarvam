# BharatBeat

**Indic voice agent for the rural FMCG beat, plus a distribution console.**

Two integrated subsystems:

- **Voice agent** — places a live outbound **Twilio** call to a rural retailer, runs an all-8 kHz μ-law loop on **Sarvam** (Saaras v3 streaming STT with auto language detection → Sarvam‑105B dialogue with tool-calling → Bulbul v3 TTS), confirms the weekly renewal, pushes the right scheme with the exact ₹ saving, reads back the total, **writes the order to Postgres**, and updates the store's **Supermemory** profile after hangup.
- **Distribution console** — a React + Tailwind SPA (the BharatBeat design system) showing the FMCG hierarchy: regions/areas with **targets vs. achieved**, retailers with their sales rep / deputy / area manager, a retail map, stockists, brand managers, and the voice-agent console (trigger a call, watch it live, review transcript + order + post-call summary).

A retailer *is* an FMCG **outlet** in a beat → rep → distributor → area → region; a confirmed renewal call is **secondary sales** that rolls up into achievement.

## Stack

FastAPI (async, Python 3.12) · SQLAlchemy 2 + asyncpg + Postgres · Sarvam AI · Twilio Media Streams · Supermemory · React + Vite + TypeScript + Tailwind + chart.js + react-leaflet.

## Prerequisites

- Python **3.12** (Twilio has no 3.14 wheels yet; 3.12 also keeps stdlib `audioop` for μ-law)
- Node 20+ / npm, Docker (for Postgres), `ngrok` (to expose the server to Twilio)
- Accounts/keys: **Sarvam** API key, **Twilio** (a **non-Indian** voice number to call +91 handsets), **Supermemory** API key

## Quickstart

### 1. Backend + database
```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in SARVAM/TWILIO/SUPERMEMORY keys
docker compose up -d --wait db  # Postgres on :5432
.venv/bin/python -m scripts.seed  # synthetic Colgate data (72 outlets incl. Kumar Stores)
.venv/bin/python -m uvicorn main:app --reload --port 8000
```
API at http://localhost:8000 (docs at `/docs`).

### 2. Frontend
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```
The console reads the backend at `http://localhost:8000` (override with `VITE_API_BASE` / `VITE_WS_BASE`).

### 3. Place a live call
```bash
ngrok http 8000
# put the ngrok host into backend/.env, then restart uvicorn:
#   PUBLIC_URL=https://<sub>.ngrok-free.app
#   PUBLIC_WS_HOST=<sub>.ngrok-free.app
.venv/bin/python -m scripts.smoke_sarvam           # optional: verify Sarvam TTS + LLM
.venv/bin/python -m scripts.place_call --outlet-code OUT0001 --to +91XXXXXXXXXX
```
Then open the **Voice Agent** page in the console to watch the call live, or trigger it from there.

> **Twilio + India:** to call a +91 handset the `from_` number must be **non-Indian**, India **geo-permissions** must be enabled (Console → Voice → Settings → Geo Permissions), the retailer must have consented, and on a trial account the destination must be **verified** (10-min cap).

## Tests
```bash
cd backend && .venv/bin/python -m pytest -q       # backend unit + integration
cd frontend && npm run build                      # frontend type-check + build
```

## Layout
```
backend/   FastAPI app — src/{core,audio,telephony,voice,domain,tools,memory,api}, scripts/, tests/
frontend/  Vite + React + TS console — src/{pages,components,hooks,lib,styles}
```

See `docs`/the plan for the full architecture and the FMCG data model.
