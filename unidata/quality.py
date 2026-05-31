"""Data-quality assessment, source attribution, and confidence scoring.

These are reported alongside the result (CLI, logs, HTML report) but never added
to the JSON, which stays exactly the provided schema. The checks answer: are
required fields missing, do any dates look invalid, are there duplicate records,
where did each value come from, and how much should we trust it?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import cost_appears_in
from .schema import UniversityData

_MONTHS = (
    "january february march april may june july august "
    "september october november december jan feb mar apr jun jul aug sep oct nov dec"
).split()


def _looks_like_date(text: str) -> bool:
    low = text.lower()
    if any(m in low for m in _MONTHS):
        return True
    if re.search(r"\b20\d{2}\b", text):  # a year
        return True
    return bool(re.search(r"\b\d{1,2}[/-]\d{1,2}\b", text))  # 11/1, 1-15


def _snippet(forms: list[str], page_text: list[tuple[str, str]], by_digits: bool = False) -> dict | None:
    """Find the source URL and exact line where a value first appears (a citation).

    `forms` are alternate string renderings of the value (e.g. "11,466" / "11466").
    With `by_digits`, the match compares digit-only strings (for phone numbers).
    """
    for url, text in page_text:
        for line in text.splitlines():
            hay = re.sub(r"\D", "", line) if by_digits else line
            for f in forms:
                needle = re.sub(r"\D", "", f) if by_digits else f
                if needle and needle in hay:
                    return {"source": url, "snippet": line.strip()[:160]}
    return None


@dataclass
class QualityReport:
    missing_fields: list[str] = field(default_factory=list)
    invalid_dates: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    field_sources: dict[str, list[str]] = field(default_factory=dict)  # field -> source URLs
    confidence: dict[str, str] = field(default_factory=dict)  # field -> high|medium|low
    citations: list[dict] = field(default_factory=list)  # field -> {value, source, snippet}

    @property
    def issue_count(self) -> int:
        return len(self.missing_fields) + len(self.invalid_dates) + len(self.duplicates)

    @property
    def ok(self) -> bool:
        return self.issue_count == 0

    def as_dict(self) -> dict:
        return {
            "issue_count": self.issue_count,
            "missing_fields": self.missing_fields,
            "invalid_dates": self.invalid_dates,
            "duplicates": self.duplicates,
            "field_sources": self.field_sources,
            "confidence": self.confidence,
            "citations": self.citations,
        }


def assess(data: UniversityData, pages: list, method: str) -> QualityReport:
    """Run quality checks and build attribution/confidence for one result.

    `pages` is the list of CrawledPage objects actually used for extraction.
    """
    rep = QualityReport()
    page_text = [(p.result.url, p.result.text) for p in pages]

    ov = data.overview
    name = ov.university_name if ov else None
    con = ov.contact if ov else None
    loc = ov.location if ov else None

    # --- missing required-ish fields ------------------------------------
    if not name:
        rep.missing_fields.append("overview.university_name")
    if not (con and (con.phone or con.email)):
        rep.missing_fields.append("overview.contact")
    if not (loc and (loc.city or loc.state or loc.postal_code)):
        rep.missing_fields.append("overview.location")
    if not data.tuition_breakdown:
        rep.missing_fields.append("tuition_breakdown")
    if not data.admission_deadlines:
        rep.missing_fields.append("admission_deadlines")

    # --- invalid dates ---------------------------------------------------
    for d in data.admission_deadlines:
        if d.deadline_date and not _looks_like_date(d.deadline_date):
            rep.invalid_dates.append(d.deadline_date)

    # --- duplicate records ----------------------------------------------
    seen: set[tuple] = set()
    for t in data.tuition_breakdown:
        key = ((t.fee_type or "").lower(), t.cost)
        if key in seen:
            rep.duplicates.append(f"tuition: {t.fee_type} = {t.cost}")
        seen.add(key)
    seen_d: set[tuple] = set()
    for d in data.admission_deadlines:
        dkey = (d.deadline_type, d.deadline_date)
        if dkey in seen_d:
            rep.duplicates.append(f"deadline: {d.deadline_type} / {d.deadline_date}")
        seen_d.add(dkey)

    # --- source attribution ---------------------------------------------
    if con and con.phone:
        digits = re.sub(r"\D", "", con.phone)
        srcs = [u for u, t in page_text if digits and digits in re.sub(r"\D", "", t)]
        if srcs:
            rep.field_sources["contact.phone"] = srcs
    if con and con.email:
        srcs = [u for u, t in page_text if con.email.lower() in t.lower()]
        if srcs:
            rep.field_sources["contact.email"] = srcs

    # --- confidence ------------------------------------------------------
    # Grounded values are present verbatim on a fetched page; the LLM path with
    # full grounding is treated as high confidence, the heuristic path as medium.
    grounded = sum(
        1
        for t in data.tuition_breakdown
        if t.cost is not None and any(cost_appears_in(t.cost, txt) for _, txt in page_text)
    )
    base = "high" if method == "gemini" else "medium"
    rep.confidence["overall"] = base if data.tuition_breakdown else "low"
    rep.confidence["tuition_grounded"] = f"{grounded}/{len(data.tuition_breakdown)}"
    rep.confidence["method"] = method

    # --- citations (evidence spans) -------------------------------------
    # The exact source line each value came from. Capped for tuition so the side
    # artifact stays a reasonable size on schools with huge cost matrices.
    for t in data.tuition_breakdown[:25]:
        if t.cost is None:
            continue
        cit = _snippet([f"{t.cost:,}", str(t.cost)], page_text)
        if cit:
            rep.citations.append({"field": f"tuition: {t.fee_type}", "value": t.cost, **cit})
    if con and con.phone:
        cit = _snippet([con.phone], page_text, by_digits=True)
        if cit:
            rep.citations.append({"field": "contact.phone", "value": con.phone, **cit})
    if con and con.email:
        cit = _snippet([con.email], page_text)
        if cit:
            rep.citations.append({"field": "contact.email", "value": con.email, **cit})

    return rep
