"""Value normalization shared by both extractors.

Keeping money/date/year parsing here means the LLM and the heuristic path emit
identically shaped values, and the rules are unit-testable in isolation.
"""

from __future__ import annotations

import re
from datetime import date

from dateutil import parser as date_parser

_MONEY_RE = re.compile(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{2})?")
_YEAR_RANGE_RE = re.compile(r"(20[0-9]{2})\s*[-–—/]\s*(20[0-9]{2}|[0-9]{2})")


def to_money(value) -> float | None:
    """Parse a currency-ish value into a float, or None.

    Accepts already-numeric input (the LLM often returns numbers) and strings
    like "$58,212", "58,212.00", or "$1,500 per semester".
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = _MONEY_RE.search(text)
    if match:
        return float(match.group(1).replace(",", ""))
    # Bare number, possibly embedded in text ("1,500 per semester").
    bare = re.search(r"[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?", text)
    if bare:
        try:
            return float(bare.group(0).replace(",", ""))
        except ValueError:
            return None
    return None


def normalize_academic_year(value) -> str | None:
    """Render an academic year span as "YYYY-YYYY"."""
    if not value:
        return None
    text = str(value)
    m = _YEAR_RANGE_RE.search(text)
    if not m:
        single = re.search(r"20[0-9]{2}", text)
        return single.group(0) if single else None
    start, end = m.group(1), m.group(2)
    if len(end) == 2:  # "2024-25" -> "2024-2025"
        end = start[:2] + end
    return f"{start}-{end}"


def to_date(value) -> date | None:
    """Parse a full calendar date, returning None when the year is missing.

    We deliberately refuse to guess a year. dateutil will happily backfill the
    current year for "November 1", which would fabricate data, so we only accept
    a parse when a 4-digit year is actually present in the text.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or not re.search(r"\b20[0-9]{2}\b", text):
        return None
    try:
        parsed = date_parser.parse(text, fuzzy=True)
        return parsed.date()
    except (ValueError, OverflowError):
        return None


_PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def find_phone(text: str) -> str | None:
    m = _PHONE_RE.search(text)
    return m.group(0).strip() if m else None


def find_email(text: str) -> str | None:
    # Skip image/asset-looking false positives.
    for m in _EMAIL_RE.finditer(text):
        candidate = m.group(0)
        if not candidate.lower().endswith((".png", ".jpg", ".gif", ".webp")):
            return candidate
    return None
