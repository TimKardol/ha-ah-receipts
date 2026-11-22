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
# AH rarely moves a shelf price this much at once; a bigger jump under the same
# short receipt name is treated as a different product (e.g. a whole loaf 2,79 vs a half 1,49).
SPLIT_JUMP = 0.30


@dataclass
class Observation:
    receipt_id: str
    when: str  # ISO datetime, sorts chronologically
    price: float
    qty: int
    bonus: bool


@dataclass
class Product:
    name: str  # short name as printed on the receipt
    key: str = ""  # name, or name#2, name#3 ... for products sharing a short name
    observations: list[Observation] = field(default_factory=list)
    variable_auto: bool = False
    variable_override: bool | None = None
    per_kg: bool = False
    variant: int = 1
    variants: int = 1
    info: dict[str, Any] = field(default_factory=dict)  # data["names"][key]

    def __post_init__(self) -> None:
        self.key = self.key or self.name

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
        match = self.info.get("match") or {}
        return {
            "key": self.key,
            "name": self.name,
            "variant": self.variant,
            "variants": self.variants,
            "title": match.get("title"),
            "size": match.get("size"),
            "image": match.get("image"),
            "product_id": match.get("id"),
            "match_status": self.info.get("status", "new"),
            "candidates": self.info.get("candidates", []) if self.info.get("status") == "pending" else [],
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
    """Build every product's price history from the stored receipts, keyed by product key."""
    receipts = sorted(data.get("receipts", {}).items(), key=lambda kv: kv[1]["when"])
    overrides = data.get("overrides", {})
    names = data.get("names", {})

    # 1. One observation per short name per receipt.
    by_name: dict[str, Product] = {}
    for receipt_id, receipt in receipts:
        per_name: dict[str, list[dict[str, Any]]] = {}
        for item in receipt["items"]:
            per_name.setdefault(item["name"], []).append(item)
        for name, lines in per_name.items():
            product = by_name.setdefault(name, Product(name))
            units = [line["unit"] for line in lines]
            if any(line.get("per_kg") for line in lines):
                product.per_kg = True
            if len(set(units)) > 1:
                # Same name, different prices on one receipt: sold by weight.
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

    # 2. Split a short name into separate products on big price jumps.
    products: dict[str, Product] = {}
    for name, whole in by_name.items():
        base = overrides.get(name, {})
        variable = base.get("variable", whole.variable_auto)
        if variable or base.get("no_split"):
            parts = [whole]
        else:
            parts = _split(whole)
        for idx, part in enumerate(parts, start=1):
            part.variant, part.variants = idx, len(parts)
            part.key = name if idx == 1 else f"{name}#{idx}"
            if part is not whole:
                part.per_kg = whole.per_kg
            if not part.variable_auto:
                part.variable_auto = _changes_every_time(part.observations)
            part.variable_override = overrides.get(part.key, {}).get("variable")
            part.info = names.get(part.key, {})
            products[part.key] = part
    return products


def _split(whole: Product) -> list[Product]:
    parts: list[Product] = []
    for obs in whole.observations:
        best, best_off = None, None
        for part in parts:
            last = part.observations[-1].price
            off = abs(obs.price - last) / last if last else 1.0
            if off <= SPLIT_JUMP and (best_off is None or off < best_off):
                best, best_off = part, off
        if best is None:
            best = Product(whole.name)
            parts.append(best)
        best.observations.append(obs)
    return parts or [whole]


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
            "key": product.key,
            "title": product.info.get("match", {}).get("title") if product.info.get("match") else None,
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
