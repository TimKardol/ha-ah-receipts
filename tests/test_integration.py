from pathlib import Path
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from .fixtures import RECEIPT_JAN

PDF = b"%PDF-1.4 fake"


@pytest.fixture(autouse=True)
def fake_pdf_text():
    """Real receipts are private, so feed the parser a made-up receipt."""
    def fake(data):
        if not data.startswith(b"%PDF"):
            from custom_components.ah_kassabon.parser import ReceiptParseError
            raise ReceiptParseError("Kan PDF niet lezen")
        return RECEIPT_JAN
    with patch("custom_components.ah_kassabon.parser.pdf_to_text", side_effect=fake):
        yield

FAKE_AH = {
    "ah spaghetti": [{"id": 11, "title": "AH Spaghetti", "brand": "AH", "size": "500 g", "price": 0.99, "image": None}],
    "ah pindakaas": [
        {"id": 21, "title": "AH Pindakaas naturel", "brand": "AH", "size": "350 g", "price": 2.49, "image": None},
        {"id": 22, "title": "AH Pindakaas met stukjes", "brand": "AH", "size": "350 g", "price": 2.49, "image": None},
    ],
}


@pytest.fixture(autouse=True)
def fake_ah_search():
    """No network in tests: answer AH searches from a made-up table."""
    async def fake(self, query, size=10):
        return list(FAKE_AH.get(query, []))
    with patch("custom_components.ah_kassabon.ah_search.AhSearch.search", fake), \
         patch("custom_components.ah_kassabon.asyncio.sleep", return_value=None):
        yield


async def _setup(hass):
    entry = MockConfigEntry(domain="ah_kassabon", title="AH Kassabon")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry

async def test_upload_ws_and_sensors(hass, hass_client, hass_ws_client):
    await async_setup_component(hass, "http", {})
    await _setup(hass)
    events = async_capture_events(hass, "ah_kassabon_imported")
    states = [s.entity_id for s in hass.states.async_all("sensor")]
    assert len(states) == 3

    client = await hass_client()
    form = aiohttp.FormData(); form.add_field("file", PDF, filename="bon.pdf", content_type="application/pdf")
    resp = await client.post("/api/ah_kassabon/upload", data=form)
    assert resp.status == 200, await resp.text()
    body = await resp.json()
    r = body["results"][0]
    assert r["ok"] and not r["duplicate"] and r["items"] == 8, r
    await hass.async_block_till_done()
    assert len(events) == 1

    # duplicate
    form = aiohttp.FormData(); form.add_field("file", PDF, filename="bon.pdf", content_type="application/pdf")
    body = await (await client.post("/api/ah_kassabon/upload", data=form)).json()
    assert body["results"][0]["duplicate"]
    # junk
    form = aiohttp.FormData(); form.add_field("file", b"not a pdf", filename="x.pdf")
    body = await (await client.post("/api/ah_kassabon/upload", data=form)).json()
    assert not body["results"][0]["ok"]

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ah_kassabon/products"})
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert len(msg["result"]["receipts"]) == 1 and len(msg["result"]["products"]) == 7
    await ws.send_json({"id": 2, "type": "ah_kassabon/set_variable", "product": "AH RUNDERGEH", "variable": True})
    assert (await ws.receive_json())["success"]

    # card JS is served
    resp = await client.get("/ah_kassabon/ah-kassabon-card.js")
    assert resp.status == 200

async def test_import_file_service(hass, tmp_path):
    await async_setup_component(hass, "http", {})
    await _setup(hass)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    p = tmp_path / "bon.pdf"; p.write_bytes(PDF)
    res = await hass.services.async_call("ah_kassabon", "import_file", {"path": str(p)}, blocking=True, return_response=True)
    assert res["ok"] and res["receipt_id"] == "202601311015-1234"
    await hass.services.async_call("ah_kassabon", "remove_receipt", {"receipt_id": "202601311015-1234"}, blocking=True)

async def test_unauthenticated_upload_rejected(hass, hass_client_no_auth):
    await async_setup_component(hass, "http", {})
    await _setup(hass)
    client = await hass_client_no_auth()
    resp = await client.post("/api/ah_kassabon/upload", data={"file": "x"})
    assert resp.status == 401



async def test_name_lookup_and_confirm(hass, hass_client, hass_ws_client):
    await async_setup_component(hass, "http", {})
    await _setup(hass)
    client = await hass_client()
    form = aiohttp.FormData(); form.add_field("file", PDF, filename="bon.pdf", content_type="application/pdf")
    assert (await client.post("/api/ah_kassabon/upload", data=form)).status == 200
    await hass.async_block_till_done(wait_background_tasks=True)

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ah_kassabon/products"})
    products = {p["key"]: p for p in (await ws.receive_json())["result"]["products"]}
    assert products["AH SPAGHETTI"]["match_status"] == "auto"
    assert products["AH SPAGHETTI"]["title"] == "AH Spaghetti"
    assert products["AH PINDAKAAS"]["match_status"] == "pending"
    assert len(products["AH PINDAKAAS"]["candidates"]) == 2
    assert products["COLA ZERO"]["match_status"] == "none"

    await ws.send_json({"id": 2, "type": "ah_kassabon/search", "query": "ah pindakaas", "key": "AH PINDAKAAS"})
    msg = await ws.receive_json()
    assert msg["success"] and len(msg["result"]["results"]) == 2
    pick = msg["result"]["results"][1]

    await ws.send_json({"id": 3, "type": "ah_kassabon/set_product", "key": "AH PINDAKAAS", "match": pick})
    assert (await ws.receive_json())["success"]
    await ws.send_json({"id": 4, "type": "ah_kassabon/set_product", "key": "COLA ZERO", "status": "skipped"})
    assert (await ws.receive_json())["success"]
    await ws.send_json({"id": 5, "type": "ah_kassabon/set_product", "key": "AH SPAGHETTI", "status": "confirmed"})
    assert (await ws.receive_json())["success"]

    await ws.send_json({"id": 6, "type": "ah_kassabon/products"})
    products = {p["key"]: p for p in (await ws.receive_json())["result"]["products"]}
    assert products["AH PINDAKAAS"]["match_status"] == "confirmed"
    assert products["AH PINDAKAAS"]["title"] == pick["title"]
    assert products["COLA ZERO"]["match_status"] == "skipped"
    assert products["AH SPAGHETTI"]["match_status"] == "confirmed"


async def test_search_unavailable_is_reported(hass, hass_ws_client):
    from custom_components.ah_kassabon.ah_search import AhSearchError
    await async_setup_component(hass, "http", {})
    await _setup(hass)
    ws = await hass_ws_client(hass)
    with patch("custom_components.ah_kassabon.ah_search.AhSearch.search", side_effect=AhSearchError("weg")):
        await ws.send_json({"id": 1, "type": "ah_kassabon/search", "query": "melk"})
        msg = await ws.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "search_failed"
