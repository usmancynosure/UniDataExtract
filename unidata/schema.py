"""Output schema for the ETL pipeline.

The assignment refers to a "provided Pydantic schema" that was not attached, so
this is a self-designed schema that covers every field the task asks for:
university overview + contact, a tuition/cost breakdown, admission deadlines,
and metadata for every page used as a source.

Design notes:
- Almost every field is Optional and defaults to None. The pipeline must return
  null when a value cannot be extracted with reasonable confidence rather than
  guessing, so the schema makes "missing" the natural, valid state.
- Money is stored as float in a single currency (default USD). Dates are stored
  twice: a normalized `date` when the full date is known, and the raw text so we
  never lose information or invent a year that wasn't on the page.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PageMetadata(BaseModel):
    """Provenance for one page the pipeline fetched and used."""

    url: str
    title: str | None = None
    page_type: str = "other"  # homepage | admissions | tuition | other
    depth: int = 0
    http_status: int
    fetched_at: datetime
    content_sha1: str | None = None
    word_count: int | None = None
    relevance_score: float | None = None


class ContactInfo(BaseModel):
    phone: str | None = None
    email: str | None = None
    mailing_address: str | None = None
    admissions_office_url: str | None = None


class TuitionItem(BaseModel):
    """One row of a cost-of-attendance breakdown.

    A university usually has several of these (undergrad in-state vs out-of-state,
    graduate, etc.), so the output holds a list rather than a single object.
    """

    student_type: str | None = None  # undergraduate | graduate
    residency: str | None = None  # in_state | out_of_state | international
    academic_year: str | None = None  # e.g. "2024-2025"
    tuition: float | None = None
    fees: float | None = None
    room_and_board: float | None = None
    books_and_supplies: float | None = None
    total_cost_of_attendance: float | None = None
    currency: str = "USD"
    note: str | None = None


class AdmissionDeadline(BaseModel):
    name: str  # "Early Decision I", "Regular Decision", "Transfer", ...
    applicant_type: str | None = None  # first_year | transfer | international | graduate
    deadline: date | None = None  # set only when the full date (incl. year) is known
    deadline_text: str | None = None  # raw text exactly as found on the page
    notification_date: date | None = None


class UniversityData(BaseModel):
    """Top-level extraction result for a single university."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    domain: str
    homepage_url: str
    overview: str | None = None
    contact: ContactInfo = Field(default_factory=ContactInfo)
    tuition: list[TuitionItem] = Field(default_factory=list)
    admission_deadlines: list[AdmissionDeadline] = Field(default_factory=list)
    sources: list[PageMetadata] = Field(default_factory=list)

    extraction_method: str = "heuristic"  # gemini | heuristic
    extracted_at: datetime
