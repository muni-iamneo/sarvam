"""Health + readiness endpoints."""

from fastapi import APIRouter

from src.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}
