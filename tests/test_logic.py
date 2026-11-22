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
