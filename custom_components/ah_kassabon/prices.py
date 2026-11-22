"""Price history and comparisons, built from stored receipts.

Pure Python (no Home Assistant imports) so it can be tested on its own.

Stored data shape:
    {
      "receipts": {receipt_id: {"when": iso, "store": str|None, "total": float|None,
                                "imported": iso,
                                "items": [{"name", "qty", "unit", "bonus"}]}},
      "overrides": {product_name: {"variable": bool}}
    }
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# A product whose price changed on this many purchases in a row is almost
# certainly sold by weight (meat, cheese) rather than repriced by AH.
VARIABLE_STREAK = 3


@dataclass
class Observation:
    receipt_id: str
    when: str  # ISO datetime, sorts chronologically
    price: float
    qty: int
    bonus: bool


@dataclass
class Product:
    name: str
    observations: list[Observation] = field(default_factory=list)
    variable_auto: bool = False
    variable_override: bool | None = None
    per_kg: bool = False

    @property
    def variable(self) -> bool:
        if self.variable_override is not None:
            return self.variable_override
        return self.variable_auto

    @property
    def first(self) -> Observation:
        return self.observations[0]

    @property
    def latest(self) -> Observation:
        return self.observations[-1]

    @property
    def previous_different(self) -> Observation | None:
        """The last purchase at a different price than now, if any."""
        for obs in reversed(self.observations[:-1]):
            if obs.price != self.latest.price:
                return obs
        return None

    def as_dict(self) -> dict[str, Any]:
        first, latest = self.first, self.latest
        diff = round(latest.price - first.price, 2)
        prev = self.previous_different
        return {
            "name": self.name,
            "variable": self.variable,
            "variable_auto": self.variable_auto,
            "per_kg": self.per_kg,
            "times": len(self.observations),
            "quantity": sum(o.qty for o in self.observations),
            "first_price": first.price,
            "first_when": first.when,
            "price": latest.price,
            "when": latest.when,
            "diff": diff,
            "pct": round(diff / first.price * 100, 1) if first.price else None,
            "last_change_from": prev.price if prev else None,
            "last_change_when": _first_at_price_after(self.observations, prev),
            "history": [[o.when, o.price] for o in self.observations],
        }


def _first_at_price_after(observations: list[Observation], prev: Observation | None):
    """When the current price was first seen after the last different price."""
    if prev is None:
        return None
    seen_prev = False
    for obs in observations:
        if obs is prev:
            seen_prev = True
            continue
        if seen_prev and obs.price == observations[-1].price:
            return obs.when
    return None


def _receipt_price(units: list[float]) -> float:
    """One price per product per receipt: the most common unit price."""
    return Counter(units).most_common(1)[0][0]


def build_products(data: dict[str, Any]) -> dict[str, Product]:
    """Build every product's price history from the stored receipts."""
    receipts = sorted(data.get("receipts", {}).items(), key=lambda kv: kv[1]["when"])
    overrides = data.get("overrides", {})
    products: dict[str, Product] = {}
    for receipt_id, receipt in receipts:
        per_name: dict[str, list[dict[str, Any]]] = {}
        for item in receipt["items"]:
            per_name.setdefault(item["name"], []).append(item)
        for name, lines in per_name.items():
            product = products.setdefault(name, Product(name))
            units = [line["unit"] for line in lines]
            if any(line.get("per_kg") for line in lines):
                product.per_kg = True
            if len(set(units)) > 1:
                # Same product, different prices on one receipt: sold by weight.
                product.variable_auto = True
            product.observations.append(
                Observation(
                    receipt_id=receipt_id,
                    when=receipt["when"],
                    price=_receipt_price(units),
                    qty=sum(line["qty"] for line in lines),
                    bonus=any(line["bonus"] for line in lines),
                )
            )
    for product in products.values():
        if not product.variable_auto:
            product.variable_auto = _changes_every_time(product.observations)
        override = overrides.get(product.name, {}).get("variable")
        product.variable_override = override
    return products


def _changes_every_time(observations: list[Observation]) -> bool:
    streak = 0
    for before, after in zip(observations, observations[1:]):
        streak = streak + 1 if before.price != after.price else 0
        if streak >= VARIABLE_STREAK:
            return True
    return False


def compare_receipt(data: dict[str, Any], receipt_id: str) -> dict[str, Any]:
    """Compare one receipt's prices with the last earlier purchase of each product."""
    products = build_products(data)
    receipt = data["receipts"][receipt_id]
    increases: list[dict[str, Any]] = []
    decreases: list[dict[str, Any]] = []
    compared = skipped_variable = 0
    for product in products.values():
        idx = next(
            (i for i, o in enumerate(product.observations) if o.receipt_id == receipt_id),
            None,
        )
        if idx is None:
            continue
        if product.variable:
            skipped_variable += 1
            continue
        if idx == 0:
            continue  # first time we see this product
        now, before = product.observations[idx], product.observations[idx - 1]
        compared += 1
        if now.price == before.price:
            continue
        diff = round(now.price - before.price, 2)
        change = {
            "product": product.name,
            "old": before.price,
            "new": now.price,
            "diff": diff,
            "pct": round(diff / before.price * 100, 1) if before.price else None,
            "since": before.when,
        }
        (increases if diff > 0 else decreases).append(change)
    increases.sort(key=lambda c: c["pct"] or 0, reverse=True)
    decreases.sort(key=lambda c: c["pct"] or 0)
    return {
        "receipt_id": receipt_id,
        "when": receipt["when"],
        "store": receipt.get("store"),
        "total": receipt.get("total"),
        "items": len(receipt["items"]),
        "compared": compared,
        "skipped_variable": skipped_variable,
        "increases": increases,
        "decreases": decreases,
    }


def summary(data: dict[str, Any]) -> dict[str, Any]:
    """Overall figures for the sensors."""
    products = build_products(data)
    tracked = [
        p for p in products.values() if not p.variable and len(p.observations) >= 2
    ]
    up = [p.as_dict() for p in tracked if p.latest.price > p.first.price]
    down = [p.as_dict() for p in tracked if p.latest.price < p.first.price]
    up.sort(key=lambda d: d["pct"] or 0, reverse=True)
    pcts = [
        (p.latest.price - p.first.price) / p.first.price * 100
        for p in tracked
        if p.first.price
    ]
    receipts = data.get("receipts", {})
    latest_id = max(receipts, key=lambda r: receipts[r]["when"]) if receipts else None
    return {
        "receipts": len(receipts),
        "products": len(products),
        "tracked": len(tracked),
        "more_expensive": up,
        "cheaper": down,
        "average_pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
        "latest_receipt": receipts[latest_id] if latest_id else None,
        "latest_receipt_id": latest_id,
    }
