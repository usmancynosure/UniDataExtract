from unidata.report import to_html, to_markdown
from unidata.schema import (
    AdmissionDeadline,
    Contact,
    DeadlineType,
    Location,
    Overview,
    TuitionItem,
    UniversityData,
)


def _data():
    return UniversityData(
        overview=Overview(
            university_name="Test University",
            location=Location(city="Lewisburg", state="PA", postal_code="17837"),
            contact=Contact(phone="570-577-3000", email="admissions@test.edu"),
        ),
        tuition_breakdown=[TuitionItem(fee_type="Tuition", cost=11466, currency="USD")],
        admission_deadlines=[
            AdmissionDeadline(deadline_type=DeadlineType.EARLY_DECISION, deadline_date="Nov 1, 2025")
        ],
    )


def test_html_report_is_self_contained():
    html = to_html(_data(), "test.edu")
    assert html.startswith("<!doctype html>")
    assert "Test University" in html
    assert "$11,466" in html
    assert "http" not in html.split("<style>")[1].split("</style>")[0]  # no external assets in CSS


def test_markdown_report_has_sections():
    md = to_markdown(_data(), "test.edu")
    assert md.startswith("# Test University")
    for heading in ("## Overview", "## Tuition / Cost", "## Admission deadlines", "## Sources"):
        assert heading in md
