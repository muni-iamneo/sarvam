"""BharatBeat FastAPI application entrypoint.

Wires the voice-agent + FMCG distribution console backend. Routers are mounted
incrementally as phases land; the DB engine is initialised in the lifespan.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.calls import router as calls_router
from src.api.dashboard import router as dashboard_router
from src.api.health import router as health_router
from src.api.schedules import router as schedules_router
from src.core.config import settings
from src.core.logging import get_logger, setup_logging
from src.telephony.scheduler import scheduler

setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (env=%s)", settings.app_name, settings.environment)
    db_ready = False
    if settings.auto_create_all:
        try:
            from src.domain.db import init_db

            await init_db()
            db_ready = True
        except Exception as exc:  # keep /health up so the DB error is visible
            logger.error("DB init failed (is Postgres up?): %s", exc)
    # Only run the batch-call worker when the DB is reachable — otherwise it
    # would just error on every tick.
    if settings.scheduler_enabled and db_ready:
        scheduler.start()
    elif settings.scheduler_enabled:
        logger.warning("Scheduler not started (database unavailable)")
    yield
    await scheduler.stop()
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(calls_router)
app.include_router(schedules_router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "docs": "/docs"}
