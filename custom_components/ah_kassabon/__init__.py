"""AH Kassabon: read Albert Heijn receipts and track price changes."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from . import prices
from .const import (
    CARD_URL,
    DOMAIN,
    EVENT_IMPORTED,
    SIGNAL_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPLOAD_URL,
)
from .parser import Receipt, ReceiptParseError, parse_pdf

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


class KassabonData:
    """Holds the stored receipts and handles imports."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {"receipts": {}, "overrides": {}}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.data = {"receipts": {}, "overrides": {}, **stored}

    async def _async_save(self) -> None:
        await self._store.async_save(self.data)
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    async def async_import_pdf(self, data: bytes, filename: str | None = None) -> dict[str, Any]:
        """Parse a receipt PDF, store it and compare its prices."""
        try:
            receipt: Receipt = await self.hass.async_add_executor_job(parse_pdf, data)
        except ReceiptParseError as err:
            return {"ok": False, "file": filename, "error": str(err)}
        async with self._lock:
            rid = receipt.receipt_id
            duplicate = rid in self.data["receipts"]
            if not duplicate:
                self.data["receipts"][rid] = {
                    "when": receipt.when.isoformat(),
                    "store": receipt.store,
                    "total": receipt.total,
                    "imported": dt_util.utcnow().isoformat(),
                    "items": [
                        {"name": i.name, "qty": i.qty, "unit": i.unit, "bonus": i.bonus, "per_kg": i.per_kg}
                        for i in receipt.items
                    ],
                }
                await self._async_save()
            result = prices.compare_receipt(self.data, rid)
        result.update(
            {
                "ok": True,
                "file": filename,
                "duplicate": duplicate,
                "missing_items": receipt.missing_items,
            }
        )
        if receipt.missing_items:
            _LOGGER.warning(
                "Kassabon %s: %s product(en) niet herkend; stuur de PDF mee in een issue",
                rid,
                receipt.missing_items,
            )
        if not duplicate:
            self.hass.bus.async_fire(EVENT_IMPORTED, result)
        return result

    async def async_set_variable(self, product: str, variable: bool | None) -> None:
        async with self._lock:
            product = product.upper()
            if variable is None:
                self.data["overrides"].pop(product, None)
            else:
                self.data["overrides"][product] = {"variable": variable}
            await self._async_save()

    async def async_remove_receipt(self, receipt_id: str) -> bool:
        async with self._lock:
            if self.data["receipts"].pop(receipt_id, None) is None:
                return False
            await self._async_save()
            return True


type KassabonConfigEntry = ConfigEntry[KassabonData]


def _get(hass: HomeAssistant) -> KassabonData:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("AH Kassabon is niet geladen")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the upload endpoint, websocket commands, card and actions."""
    hass.http.register_view(KassabonUploadView())
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL,
                str(Path(__file__).parent / "frontend" / "ah-kassabon-card.js"),
                False,
            )
        ]
    )
    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    websocket_api.async_register_command(hass, ws_products)
    websocket_api.async_register_command(hass, ws_set_variable)

    async def import_file(call: ServiceCall) -> ServiceResponse:
        path = call.data["path"]
        if not hass.config.is_allowed_path(path):
            raise ServiceValidationError(f"Geen toegang tot {path} (allowlist_external_dirs)")
        try:
            content = await hass.async_add_executor_job(Path(path).read_bytes)
        except OSError as err:
            raise ServiceValidationError(f"Kan {path} niet lezen: {err}") from err
        return await _get(hass).async_import_pdf(content, Path(path).name)

    async def set_variable(call: ServiceCall) -> None:
        await _get(hass).async_set_variable(call.data["product"], call.data.get("variable"))

    async def remove_receipt(call: ServiceCall) -> None:
        if not await _get(hass).async_remove_receipt(call.data["receipt_id"]):
            raise ServiceValidationError(f"Kassabon {call.data['receipt_id']} bestaat niet")

    hass.services.async_register(
        DOMAIN,
        "import_file",
        import_file,
        schema=vol.Schema({vol.Required("path"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "set_variable",
        set_variable,
        schema=vol.Schema(
            {vol.Required("product"): cv.string, vol.Optional("variable"): vol.Any(None, cv.boolean)}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "remove_receipt",
        remove_receipt,
        schema=vol.Schema({vol.Required("receipt_id"): cv.string}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KassabonConfigEntry) -> bool:
    data = KassabonData(hass)
    await data.async_load()
    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KassabonConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class KassabonUploadView(HomeAssistantView):
    """POST one or more receipt PDFs (multipart field 'file')."""

    url = UPLOAD_URL
    name = f"api:{DOMAIN}:upload"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        try:
            kassabon = _get(hass)
        except HomeAssistantError as err:
            return self.json_message(str(err), 503)
        results = []
        reader = await request.multipart()
        while (part := await reader.next()) is not None:
            if part.name != "file":
                continue
            content = await part.read(decode=False)
            if len(content) > MAX_UPLOAD_BYTES:
                results.append({"ok": False, "file": part.filename, "error": "Bestand te groot"})
                continue
            results.append(await kassabon.async_import_pdf(bytes(content), part.filename))
        if not results:
            return self.json_message("Geen bestand ontvangen", 400)
        return self.json({"results": results})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/products"})
@websocket_api.async_response
async def ws_products(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    try:
        kassabon = _get(hass)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))
        return
    data = kassabon.data
    products = await hass.async_add_executor_job(
        lambda: [p.as_dict() for p in prices.build_products(data).values()]
    )
    receipts = [
        {"id": rid, "when": r["when"], "store": r.get("store"), "total": r.get("total"), "items": len(r["items"])}
        for rid, r in sorted(data["receipts"].items(), key=lambda kv: kv[1]["when"], reverse=True)
    ]
    connection.send_result(msg["id"], {"products": products, "receipts": receipts})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_variable",
        vol.Required("product"): str,
        vol.Optional("variable"): vol.Any(None, bool),
    }
)
@websocket_api.async_response
async def ws_set_variable(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    try:
        await _get(hass).async_set_variable(msg["product"], msg.get("variable"))
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))
        return
    connection.send_result(msg["id"])
