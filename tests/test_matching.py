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
