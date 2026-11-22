from pathlib import Path
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from .fixtures import RECEIPT_JAN, later_receipt

PDF = b"%PDF-1.4 fake"
PDF_FEB = b"%PDF-1.4 february"


@pytest.fixture(autouse=True)
def fake_pdf_text():
    """Real receipts are private, so feed the parser a made-up receipt."""
    def fake(data):
        if not data.startswith(b"%PDF"):
            from custom_components.ah_kassabon.parser import ReceiptParseError
            raise ReceiptParseError("Kan PDF niet lezen")
        if data == PDF_FEB:
            return later_receipt(7, {"0,99": "1,05"})
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


TOKENS = {"access_token": "a1", "refresh_token": "r1", "member_id": "m", "expires_at": 4102444800}


async def test_account_sync_imports_and_links_products(hass, hass_client, hass_ws_client):
    """Two receipts in the account: January was uploaded by hand, February is new."""
    from custom_components.ah_kassabon import ah_search
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    await async_setup_component(hass, "http", {})
    rows = [
        {"id": "feb", "when": "2026-02-07T10:15:00+01:00", "total": 30.06},
        {"id": "jan", "when": "2026-01-31T09:15:30Z", "total": 30.00},  # same moment, UTC
    ]
    lines = {
        "jan": [{"name": "AH SPAGHETTI", "qty": 1, "price": None, "amount": 0.99, "pos_id": 501},
                {"name": "AH  pindakaas", "qty": 2, "price": 2.49, "amount": 4.98, "pos_id": 502}],
        "feb": [{"name": "AH SPAGHETTI", "qty": 1, "price": None, "amount": 1.05, "pos_id": 501}],
    }
    info = {
        11: {"id": 11, "title": "AH Spaghetti", "brand": "AH", "size": "500 g", "price": 1.05, "image": None},
        22: {"id": 22, "title": "AH Pindakaas naturel", "brand": "AH", "size": "350 g", "price": 2.49, "image": None},
    }
    pdf_calls = []

    async def receipts(self, offset=0, limit=50):
        return rows if offset == 0 else []

    async def receipt_pdf(self, rid):
        pdf_calls.append(rid)
        return PDF_FEB

    async def receipt_products(self, rid):
        return lines[rid]

    async def webshop_ids(self, ids):
        return {501: 11, 502: 22}

    async def products_by_ids(self, ids):
        return {i: info[i] for i in ids}

    entry = MockConfigEntry(domain="ah_kassabon", title="AH Kassabon", data={"account": TOKENS})
    entry.add_to_hass(hass)
    with patch.object(ah_search.AhAccount, "receipts", receipts), \
         patch.object(ah_search.AhAccount, "receipt_pdf", receipt_pdf), \
         patch.object(ah_search.AhAccount, "receipt_products", receipt_products), \
         patch.object(ah_search.AhAccount, "webshop_ids", webshop_ids), \
         patch.object(ah_search.AhSearch, "products_by_ids", products_by_ids), \
         patch("custom_components.ah_kassabon.SYNC_DAYS", 100000), \
         patch("custom_components.ah_kassabon.KassabonData.schedule_sync"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        events = async_capture_events(hass, "ah_kassabon_imported")
        client = await hass_client()
        form = aiohttp.FormData(); form.add_field("file", PDF, filename="bon.pdf", content_type="application/pdf")
        assert (await client.post("/api/ah_kassabon/upload", data=form)).status == 200

        ws = await hass_ws_client(hass)
        await ws.send_json({"id": 1, "type": "ah_kassabon/sync"})
        msg = await ws.receive_json()
        assert msg["success"], msg
        assert msg["result"] == {"new_receipts": 1, "linked_receipts": 2, "named_products": 2}
        assert pdf_calls == ["feb"]  # January was already there
        await hass.async_block_till_done(wait_background_tasks=True)
        assert len(events) == 1  # only the hand upload; old account receipts stay quiet

        await ws.send_json({"id": 2, "type": "ah_kassabon/products"})
        result = (await ws.receive_json())["result"]
        products = {p["key"]: p for p in result["products"]}
        assert len(result["receipts"]) == 2
        assert result["account"]["connected"] and result["account"]["last_sync"]
        assert products["AH SPAGHETTI"]["match_status"] == "account"
        assert products["AH SPAGHETTI"]["title"] == "AH Spaghetti"
        assert products["AH PINDAKAAS"]["title"] == "AH Pindakaas naturel"

        # A second sync finds nothing new.
        await ws.send_json({"id": 3, "type": "ah_kassabon/sync"})
        assert (await ws.receive_json())["result"]["new_receipts"] == 0


async def test_sync_without_login(hass, hass_ws_client):
    await async_setup_component(hass, "http", {})
    await _setup(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "ah_kassabon/sync"})
    msg = await ws.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "sync_failed"


async def test_options_login_and_logout(hass, aioclient_mock):
    aioclient_mock.post(
        "https://api.ah.nl/mobile-auth/v1/auth/token",
        json={"access_token": "a2", "refresh_token": "r2", "member_id": "m", "expires_in": 3600},
    )
    aioclient_mock.post("https://api.ah.nl/graphql", json={"data": {"posReceiptsPage": {"posReceipts": []}}})
    await async_setup_component(hass, "http", {})
    entry = await _setup(hass)

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["step_id"] == "login" and "login.ah.nl" in flow["description_placeholders"]["url"]
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"code": "appie://login-exit?code=ABC123&state=x"}
    )
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.data["account"]["access_token"] == "a2"
    sent = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/auth/token")]
    assert sent[0][2] == {"clientId": "appie-ios", "code": "ABC123"}
    assert entry.runtime_data.account is not None

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] == "menu"
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "logout"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {})
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done(wait_background_tasks=True)
    assert "account" not in entry.data
    assert entry.runtime_data.account is None


async def test_options_login_rejected_code(hass, aioclient_mock):
    aioclient_mock.post("https://api.ah.nl/mobile-auth/v1/auth/token", status=400)
    await async_setup_component(hass, "http", {})
    entry = await _setup(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"code": "old"})
    assert flow["type"] == "form" and flow["errors"] == {"code": "invalid_code"}


async def test_account_refreshes_expired_token(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from custom_components.ah_kassabon.ah_search import AhAccount
    aioclient_mock.post(
        "https://api.ah.nl/mobile-auth/v1/auth/token/refresh",
        json={"access_token": "fresh", "refresh_token": "r9", "expires_in": 3600},
    )
    aioclient_mock.post(
        "https://api.ah.nl/graphql",
        json={"data": {"posReceiptsPage": {"posReceipts": [{"id": "x", "dateTime": "2026-01-31T10:15:00", "totalAmount": {"amount": 30.0}}]}}},
    )
    saved = []
    account = AhAccount(async_get_clientsession(hass), {**TOKENS, "expires_at": 0}, saved.append)
    assert await account.receipts() == [{"id": "x", "when": "2026-01-31T10:15:00", "total": 30.0}]
    assert saved[0]["access_token"] == "fresh" and saved[0]["member_id"] == "m"
    graphql = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/graphql")][0]
    assert graphql[3]["Authorization"] == "Bearer fresh"


async def test_reauth_with_new_code(hass, aioclient_mock):
    aioclient_mock.post(
        "https://api.ah.nl/mobile-auth/v1/auth/token",
        json={"access_token": "a3", "refresh_token": "r3", "expires_in": 3600},
    )
    aioclient_mock.post("https://api.ah.nl/graphql", json={"data": {"posReceiptsPage": {"posReceipts": []}}})
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain="ah_kassabon", title="AH Kassabon", data={"account": TOKENS})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    flow = await entry.start_reauth_flow(hass)
    assert flow["step_id"] == "reauth_confirm"
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"code": "NEW"})
    assert flow["type"] == "abort" and flow["reason"] == "reauth_successful"
    assert entry.data["account"]["access_token"] == "a3"
