from dataclasses import dataclass

from unidata.quality import assess
from unidata.schema import (
    AdmissionDeadline,
    Contact,
    DeadlineType,
    Location,
    Overview,
    TuitionItem,
    UniversityData,
)


@dataclass
class _Result:
    url: str
    text: str


@dataclass
class _Page:
    result: _Result


def _pages():
    return [
        _Page(_Result("https://x.edu/tuition", "Tuition is $11,466. Call 410-543-6161.")),
    ]


def test_flags_missing_and_invalid_and_duplicates():
    data = UniversityData(
        overview=Overview(university_name=None, location=Location(), contact=Contact()),
        tuition_breakdown=[
            TuitionItem(fee_type="Tuition", cost=11466),
            TuitionItem(fee_type="Tuition", cost=11466),  # duplicate
        ],
        admission_deadlines=[
            AdmissionDeadline(deadline_type=DeadlineType.REGULAR_DECISION, deadline_date="garbage text"),
        ],
    )
    q = assess(data, _pages(), method="gemini")
    assert "overview.university_name" in q.missing_fields
    assert "overview.contact" in q.missing_fields
    assert q.invalid_dates == ["garbage text"]
    assert len(q.duplicates) == 1
    assert q.issue_count >= 3


def test_attribution_and_confidence():
    data = UniversityData(
        overview=Overview(
            university_name="X University",
            location=Location(state="MD"),
            contact=Contact(phone="410-543-6161"),
        ),
        tuition_breakdown=[TuitionItem(fee_type="Tuition", cost=11466)],
        admission_deadlines=[
            AdmissionDeadline(deadline_type=DeadlineType.EARLY_DECISION, deadline_date="Nov 1, 2025")
        ],
    )
    q = assess(data, _pages(), method="gemini")
    assert q.confidence["overall"] == "high"
    assert q.confidence["tuition_grounded"] == "1/1"
    # phone is on the page, so it gets attributed to a source URL
    assert q.field_sources["contact.phone"] == ["https://x.edu/tuition"]
    assert q.ok  # no missing/invalid/duplicate issues here
