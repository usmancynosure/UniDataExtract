"""Value normalization shared by both extractors.

Keeping money/contact/deadline parsing here means the LLM and the heuristic path
emit identically shaped values, and the rules are unit-testable in isolation.
"""

from __future__ import annotations

import re

_MONEY_RE = re.compile(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{2})?")
_PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_POSTAL_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")


def count_money(text: str) -> int:
    """How many dollar figures a page contains — a signal that it holds real costs."""
    return len(_MONEY_RE.findall(text))


def cost_appears_in(cost: int, text: str) -> bool:
    """True if a cost figure is actually present in the source text (grounding).

    Checks both the comma-grouped form ("11,466") and the plain form ("11466"),
    so an LLM-returned number that was never on the page is rejected.
    """
    return f"{cost:,}" in text or str(cost) in text.replace(",", "")


def to_cost(value) -> int | None:
    """Parse a currency-ish value into a whole-dollar int, or None.

    Accepts already-numeric input (the LLM usually returns numbers) and strings
    like "$58,212", "58,212.00", or "$1,500 per semester". `cost` is an int in
    the target schema, so cents are rounded away.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).strip()
    if not text:
        return None
    match = _MONEY_RE.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    bare = re.search(r"[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?", text)
    if bare:
        try:
            return int(round(float(bare.group(0).replace(",", ""))))
        except ValueError:
            return None
    return None


def safe_email(value) -> str | None:
    """Return value only if it is a syntactically valid email, else None.

    The schema types email as EmailStr, which raises on malformed input. Guarding
    here keeps a stray LLM string from failing validation for the whole record.
    """
    if not value:
        return None
    match = _EMAIL_RE.search(str(value))
    if not match:
        return None
    candidate = match.group(0)
    if candidate.lower().endswith((".png", ".jpg", ".gif", ".webp")):
        return None
    return candidate


def find_phone(text: str) -> str | None:
    m = _PHONE_RE.search(text)
    return m.group(0).strip() if m else None


def find_email(text: str) -> str | None:
    for m in _EMAIL_RE.finditer(text):
        candidate = m.group(0)
        if not candidate.lower().endswith((".png", ".jpg", ".gif", ".webp")):
            return candidate
    return None


def find_postal_code(text: str) -> str | None:
    m = _POSTAL_RE.search(text)
    return m.group(0) if m else None


# The provided DeadlineType enum only allows these three values. Anything that
# does not map to one of them is dropped (per the chosen strict behavior).
_DEADLINE_MAP = (
    ("transfer", "Transfer Admission"),
    ("early decision", "Early Decision"),
    ("regular", "Regular Decision"),
)


def to_deadline_type(raw) -> str | None:
    """Map a free-text deadline label to one of the three allowed enum values."""
    if not raw:
        return None
    low = str(raw).lower()
    for keyword, value in _DEADLINE_MAP:
        if keyword in low:
            return value
    return None
