"""Presentation helpers shared by the CLI, web dashboard, and report generator.

These do not change the validated data — they only group and format it for humans,
so the JSON deliverable stays exactly the provided schema.
"""

from __future__ import annotations

from .schema import TuitionItem

# Order matters: the first keyword that matches a fee_type wins, so more specific
# buckets ("room & board") are checked before generic ones ("fees").
_FEE_CATEGORIES = (
    ("Total / Cost of Attendance", ("total", "cost of attendance", "direct cost", "estimated cost")),
    ("Housing", ("room", "board", "housing", "residence")),
    ("Food / Meals", ("food", "meal", "dining")),
    ("Books & Supplies", ("book", "supplies", "materials")),
    ("Health & Insurance", ("insurance", "health")),
    ("Transportation", ("transport", "travel", "parking")),
    ("Personal", ("personal", "miscellaneous", "misc")),
    ("Tuition", ("tuition",)),
    ("Fees", ("fee",)),
)

CATEGORY_ORDER = [name for name, _ in _FEE_CATEGORIES] + ["Other"]


def fee_category(fee_type: str | None) -> str:
    """Bucket a free-text fee label into a stable, display-friendly category."""
    low = (fee_type or "").lower()
    for name, keywords in _FEE_CATEGORIES:
        if any(k in low for k in keywords):
            return name
    return "Other"


def format_cost(item: TuitionItem) -> str:
    """Render a cost as e.g. "$11,466" (USD) or "11,466 EUR"."""
    if item.cost is None:
        return "—"
    currency = item.currency or "USD"
    return f"${item.cost:,}" if currency == "USD" else f"{item.cost:,} {currency}"


def tuition_summary(items: list[TuitionItem]) -> dict:
    """Headline stats for a cost breakdown: count and lowest/highest figures."""
    costs = [i.cost for i in items if i.cost is not None]
    return {
        "count": len(items),
        "lowest": min(costs) if costs else None,
        "highest": max(costs) if costs else None,
        "categories": len({fee_category(i.fee_type) for i in items}),
    }


def group_by_category(items: list[TuitionItem]) -> list[tuple[str, list[TuitionItem]]]:
    """Group fee items by category, returned in the canonical display order."""
    buckets: dict[str, list[TuitionItem]] = {}
    for item in items:
        buckets.setdefault(fee_category(item.fee_type), []).append(item)
    return [(cat, buckets[cat]) for cat in CATEGORY_ORDER if cat in buckets]
