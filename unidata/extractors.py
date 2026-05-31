"""Transform step: turn fetched pages into the provided schema's fields.

Two extractors share one interface:

* `GeminiExtractor`  - LLM with structured-JSON output (primary, when a key is set)
* `HeuristicExtractor` - regex/keyword parsing (deterministic fallback, no key needed)

Both emit the same intermediate dict, which `assemble_core` normalizes into typed
Pydantic objects (Overview / TuitionItem / AdmissionDeadline). That keeps
normalization in one place regardless of source.
"""

from __future__ import annotations

import json
import logging
import os
import re

from bs4 import BeautifulSoup

from .normalize import (
    find_email,
    find_phone,
    find_postal_code,
    safe_email,
    to_cost,
    to_deadline_type,
)
from .schema import AdmissionDeadline, Contact, Location, Overview, TuitionItem

log = logging.getLogger("unidata.extract")

_MONEY_SUB = re.compile(r"\$\s?[0-9][0-9,]*(?:\.[0-9]{2})?")
_DATE_RE = re.compile(
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:,?\s*20\d{2})?",
    re.IGNORECASE,
)
_MONTHS = (
    "january february march april may june july august "
    "september october november december"
).split()


# --------------------------------------------------------------------------
# Shared normalization: raw dict -> typed, validated field objects
# --------------------------------------------------------------------------

def assemble_core(raw: dict) -> dict:
    """Normalize a raw extraction dict into the schema's field values."""
    ov = raw.get("overview") or {}
    loc = ov.get("location") or {}
    con = ov.get("contact") or {}

    overview = Overview(
        university_name=_clean_str(ov.get("university_name")),
        location=Location(
            city=_clean_str(loc.get("city")),
            state=_clean_str(loc.get("state")),
            country=_clean_str(loc.get("country")),
            postal_code=_clean_str(loc.get("postal_code")),
        ),
        contact=Contact(
            phone=_clean_str(con.get("phone")),
            email=safe_email(con.get("email")),
        ),
    )

    tuition: list[TuitionItem] = []
    seen_fee: set[tuple] = set()
    for row in raw.get("tuition_breakdown") or []:
        cost = to_cost(row.get("cost"))
        fee_type = _clean_str(row.get("fee_type"))
        if cost is None or not fee_type:
            continue  # a cost line needs both a label and a number
        key = (fee_type.lower(), cost)
        if key in seen_fee:
            continue
        seen_fee.add(key)
        tuition.append(
            TuitionItem(fee_type=fee_type, cost=cost, currency=(row.get("currency") or "USD"))
        )

    deadlines: list[AdmissionDeadline] = []
    for row in raw.get("admission_deadlines") or []:
        dtype = to_deadline_type(row.get("deadline_type") or row.get("notes"))
        if dtype is None:
            continue  # strict: only the three allowed enum values are kept
        deadlines.append(
            AdmissionDeadline(
                deadline_type=dtype,
                deadline_date=_clean_str(row.get("deadline_date")),
                notes=_clean_str(row.get("notes")),
            )
        )

    return {
        "overview": overview,
        "tuition_breakdown": tuition,
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
            blocks.append(f"=== PAGE ({category}) {page.result.url} ===\n{text}")
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# LLM extractor
# --------------------------------------------------------------------------

PROMPT = """You are a precise data extraction system for US university websites.
From the page text below, extract the university overview, the tuition/cost
breakdown, and the admission deadlines.

Return ONLY a JSON object with exactly this shape:
{
  "overview": {
    "university_name": string|null,
    "location": { "city": string|null, "state": string|null,
                  "country": string|null, "postal_code": string|null },
    "contact": { "phone": string|null, "email": string|null }
  },
  "tuition_breakdown": [
    { "fee_type": string, "cost": integer, "currency": "USD" }
  ],
  "admission_deadlines": [
    { "deadline_type": "Early Decision"|"Regular Decision"|"Transfer Admission"|null,
      "deadline_date": string|null, "notes": string|null }
  ]
}

Guidance:
- tuition_breakdown: ONE object per line item. Put residency/year context inside
  fee_type, e.g. {"fee_type":"Tuition (in-state)","cost":11466,"currency":"USD"},
  {"fee_type":"Mandatory Fees","cost":900,"currency":"USD"},
  {"fee_type":"Room and Board","cost":18380,"currency":"USD"},
  {"fee_type":"Total Cost of Attendance (in-state)","cost":31496,"currency":"USD"}.
- deadline_type MUST be EXACTLY one of "Early Decision", "Regular Decision",
  "Transfer Admission", or null. Put specifics (e.g. "Early Decision II",
  "Early Action", first-year vs transfer) in notes.

Hard rules:
- Use null (or [] for the lists) whenever a value is not clearly stated. Never guess.
- cost is a plain integer, no symbols or commas (e.g. 58212). currency is "USD".
- deadline_date is the date text as written on the page (e.g. "November 1").
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

    def extract(self, sources: dict) -> dict | None:
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
        return assemble_core(raw)


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

    def extract(self, sources: dict) -> dict:
        homepage = (sources.get("homepage") or [None])[0]
        admissions_pages = sources.get("admissions", [])
        tuition_pages = sources.get("tuition", [])

        name = _name_from_homepage(homepage.result) if homepage else None

        contact_text = "\n".join(
            p.result.text for p in admissions_pages + ([homepage] if homepage else [])
        )
        raw = {
            "overview": {
                "university_name": name,
                "location": {"postal_code": find_postal_code(contact_text)},
                "contact": {
                    "phone": find_phone(contact_text),
                    "email": find_email(contact_text),
                },
            },
            "tuition_breakdown": _tuition_items(tuition_pages),
            "admission_deadlines": _deadline_items(admissions_pages),
        }
        return assemble_core(raw)


def _name_from_homepage(result) -> str | None:
    soup = BeautifulSoup(result.html, "lxml")
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        return og_site["content"].strip()
    if result.title:
        return result.title.split("|")[-1].split("-")[-1].strip() or result.title
    return None


_FEE_HINTS = ("tuition", "fee", "room", "board", "total", "cost of attendance", "book", "supplies")


def _tuition_items(tuition_pages) -> list[dict]:
    items: list[dict] = []
    for page in tuition_pages:
        for line in page.result.text.splitlines():
            line = line.strip()
            if "$" not in line:
                continue
            low = line.lower()
            if not any(h in low for h in _FEE_HINTS):
                continue
            cost = to_cost(line)
            if cost is None:
                continue
            fee_type = _MONEY_SUB.sub("", line).strip(" .:-–\t") or "Cost"
            items.append({"fee_type": fee_type[:80], "cost": cost, "currency": "USD"})
        if items:
            break  # one good page is enough for the deterministic path
    return items


def _deadline_items(admissions_pages) -> list[dict]:
    rows: list[dict] = []
    for page in admissions_pages:
        for line in page.result.text.splitlines():
            line = line.strip()
            low = line.lower()
            if len(line) > 110 or not line[:1].isalnum():
                continue
            if not any(m in low for m in _MONTHS):
                continue
            if to_deadline_type(low) is None:
                continue
            date_match = _DATE_RE.search(line)
            rows.append(
                {
                    "deadline_type": to_deadline_type(low),
                    "deadline_date": date_match.group(0) if date_match else None,
                    "notes": line[:120],
                }
            )
            if len(rows) >= 8:
                return rows
        if rows:
            break
    return rows
