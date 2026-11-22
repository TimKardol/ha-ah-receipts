"""Match a short receipt name ("AH BAKAARDAP") to AH products found by search.

Pure Python, no Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

import re
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")

# Score needed, and lead over the runner-up, to accept a match without asking.
AUTO_SCORE = 80
AUTO_LEAD = 25


def _words(text: str) -> list[str]:
    text = (
        text.lower()
        .replace("é", "e")
        .replace("ë", "e")
        .replace("è", "e")
        .replace("ï", "i")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("'", "")
        .replace("&", " ")
    )
    return _WORD_RE.findall(text)


def search_queries(short_name: str) -> list[str]:
    """Queries to try, most specific first: the full short name, then shorter."""
    words = _words(short_name)
    queries = []
    for n in range(len(words), 0, -1):
        query = " ".join(words[:n])
        if query in ("ah",) or (n == 1 and len(query) < 3):
            continue
        queries.append(query)
    return queries[:3]


def _name_score(short_name: str, title: str, brand: str | None) -> int:
    """0-60: how well the truncated receipt words fit the product title."""
    short = _words(short_name)
    is_ah = bool(short) and short[0] == "ah"
    if is_ah:
        short = short[1:]
    title_words = _words(title)
    joined = "".join(title_words)
    if not short:
        return 0
    hits = 0
    for word in short:
        # Receipt words are cut off ("BAKAARDAP"), or glue two words ("ROERBAKGR").
        if any(t.startswith(word) for t in title_words) or word in joined:
            hits += 1
        elif any(word.startswith(t) and len(t) >= 3 for t in title_words):
            hits += 0.5
    score = 45 * hits / len(short)
    brand_is_ah = (brand or "").strip().upper() == "AH" or title.upper().startswith("AH ")
    if is_ah == brand_is_ah:
        score += 15
    elif is_ah:
        # The receipt says AH, so another brand is almost certainly wrong.
        score -= 15
    return max(0, round(score))


def _price_score(target: float | None, price: float | None) -> int:
    """0-50: how close the product's regular price is to the receipt price."""
    if target is None or not price:
        return 0
    if abs(price - target) < 0.005:
        return 50
    off = abs(price - target) / target
    if off <= 0.05:
        return 35
    if off <= 0.15:
        return 20
    if off <= 0.30:
        return 8
    return 0


def rank(short_name: str, target_price: float | None, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score and sort candidates; each gets 'score'. Duplicates by id are dropped."""
    seen: set[Any] = set()
    ranked = []
    for cand in candidates:
        # AH sometimes lists the same product twice under two ids.
        same = (cand.get("title", "").lower(), cand.get("size"), cand.get("price"))
        if cand.get("id") in seen or same in seen:
            continue
        seen.update((cand.get("id"), same))
        score = _name_score(short_name, cand.get("title", ""), cand.get("brand")) + _price_score(
            target_price, cand.get("price")
        )
        ranked.append({**cand, "score": score})
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked


def pick_automatically(ranked: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The clear winner, or None when the person should choose."""
    if not ranked or ranked[0]["score"] < AUTO_SCORE:
        return None
    if len(ranked) > 1 and ranked[0]["score"] - ranked[1]["score"] < AUTO_LEAD:
        return None
    return ranked[0]


def product_from_search(raw: dict[str, Any]) -> dict[str, Any]:
    """Trim an AH search result to what we store."""
    images = raw.get("images") or []
    image = None
    if images:
        small = sorted(
            (i for i in images if i.get("url")), key=lambda i: i.get("width") or 9999
        )
        image = small[0]["url"] if small else None
    regular = raw.get("priceBeforeBonus") or raw.get("currentPrice")
    return {
        "id": raw.get("webshopId"),
        "title": raw.get("title") or "",
        "brand": raw.get("brand"),
        "size": raw.get("salesUnitSize"),
        "price": float(regular) if regular else None,
        "image": image,
    }
