"""AH product search without an account (anonymous token), as the AH app does.

Unofficial: AH can change this at any time. Only product search is used; no
receipts or personal data are sent. Failures never block importing receipts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .matching import product_from_search

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.ah.nl"
CLIENT_ID = "appie-ios"
CLIENT_VERSION = "9.28"
HEADERS = {
    "User-Agent": f"Appie/{CLIENT_VERSION} (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)",
    "x-client-name": CLIENT_ID,
    "x-client-version": CLIENT_VERSION,
    "x-application": "AHWEBSHOP",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
TIMEOUT = aiohttp.ClientTimeout(total=15)


class AhSearchError(Exception):
    """AH search is unavailable."""


class AhSearch:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def _ensure_token(self) -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._expires:
                return self._token
            try:
                async with self._session.post(
                    f"{BASE_URL}/mobile-auth/v1/auth/token/anonymous",
                    json={"clientId": CLIENT_ID},
                    headers=HEADERS,
                    timeout=TIMEOUT,
                ) as resp:
                    if resp.status != 200:
                        raise AhSearchError(f"AH gaf status {resp.status} bij inloggen (anoniem)")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise AhSearchError(f"AH niet bereikbaar: {err}") from err
            token = data.get("access_token")
            if not token:
                raise AhSearchError("AH gaf geen token terug")
            self._token = token
            self._expires = time.monotonic() + max(60, int(data.get("expires_in") or 3600) - 60)
            return token

    async def search(self, query: str, size: int = 10) -> list[dict[str, Any]]:
        """Search AH products; returns trimmed products (id, title, brand, size, price, image)."""
        for attempt in (1, 2):
            token = await self._ensure_token()
            try:
                async with self._session.get(
                    f"{BASE_URL}/mobile-services/product/search/v2",
                    params={"query": query, "page": "0", "size": str(size), "sortOn": "RELEVANCE"},
                    headers={**HEADERS, "Authorization": f"Bearer {token}"},
                    timeout=TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        self._token = None
                        continue
                    if resp.status != 200:
                        raise AhSearchError(f"AH gaf status {resp.status} bij zoeken")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise AhSearchError(f"AH niet bereikbaar: {err}") from err
            products = data.get("products") or []
            return [product_from_search(p) for p in products if p.get("webshopId")]
        return []
