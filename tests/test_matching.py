"""Matching receipt short names to AH search results (made-up products)."""

from custom_components.ah_kassabon import matching


def _p(pid, title, price, brand="AH"):
    return {"id": pid, "title": title, "brand": brand, "price": price}


def test_search_queries():
    assert matching.search_queries("AH BAKAARDAP") == ["ah bakaardap"]
    assert matching.search_queries("HALFVOLLE MELK") == ["halfvolle melk", "halfvolle"]
    assert matching.search_queries("AH") == []


def test_rank_prefers_name_and_price():
    cands = [
        _p(1, "AH Bakaardappelen", 2.19),
        _p(2, "AH Bakaardappelen krieltjes", 2.79),
        _p(3, "Lay's Bakaardappel chips", 2.19, brand="Lay's"),
        _p(1, "AH Bakaardappelen", 2.19),  # duplicate
    ]
    ranked = matching.rank("AH BAKAARDAP", 2.19, cands)
    assert [c["id"] for c in ranked] == [1, 3, 2]
    assert ranked[0]["score"] == 110
    assert matching.pick_automatically(ranked) == ranked[0]


def test_close_call_asks_the_person():
    ranked = matching.rank("AH YOGHURT", 1.29, [_p(1, "AH Yoghurt naturel", 1.29), _p(2, "AH Yoghurt Grieks", 1.29)])
    assert matching.pick_automatically(ranked) is None
    assert matching.pick_automatically([]) is None


def test_glued_words_and_prefix():
    ranked = matching.rank("AH ROERBAKGR", 2.49, [_p(1, "AH Roerbak groenten", 2.49)])
    assert ranked[0]["score"] >= matching.AUTO_SCORE


def test_product_from_search():
    raw = {
        "webshopId": 42, "title": "AH Pesto", "brand": "AH", "salesUnitSize": "190 g",
        "currentPrice": 1.5, "priceBeforeBonus": 2.29,
        "images": [{"url": "big", "width": 800}, {"url": "small", "width": 200}, {"width": 50}],
    }
    assert matching.product_from_search(raw) == {
        "id": 42, "title": "AH Pesto", "brand": "AH", "size": "190 g", "price": 2.29, "image": "small",
    }
    assert matching.product_from_search({"webshopId": 1})["price"] is None


def test_same_product_listed_twice_is_one():
    ranked = matching.rank("AH STOKBROOD", 1.49, [
        {"id": 1, "title": "AH Stokbrood wit", "brand": "AH", "size": "per stuk", "price": 1.49},
        {"id": 2, "title": "AH Stokbrood wit", "brand": "AH", "size": "per stuk", "price": 1.49},
        {"id": 3, "title": "AH Stokbrood volkoren", "brand": "AH", "size": "per stuk", "price": 1.49},
    ])
    assert [c["id"] for c in ranked] == [1, 3]


def test_code_from_input():
    from custom_components.ah_kassabon.ah_search import code_from_input
    assert code_from_input("appie://login-exit?code=AbC-123&foo=1") == "AbC-123"
    assert code_from_input("  AbC-123 ") == "AbC-123"


def test_account_ids_keep_same_name_products_apart():
    from custom_components.ah_kassabon import prices
    def receipt(day, unit, pid):
        return {"when": f"2026-01-{day:02d}T10:00:00", "items": [{"name": "AH BROOD", "qty": 1, "unit": unit, "bonus": False}],
                "ids": [{"name": "AH BROOD", "price": unit, "id": pid}]}
    receipts = {"r1": receipt(3, 2.79, 1), "r2": receipt(10, 1.49, 2), "r3": receipt(17, 2.79, 1)}
    products = prices.build_products({"receipts": receipts, "overrides": {}})
    assert matching.account_ids(products, receipts) == {"AH BROOD": 1, "AH BROOD#2": 2}
