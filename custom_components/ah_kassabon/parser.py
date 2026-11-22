"""Read an Albert Heijn digital receipt (kassabon) PDF.

The AH app shares receipts as text PDFs. With layout extraction each product
line looks like:

    2        AH PINDAKAAS         2,49     4,98
    1        HALFVOLLE MELK                1,15 B
    1        AH KIPFILET                   6,12BB

quantity, name (cut to ~12 characters), unit price (only when quantity > 1),
line amount, and an optional Bonus flag. Product lines sit between the
BONUSKAART / AIRMILES lines and SUBTOTAAL. Bonus discounts are printed as
separate lines below SUBTOTAAL, so the product prices are regular shelf prices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import io
import re

_ITEM_RE = re.compile(
    r"^\s*(?P<qty>\d+(?:[.,]\d+)?)(?P<kg>KG)?\s+(?P<name>\S.*?)\s+(?P<a>\d+,\d\d)"
    r"(?:\s+(?P<b>\d+,\d\d))?\s*(?P<flag>B+|\d+%)?\s*$",
    re.IGNORECASE,
)
# Card payments print a full timestamp: "PAYMENT   Date   03/10/2026 12:01".
_PAYMENT_WHEN_RE = re.compile(r"Date\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})")
# The footer line "13:47   13-9-2026"; its time is sometimes cut short ("12:1").
_WHEN_RE = re.compile(r"(\d{1,2}):(\d{1,2})\s+(\d{1,2})-(\d{1,2})-(\d{4})")
_TOTAL_RE = re.compile(r"^\s*TOTAAL\s+(-?\d+,\d\d)\s*$", re.MULTILINE)
_STORE_RE = re.compile(r"^\s*(\d{3,5})\s*$", re.MULTILINE)
_COUNT_RE = re.compile(r"^\s*(\d+)\s+SUBTOTAAL", re.MULTILINE)


class ReceiptParseError(ValueError):
    """The file is not a readable AH receipt."""


@dataclass
class ReceiptItem:
    name: str
    qty: int
    unit: float
    bonus: bool
    per_kg: bool = False


@dataclass
class Receipt:
    when: datetime
    store: str | None
    total: float | None
    items: list[ReceiptItem] = field(default_factory=list)
    printed_count: int | None = None  # item count AH prints next to SUBTOTAAL

    @property
    def missing_items(self) -> int:
        """Items AH counted that the reader did not pick up (0 when all read)."""
        if self.printed_count is None:
            return 0
        return max(0, self.printed_count - sum(i.qty for i in self.items))

    @property
    def receipt_id(self) -> str:
        return f"{self.when:%Y%m%d%H%M}-{self.store or 'x'}"


def _num(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def pdf_to_text(data: bytes) -> str:
    """Extract layout text from PDF bytes. Blocking: run in an executor."""
    from pypdf import PdfReader  # imported lazily, pypdf is a heavy import

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(
            page.extract_text(extraction_mode="layout") or "" for page in reader.pages
        )
    except Exception as err:  # pypdf raises many error types
        raise ReceiptParseError(f"Kan PDF niet lezen: {err}") from err


def parse_text(text: str) -> Receipt:
    """Parse the extracted text of an AH receipt."""
    lines = text.splitlines()
    items: list[ReceiptItem] = []
    in_items = False
    seen_subtotal = False
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if not in_items:
            if upper.startswith(("BONUSKAART", "AIRMILES")):
                in_items = True
            elif upper.startswith("AANTAL") and "OMSCHRIJVING" in upper:
                in_items = True
            continue
        if upper.startswith(("BONUSKAART", "AIRMILES")):
            continue
        if "SUBTOTAAL" in upper:
            seen_subtotal = True
            break
        match = _ITEM_RE.match(line)
        if not match:
            continue  # e.g. +STATIEGELD (deposit) lines
        first = _num(match["a"])
        if match["kg"]:
            # "0.350KG  BANANEN  1,89  0,66": price per kg, then the amount.
            if not match["b"]:
                continue
            qty, unit, per_kg = 1, first, True
        else:
            if not match["qty"].isdigit() or int(match["qty"]) <= 0:
                continue
            qty = int(match["qty"])
            unit = first if match["b"] else first / qty
            per_kg = False
        items.append(
            ReceiptItem(
                name=" ".join(match["name"].split()).upper(),
                qty=qty,
                unit=round(unit, 2),
                bonus=bool(match["flag"]),
                per_kg=per_kg,
            )
        )

    if not seen_subtotal or not items:
        raise ReceiptParseError("Dit lijkt geen AH-kassabon te zijn")
    when = _receipt_time(text)
    if when is None:
        raise ReceiptParseError("Datum en tijd niet gevonden op de kassabon")

    total_match = _TOTAL_RE.search(text)
    store_match = _STORE_RE.search(text)
    count_match = _COUNT_RE.search(text)
    return Receipt(
        when=when,
        store=store_match.group(1) if store_match else None,
        total=_num(total_match.group(1)) if total_match else None,
        items=items,
        printed_count=int(count_match.group(1)) if count_match else None,
    )


def _receipt_time(text: str) -> datetime | None:
    if payment := _PAYMENT_WHEN_RE.search(text):
        day, month, year, hh, mm = (int(x) for x in payment.groups())
        return datetime(year, month, day, hh, mm)
    if footer := _WHEN_RE.findall(text):
        hh, mm, day, month, year = (int(x) for x in footer[-1])
        return datetime(year, month, day, hh, mm)
    return None


def parse_pdf(data: bytes) -> Receipt:
    """Parse AH receipt PDF bytes. Blocking: run in an executor."""
    return parse_text(pdf_to_text(data))
