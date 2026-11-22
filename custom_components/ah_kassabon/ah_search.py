"""Talk to the AH app's API: anonymous product search, and optionally the account.

Unofficial: AH can change this at any time. Without a login only product
search is used and no personal data is sent. With a login (optional, set up
under Configure) the account's own receipts are read. Failures never block
importing receipts by hand.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

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
TIMEOUT = aiohttp.ClientTimeout(total=30)
LOGIN_URL = "https://login.ah.nl/login?" + urlencode(
    {"client_id": CLIENT_ID, "response_type": "code", "redirect_uri": "appie://login-exit"}
)


class AhSearchError(Exception):
    """AH search is unavailable."""


class AhAuthError(AhSearchError):
    """The AH login is missing, expired or was refused."""


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

    async def products_by_ids(self, ids: list[int]) -> dict[int, dict[str, Any]]:
        """Look up webshop products by id; returns {id: trimmed product}."""
        out: dict[int, dict[str, Any]] = {}
        for start in range(0, len(ids), 30):
            chunk = ids[start : start + 30]
            params = [("ids", str(i)) for i in chunk] + [("sortOn", "INPUT_PRODUCT_IDS")]
            for attempt in (1, 2):
                token = await self._ensure_token()
                try:
                    async with self._session.get(
                        f"{BASE_URL}/mobile-services/product/search/v2/products",
                        params=params,
                        headers={**HEADERS, "Authorization": f"Bearer {token}"},
                        timeout=TIMEOUT,
                    ) as resp:
                        if resp.status == 401 and attempt == 1:
                            self._token = None
                            continue
                        if resp.status != 200:
                            raise AhSearchError(f"AH gaf status {resp.status} bij producten ophalen")
                        data = await resp.json(content_type=None)
                except (aiohttp.ClientError, TimeoutError) as err:
                    raise AhSearchError(f"AH niet bereikbaar: {err}") from err
                rows = data if isinstance(data, list) else data.get("products") or []
                for raw in rows:
                    if raw.get("webshopId"):
                        out[int(raw["webshopId"])] = product_from_search(raw)
                break
        return out


def code_from_input(text: str) -> str:
    """Accept the bare code or the whole appie://login-exit?code=... link."""
    text = text.strip()
    if "code=" in text:
        query = urlparse(text).query or text.split("?", 1)[-1]
        codes = parse_qs(query).get("code")
        if codes:
            return codes[0].strip()
    return text


def _tokens(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "member_id": data.get("member_id"),
        "expires_at": time.time() + max(60, int(data.get("expires_in") or 3600) - 60),
    }


async def async_exchange_code(session: aiohttp.ClientSession, code: str) -> dict[str, Any]:
    """Trade the code from the AH login page for account tokens."""
    try:
        async with session.post(
            f"{BASE_URL}/mobile-auth/v1/auth/token",
            json={"clientId": CLIENT_ID, "code": code},
            headers=HEADERS,
            timeout=TIMEOUT,
        ) as resp:
            if resp.status in (400, 401, 403):
                _LOGGER.warning(
                    "AH weigerde de inlogcode: status %s, antwoord: %s", resp.status, (await resp.text())[:300]
                )
                raise AhAuthError("AH accepteerde de code niet (verlopen of al gebruikt?)")
            if resp.status != 200:
                raise AhSearchError(f"AH gaf status {resp.status} bij inloggen")
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise AhSearchError(f"AH niet bereikbaar: {err}") from err
    if not data.get("access_token"):
        raise AhAuthError("AH gaf geen token terug")
    return _tokens(data)


RECEIPTS_QUERY = """query FetchPosReceipts($offset: Int!, $limit: Int!) {
  posReceiptsPage(pagination: {offset: $offset, limit: $limit}) {
    posReceipts { id dateTime totalAmount { amount } }
  }
}"""

RECEIPT_QUERY = """query FetchReceipt($id: String!) {
  posReceiptDetails(id: $id) {
    id
    products { id quantity name price { amount } amount { amount } }
  }
}"""

RECEIPT_PDF_QUERY = """query FetchPosReceiptPdf($id: String!) {
  posReceiptPdf(id: $id) { pdfBase64 }
}"""


class AhAccount:
    """The household's AH account (logged in once via Configure)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        tokens: dict[str, Any],
        on_tokens: Callable[[dict[str, Any]], None],
    ) -> None:
        self._session = session
        self._tokens = dict(tokens)
        self._on_tokens = on_tokens
        self._lock = asyncio.Lock()

    async def _access_token(self, force_refresh: bool = False) -> str:
        async with self._lock:
            if not force_refresh and time.time() < self._tokens.get("expires_at", 0):
                return self._tokens["access_token"]
            refresh = self._tokens.get("refresh_token")
            if not refresh:
                raise AhAuthError("AH-login verlopen, log opnieuw in")
            try:
                async with self._session.post(
                    f"{BASE_URL}/mobile-auth/v1/auth/token/refresh",
                    json={"clientId": CLIENT_ID, "refreshToken": refresh},
                    headers=HEADERS,
                    timeout=TIMEOUT,
                ) as resp:
                    if resp.status in (400, 401, 403):
                        raise AhAuthError("AH-login verlopen, log opnieuw in")
                    if resp.status != 200:
                        raise AhSearchError(f"AH gaf status {resp.status} bij vernieuwen login")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise AhSearchError(f"AH niet bereikbaar: {err}") from err
            if not data.get("access_token"):
                raise AhAuthError("AH-login verlopen, log opnieuw in")
            new = _tokens(data)
            new["refresh_token"] = new["refresh_token"] or refresh
            new["member_id"] = new["member_id"] or self._tokens.get("member_id")
            self._tokens = new
            self._on_tokens(new)
            return new["access_token"]

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in (1, 2):
            token = await self._access_token(force_refresh=attempt == 2)
            try:
                async with self._session.post(
                    f"{BASE_URL}/graphql",
                    json={"query": query, "variables": variables or {}},
                    headers={**HEADERS, "Authorization": f"Bearer {token}"},
                    timeout=TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        continue
                    if resp.status == 401:
                        raise AhAuthError("AH-login verlopen, log opnieuw in")
                    if resp.status != 200:
                        raise AhSearchError(f"AH gaf status {resp.status}")
                    body = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise AhSearchError(f"AH niet bereikbaar: {err}") from err
            if body.get("errors"):
                raise AhSearchError(f"AH: {body['errors'][0].get('message')}")
            return body.get("data") or {}
        raise AhAuthError("AH-login verlopen, log opnieuw in")

    async def receipts(self, offset: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """Receipts in the account, newest first: [{id, when, total}]."""
        data = await self.graphql(RECEIPTS_QUERY, {"offset": offset, "limit": limit})
        rows = ((data.get("posReceiptsPage") or {}).get("posReceipts")) or []
        return [
            {"id": r["id"], "when": r.get("dateTime"), "total": (r.get("totalAmount") or {}).get("amount")}
            for r in rows
            if r.get("id")
        ]

    async def receipt_products(self, receipt_id: str) -> list[dict[str, Any]]:
        """Lines of one receipt with AH's product id: [{name, price, amount, pos_id}]."""
        data = await self.graphql(RECEIPT_QUERY, {"id": receipt_id})
        lines = ((data.get("posReceiptDetails") or {}).get("products")) or []
        return [
            {
                "name": line.get("name") or "",
                "qty": line.get("quantity"),
                "price": (line.get("price") or {}).get("amount"),
                "amount": (line.get("amount") or {}).get("amount"),
                "pos_id": line.get("id"),
            }
            for line in lines
        ]

    async def receipt_pdf(self, receipt_id: str) -> bytes:
        data = await self.graphql(RECEIPT_PDF_QUERY, {"id": receipt_id})
        pdf = (data.get("posReceiptPdf") or {}).get("pdfBase64")
        if not pdf:
            raise AhSearchError("AH gaf geen PDF voor deze bon")
        return base64.b64decode(pdf)

    async def webshop_ids(self, pos_ids: list[int]) -> dict[int, int]:
        """Map receipt product ids to webshop product ids (one request)."""
        unique = sorted({int(i) for i in pos_ids if isinstance(i, int) and i > 0})
        if not unique:
            return {}
        # Aliases must be literal; the ids are integers from AH itself.
        query = "query Convert {" + "".join(
            f" p{n}: productConvertId(sourceId: {i})" for n, i in enumerate(unique)
        ) + " }"
        data = await self.graphql(query)
        out = {}
        for n, i in enumerate(unique):
            value = data.get(f"p{n}")
            if isinstance(value, int) and value > 0:
                out[i] = value
        return out
