"""Parser and price logic, no Home Assistant needed."""

from datetime import datetime

import pytest

from custom_components.ah_kassabon import parser, prices

from .fixtures import RECEIPT_CARD, RECEIPT_JAN, later_receipt


def _store(*texts):
    data = {"receipts": {}, "overrides": {}}
    ids = []
    for text in texts:
        r = parser.parse_text(text)
        data["receipts"][r.receipt_id] = {
            "when": r.when.isoformat(), "store": r.store, "total": r.total,
            "items": [vars(i) for i in r.items],
        }
        ids.append(r.receipt_id)
    return data, ids


def test_parse_receipt():
    r = parser.parse_text(RECEIPT_JAN)
    assert r.when == datetime(2026, 1, 31, 10, 15)
    assert r.store == "1234" and r.total == 30.00
    assert r.receipt_id == "202601311015-1234"
    assert sum(i.qty for i in r.items) == 9 and len(r.items) == 8
    by = {i.name: i for i in r.items}
    assert by["AH PINDAKAAS"].unit == 2.49 and by["AH PINDAKAAS"].qty == 2
    assert by["HALFVOLLE MELK"].bonus and not by["AH SPAGHETTI"].bonus
    assert by["AH RUNDERGEH"].unit == 4.57 and by["AH RUNDERGEH"].bonus  # flag glued to amount
    assert "+STATIEGELD" not in by


def test_rejects_other_text():
    with pytest.raises(parser.ReceiptParseError):
        parser.parse_text("hallo wereld")


def test_compare_and_variable_weight():
    feb = later_receipt(7, {"AH ROOMBOTER                  2,19": "AH ROOMBOTER                  2,49",
                            "COLA ZERO                     2,29": "COLA ZERO                     1,99"})
    data, (jan_id, feb_id) = _store(RECEIPT_JAN, feb)
    result = prices.compare_receipt(data, feb_id)
    assert [c["product"] for c in result["increases"]] == ["AH ROOMBOTER"]
    assert result["increases"][0]["diff"] == 0.30
    assert [c["product"] for c in result["decreases"]] == ["COLA ZERO"]
    assert result["skipped_variable"] == 1  # AH KIPFILET: two prices on one receipt
    summary = prices.summary(data)
    assert summary["receipts"] == 2 and len(summary["more_expensive"]) == 1


def test_streak_marks_variable_and_override_wins():
    texts = [RECEIPT_JAN] + [
        later_receipt(d, {"AH RUNDERGEH                  4,57": f"AH RUNDERGEH                  {p}"})
        for d, p in [(7, "4,81"), (14, "4,33"), (21, "4,95")]
    ]
    data, _ = _store(*texts)
    assert prices.build_products(data)["AH RUNDERGEH"].variable
    data["overrides"]["AH RUNDERGEH"] = {"variable": False}
    assert not prices.build_products(data)["AH RUNDERGEH"].variable


def test_card_receipt_weighed_discount_and_time():
    r = parser.parse_text(RECEIPT_CARD)
    assert r.when == datetime(2026, 2, 14, 9, 5)  # from the PAYMENT line, not "9:0"
    assert r.missing_items == 0 and r.printed_count == 5
    by = {i.name: i for i in r.items}
    assert by["BANANEN"].per_kg and by["BANANEN"].unit == 1.89 and by["BANANEN"].qty == 1
    assert by["AH APPELTAART"].unit == 6.49 and by["AH APPELTAART"].bonus
    assert by["AH YOGHURT"].unit == 1.29 and by["AH YOGHURT"].qty == 2


def test_missing_items_reported():
    text = RECEIPT_CARD.replace("1             AH BROCCOLI                                 1,49  B",
                                "1             AH BROCCOLI                                 ??")
    assert parser.parse_text(text).missing_items == 1


def test_footer_time_when_no_card_payment():
    assert parser.parse_text(RECEIPT_JAN).when == datetime(2026, 1, 31, 10, 15)


def test_price_jump_splits_variants_and_merge_undoes_it():
    data, _ = _store(
        RECEIPT_JAN,
        later_receipt(7, {"0,99": "1,89"}),  # spaghetti jumps 91%: another product
        later_receipt(14, {"0,99": "1,05"}),  # back near the first price
    )
    products = prices.build_products(data)
    assert products["AH SPAGHETTI"].variants == 2
    assert [o.price for o in products["AH SPAGHETTI"].observations] == [0.99, 1.05]
    assert [o.price for o in products["AH SPAGHETTI#2"].observations] == [1.89]
    assert products["AH SPAGHETTI#2"].as_dict()["key"] == "AH SPAGHETTI#2"

    data["overrides"]["AH SPAGHETTI"] = {"no_split": True}
    products = prices.build_products(data)
    assert "AH SPAGHETTI#2" not in products
    assert len(products["AH SPAGHETTI"].observations) == 3


def test_name_info_reaches_product():
    data, _ = _store(RECEIPT_JAN)
    data["names"] = {"AH SPAGHETTI": {"status": "auto", "match": {"id": 7, "title": "AH Spaghetti", "image": "x"}}}
    info = prices.build_products(data)["AH SPAGHETTI"].as_dict()
    assert info["title"] == "AH Spaghetti" and info["match_status"] == "auto" and info["product_id"] == 7
    assert prices.build_products(data)["AH PINDAKAAS"].as_dict()["match_status"] == "new"



def _account_receipt(day, lines):
    """A receipt fetched through the AH account: (name, unit, AH id) per line."""
    return {
        "when": f"2026-03-{day:02d}T10:00:00",
        "items": [{"name": n, "qty": 1, "unit": u, "bonus": False} for n, u, _ in lines],
        "ids": [{"name": n, "price": u, "id": i} for n, u, i in lines],
    }


def test_same_short_name_different_ah_products_are_split_not_weighed():
    receipts = {
        "r1": _account_receipt(1, [("AH WATER", 0.49, 1), ("AH WATER", 2.29, 2)]),
        "r2": _account_receipt(8, [("AH WATER", 0.55, 1)]),
        "r3": _account_receipt(15, [("AH WATER", 2.29, 2), ("AH WATER", 0.59, 1)]),
    }
    products = prices.build_products({"receipts": receipts, "overrides": {}})
    assert set(products) == {"AH WATER", "AH WATER#2"}
    assert [o.price for o in products["AH WATER"].observations] == [0.49, 0.55, 0.59]
    assert not products["AH WATER"].variable and not products["AH WATER#2"].variable


def test_weight_comes_from_ah_size():
    receipts = {f"r{d}": _account_receipt(d, [("AH STEAK", p, 7), ("AH KAAS", k, 8)])
                for d, p, k in ((1, 6.10, 3.29), (8, 5.80, 3.39), (15, 6.40, 3.49), (22, 6.00, 3.59))}
    names = {"AH STEAK": {"status": "account", "match": {"id": 7, "size": "ca. 280 g"}},
             "AH KAAS": {"status": "account", "match": {"id": 8, "size": "190 g"}}}
    products = prices.build_products({"receipts": receipts, "overrides": {}, "names": names})
    assert products["AH STEAK"].variable  # sold by weight
    assert not products["AH KAAS"].variable  # price went up every time, but it is a fixed pack
    assert products["AH KAAS"].as_dict()["diff"] == 0.30
