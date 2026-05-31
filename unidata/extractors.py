"""Transform step: turn fetched pages into structured fields.

Two extractors share one interface:

* `GeminiExtractor`  - LLM with structured-JSON output (primary, when a key is set)
* `HeuristicExtractor` - regex/keyword parsing (deterministic fallback, no key needed)

Both emit the same intermediate dict, which `assemble_core` normalizes into typed
Pydantic objects. That keeps normalization in one place regardless of source.
"""

from __future__ import annotations

import json
import logging
import os

from bs4 import BeautifulSoup

from .normalize import (
    find_email,
    find_phone,
    normalize_academic_year,
    to_date,
    to_money,
)
from .schema import AdmissionDeadline, ContactInfo, TuitionItem

log = logging.getLogger("unidata.extract")


# --------------------------------------------------------------------------
# Shared normalization: raw dict -> typed, validated field objects
# --------------------------------------------------------------------------

def assemble_core(raw: dict, fallback_admissions_url: str | None) -> dict:
    """Normalize a raw extraction dict into Pydantic-ready field values."""
    contact_raw = raw.get("contact") or {}
    contact = ContactInfo(
        phone=_clean_str(contact_raw.get("phone")),
        email=_clean_str(contact_raw.get("email")),
        mailing_address=_clean_str(contact_raw.get("mailing_address")),
        admissions_office_url=_clean_str(contact_raw.get("admissions_office_url"))
        or fallback_admissions_url,
    )

    tuition: list[TuitionItem] = []
    for row in raw.get("tuition") or []:
        item = TuitionItem(
            student_type=_clean_str(row.get("student_type")),
            residency=_clean_str(row.get("residency")),
            academic_year=normalize_academic_year(row.get("academic_year")),
            tuition=to_money(row.get("tuition")),
            fees=to_money(row.get("fees")),
            room_and_board=to_money(row.get("room_and_board")),
            books_and_supplies=to_money(row.get("books_and_supplies")),
            total_cost_of_attendance=to_money(row.get("total_cost_of_attendance")),
            currency=(row.get("currency") or "USD"),
            note=_clean_str(row.get("note")),
        )
        # Drop rows that carry no actual numbers.
        if any(
            v is not None
            for v in (
                item.tuition,
                item.fees,
                item.room_and_board,
                item.books_and_supplies,
                item.total_cost_of_attendance,
            )
        ):
            tuition.append(item)

    deadlines: list[AdmissionDeadline] = []
    for row in raw.get("admission_deadlines") or []:
        name = _clean_str(row.get("name"))
        if not name:
            continue
        text = _clean_str(row.get("deadline_text"))
        deadlines.append(
            AdmissionDeadline(
                name=name,
                applicant_type=_clean_str(row.get("applicant_type")),
                deadline=to_date(row.get("deadline") or text),
                deadline_text=text,
                notification_date=to_date(row.get("notification_date")),
            )
        )

    return {
        "name": _clean_str(raw.get("name")),
        "overview": _clean_str(raw.get("overview")),
        "contact": contact,
        "tuition": tuition,
        "admission_deadlines": deadlines,
    }


def _clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_document(sources: dict, settings) -> str:
    """Concatenate the selected pages into one labeled document for the LLM."""
    blocks: list[str] = []
    for category in ("homepage", "admissions", "tuition"):
        for page in sources.get(category, []):
            text = page.result.text[: settings.max_chars_per_page]
            blocks.append(
                f"=== PAGE ({category}) {page.result.url} ===\n{text}"
            )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# LLM extractor
# --------------------------------------------------------------------------

PROMPT = """You are a precise data extraction system for US university websites.
From the page text below, extract admissions and tuition/cost information.

Return ONLY a JSON object with exactly this shape:
{
  "name": string|null,                // official university name
  "overview": string|null,            // 1-3 sentence description of the school
  "contact": {
    "phone": string|null,             // admissions office phone
    "email": string|null,             // admissions office email
    "mailing_address": string|null,
    "admissions_office_url": string|null
  },
  "tuition": [                        // one object per cost scenario found
    {
      "student_type": "undergraduate"|"graduate"|null,
      "residency": "in_state"|"out_of_state"|"international"|null,
      "academic_year": string|null,   // e.g. "2024-2025"
      "tuition": number|null,
      "fees": number|null,
      "room_and_board": number|null,
      "books_and_supplies": number|null,
      "total_cost_of_attendance": number|null,
      "currency": "USD",
      "note": string|null
    }
  ],
  "admission_deadlines": [
    {
      "name": string,                 // e.g. "Early Decision", "Regular Decision"
      "applicant_type": "first_year"|"transfer"|"international"|"graduate"|null,
      "deadline_text": string|null,   // the date exactly as written on the page
      "deadline": string|null,        // ISO YYYY-MM-DD ONLY if the year is shown
      "notification_date": string|null
    }
  ]
}

Hard rules:
- Use null (or [] for the lists) whenever a value is not clearly stated. Never guess.
- Do NOT invent a year. If the page says "November 1" with no year, set "deadline": null
  and keep "deadline_text": "November 1".
- All money is a plain number with no symbols or commas (e.g. 58212), currency USD.
- Output JSON only, no markdown, no commentary.

PAGE TEXT:
"""


class GeminiExtractor:
    method = "gemini"

    def __init__(self, settings, api_key: str, model: str | None = None):
        from google import genai  # imported lazily so the heuristic path needs no SDK

        self.settings = settings
        self.client = genai.Client(api_key=api_key)
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    def extract(self, sources: dict, fallback_admissions_url: str | None) -> dict | None:
        document = _build_document(sources, self.settings)
        if not document.strip():
            return None
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=PROMPT + document,
                config={"response_mime_type": "application/json", "temperature": 0.0},
            )
            raw = json.loads(_strip_code_fence(resp.text))
        except Exception as exc:  # network, quota, or malformed JSON
            log.warning("Gemini extraction failed (%s); falling back to heuristics", exc)
            return None
        return assemble_core(raw, fallback_admissions_url)


def _strip_code_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


# --------------------------------------------------------------------------
# Deterministic fallback extractor
# --------------------------------------------------------------------------

class HeuristicExtractor:
    method = "heuristic"

    def __init__(self, settings):
        self.settings = settings

    def extract(self, sources: dict, fallback_admissions_url: str | None) -> dict:
        homepage = (sources.get("homepage") or [None])[0]
        admissions_pages = sources.get("admissions", [])
        tuition_pages = sources.get("tuition", [])

        name, overview = None, None
        if homepage:
            name, overview = _name_and_overview(homepage.result)

        contact_text = "\n".join(
            p.result.text for p in (admissions_pages or []) + ([homepage] if homepage else [])
        )
        contact = {
            "phone": find_phone(contact_text),
            "email": find_email(contact_text),
            "mailing_address": None,
            "admissions_office_url": fallback_admissions_url,
        }

        tuition = []
        for page in tuition_pages:
            tuition.extend(_tuition_rows(page.result.text))
            if tuition:
                break  # one good page is enough for the deterministic path

        deadlines = []
        for page in admissions_pages:
            deadlines.extend(_deadline_rows(page.result.text))
            if deadlines:
                break

        raw = {
            "name": name,
            "overview": overview,
            "contact": contact,
            "tuition": tuition,
            "admission_deadlines": deadlines,
        }
        return assemble_core(raw, fallback_admissions_url)


def _name_and_overview(result) -> tuple[str | None, str | None]:
    soup = BeautifulSoup(result.html, "lxml")
    name = None
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        name = og_site["content"].strip()
    elif result.title:
        # "Home | Bucknell University" -> "Bucknell University"
        name = result.title.split("|")[-1].split("-")[-1].strip() or result.title

    overview = None
    desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description"
    )
    if desc and desc.get("content"):
        overview = desc["content"].strip()
    return name, overview


# A label followed by a dollar amount, e.g. "Tuition .... $58,212".
_LABELS = {
    "tuition": "tuition",
    "fees": "fees",
    "room_and_board": "room_and_board",
    "books_and_supplies": "books_and_supplies",
    "total_cost_of_attendance": "total_cost_of_attendance",
}


def _tuition_rows(text: str) -> list[dict]:
    row: dict = {"currency": "USD", "student_type": "undergraduate"}
    for line in text.splitlines():
        low = line.lower()
        money = to_money(line) if "$" in line else None
        if money is None:
            continue
        if "room" in low and "board" in low:
            row.setdefault("room_and_board", money)
        elif "book" in low or "supplies" in low:
            row.setdefault("books_and_supplies", money)
        elif "total" in low or "cost of attendance" in low:
            row.setdefault("total_cost_of_attendance", money)
        elif "fee" in low and "tuition" not in low:
            row.setdefault("fees", money)
        elif "tuition" in low:
            row.setdefault("tuition", money)
    return [row] if len(row) > 2 else []


_DEADLINE_HINTS = ("deadline", "due", "apply by", "application", "decision", "priority")


def _deadline_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        # A real deadline line is short, label-like, and starts cleanly — this
        # filters out the sentence fragments that line-splitting produces.
        if len(line) > 110 or not line[:1].isalnum():
            continue
        if not any(h in low for h in _DEADLINE_HINTS) or not _has_month(low):
            continue
        if line in seen:
            continue
        seen.add(line)
        rows.append({"name": line[:80], "deadline_text": line, "deadline": line})
        if len(rows) >= 8:
            break
    return rows


_MONTHS = (
    "january february march april may june july august "
    "september october november december"
).split()


def _has_month(low: str) -> bool:
    return any(m in low for m in _MONTHS)
