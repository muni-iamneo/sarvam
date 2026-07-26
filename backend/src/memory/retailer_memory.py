"""Supermemory client for per-retailer relationship memory.

One container per outlet (``containerTag = outlet:{code}``). Holds the usual
basket, declined items + reasons, best call time and sentiment. All methods
degrade gracefully (return None/False) when no API key is set or on error.
"""

import re
from typing import Optional

import httpx

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def sanitize_tag(code: str) -> str:
    key = "outlet:" + re.sub(r"[^a-zA-Z0-9_:-]", "", code)
    return key[:100]


class RetailerMemoryClient:
    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None) -> None:
        self._key = api_key if api_key is not None else settings.supermemory_api_key
        self._client = httpx.AsyncClient(
            base_url=(api_url or settings.supermemory_api_url).rstrip("/"),
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            timeout=15.0,
        )

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    async def get_profile(self, outlet_code: str) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            resp = await self._client.post(
                "/v4/search",
                json={
                    "q": "usual weekly order, declined items and reasons, best call time, preferences",
                    "containerTag": sanitize_tag(outlet_code),
                    "limit": 3,
                    "threshold": 0.4,
                    "searchMode": "hybrid",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            joined = "\n".join(r.get("content", "") for r in results if r.get("content"))
            return joined or None
        except Exception as exc:
            logger.warning("Supermemory get_profile(%s) failed: %s", outlet_code, exc)
            return None

    async def store_profile(self, outlet_code: str, content: str, metadata: Optional[dict] = None) -> bool:
        if not self.enabled or not content.strip():
            return False
        try:
            resp = await self._client.post(
                "/v4/memories",
                json={
                    "containerTag": sanitize_tag(outlet_code),
                    "memories": [{"content": content, "metadata": metadata or {"type": "call_summary"}}],
                },
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Supermemory store_profile(%s) failed: %s", outlet_code, exc)
            return False

    async def close(self) -> None:
        await self._client.aclose()
