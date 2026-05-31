<div align="center">

# 🎓 UniDataExtract

**An ETL pipeline that turns a single university domain into structured Admissions & Tuition data.**

[![CI](https://img.shields.io/badge/CI-passing-brightgreen)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

`domain ─► discover + crawl (depth ≤ 2) ─► extract (Gemini → heuristic) ─► validate ─► JSON`

</div>

---

Give it `bucknell.edu` and it finds the right Admissions and Tuition/Cost pages **on its own**
(no hardcoded URLs), extracts the data, and emits a JSON document that is guaranteed valid
against a Pydantic schema. Comes with a `rich` CLI **and** a Streamlit web UI.

## 🎥 Demo

<!--
  HOW TO ADD THE VIDEO (pick one):

  A) MP4 with audio (recommended): on GitHub, edit this README (or open an Issue) and
     DRAG your .mp4/.mov into the editor. GitHub uploads it and inserts a URL like
     https://github.com/user-attachments/assets/xxxx — paste that URL on the line below.

  B) GIF committed to the repo: drop docs/demo.gif in the repo and uncomment the line below.
-->

<!-- A) paste the GitHub attachment URL on its own line here -->

<!-- B) ![UniCompanion demo](docs/demo.gif) -->

> _Demo video coming soon — run `streamlit run app.py` to try it live._

## ✨ Highlights

- **Discovery, not hardcoding** — pages are found by scoring link URLs + anchor text, so the
  same code works on any school. Crawl depth is capped at 2.
- **Two extractors, one interface** — Google **Gemini** (structured JSON) with a **deterministic
  regex/heuristic fallback** that needs no API key. The output schema is identical either way.
- **Pluggable fetch backend** — fast `requests` by default; `--render` swaps in **Playwright**
  (headless Chromium) for JavaScript-heavy pages.
- **Robust & polite** — honors `robots.txt`, throttles, retries 5xx, stays on-domain
  (incl. subdomains), and **skips authentication-gated pages** three different ways.
- **Grounded, never fabricates** — every field is `Optional` and defaults to `null`, and a
  **grounding pass drops any LLM value (cost, phone, email, postal) that isn't actually present
  on the fetched pages**. Tuition-page selection prefers pages that really list dollar figures.
- **Shareable reports** — generate a self-contained **HTML / Markdown** report per university
  (`--report html`) with costs grouped by category.
- **Full provenance** — every page used is recorded with URL, type, depth, HTTP status,
  SHA-1, word count, and relevance score.

## 🚀 Quickstart

```bash
make install            # venv + core deps     (or: python -m venv .venv && pip install -r requirements.txt)
cp .env.example .env     # add your free Gemini key from aistudio.google.com/apikey (optional)

python main.py bucknell.edu                      # pretty CLI
python main.py bucknell.edu salisbury.edu udc.edu --out-dir samples
python main.py bucknell.edu --json > out.json    # machine-readable
python main.py bucknell.edu --no-llm             # offline, deterministic
python main.py bucknell.edu --report html --out-dir samples   # + shareable HTML report
```

### Web interface

```bash
pip install -r requirements-ui.txt
streamlit run app.py     # or: make ui
```

Enter a domain, watch the crawl discover pages live, and browse / download the result.

### JavaScript rendering (optional)

```bash
pip install -r requirements-render.txt && playwright install chromium
python main.py bucknell.edu --render
```

CLI flags: `--out-dir`, `--json`, `--no-llm`, `--render`, `--max-depth` (2), `--max-pages` (30), `-v`.

## 🧭 How it works

| Stage | Module(s) | What happens |
|------|-----------|--------------|
| **Extract** | `fetch.py`, `discover.py`, `crawl.py` | Read the homepage + `sitemap.xml`; **score** every link by URL-slug/anchor keywords; **priority-BFS** the best ones (depth ≤ 2, page budget). |
| **Transform** | `extractors.py`, `normalize.py` | Clean pages → text → **Gemini** (or heuristic fallback) → one normalized dict. Cost → int, email guarded for `EmailStr`, deadlines mapped to the allowed enum. |
| **Load** | `schema.py`, `pipeline.py` | Assemble into `UniversityData`, **validate with Pydantic**, attach `PageMetadata` for every source. |

### Key design decisions

- **URL-slug hits weigh ~3× anchor-text hits**; specific keywords (`cost-of-attendance`) beat
  generic ones (`cost`); shallow paths get a hub bonus; junk sections (`news`, `athletics`,
  `give`) are penalized.
- **Priority BFS over blind BFS** — a max-heap on relevance means a small page budget still
  lands on the right pages.
- **Subdomain-aware scope** — many schools host admissions on `admissions.<school>.edu`.
- **Auth skipped 3 ways** — URL patterns (`/login`, `/sso`, `/portal`…), HTTP 401/403 + login
  redirects, and a rendered `<input type=password>`.
- **One shared normalizer** so LLM and heuristic output are byte-for-byte comparable and the
  "return null, don't guess" rule is enforced in exactly one place.

### How the LLM is used

Gemini (`gemini-2.5-flash`, temperature 0) does **only the transform step** — it reads
already-cleaned text and returns JSON. It never decides what to crawl, fetches nothing, and is
forbidden by both prompt and schema from inventing values. With no key, the heuristic extractor
takes over and the pipeline still produces valid output.

## ✅ Quality

```bash
make check    # ruff + mypy + pytest (the full gate)
make test     # offline unit tests (scoring, normalization, grounding, report)
```

Fully type-checked (`mypy`), `ruff`-clean, and CI runs all three on Python 3.10–3.12.

## 📁 Project structure

```
UniDataExtract/
├── main.py                  # convenience entry point
├── app.py                   # Streamlit web interface
├── unidata/                 # the package
│   ├── cli.py               #   rich-powered command line
│   ├── console.py           #   result rendering
│   ├── config.py            #   settings + keyword vocabulary
│   ├── fetch.py             #   HTTP / Playwright, robots, auth detection, cleaning
│   ├── discover.py          #   link relevance scoring
│   ├── crawl.py             #   priority BFS (depth ≤ 2) + source selection
│   ├── extractors.py        #   Gemini + heuristic extractors, shared normalizer, grounding
│   ├── normalize.py         #   money / contact / deadline parsing
│   ├── present.py           #   fee categorization + currency formatting (CLI/UI/report)
│   ├── report.py            #   standalone HTML / Markdown report generator
│   ├── schema.py            #   provided Pydantic output models
│   └── pipeline.py          #   extract → transform → load
├── tests/                   # offline unit tests
├── samples/                 # example outputs for the 3 reference schools
├── pyproject.toml           # packaging + tooling (installs the `unidata` command)
├── Makefile                 # install / test / lint / run / ui
├── requirements*.txt        # core · render · ui dependency sets
└── .github/workflows/ci.yml # lint + test on 3.10–3.12
```

## ⚠️ Assumptions & limitations

- Targets US `.edu` sites; registrable-domain check uses the last two labels (a production
  build would use the public-suffix list / `tldextract`).
- Defaults to static HTML; use `--render` for JavaScript-rendered pages. **PDF extraction is
  out of scope** (per the brief) — such figures come back `null` rather than wrong.
- Input is a **domain**, not a name. The brief says "starting only from the provided domain,"
  and a name→domain step would need a search engine, so it is intentionally omitted.
- The heuristic fallback reliably gets overview/name/contact; tuition tables and deadlines are
  much stronger via the LLM. The fallback exists for resilience, not parity.

## 📄 Output schema

The output conforms exactly to the provided Pydantic schema ([`unidata/schema.py`](unidata/schema.py)):

```
UniversityData
├── overview
│   ├── university_name
│   ├── location: { city, state, country, postal_code }
│   └── contact:  { phone, email (EmailStr) }
├── tuition_breakdown[]:   { fee_type, cost (int), currency }
├── admission_deadlines[]: { deadline_type, deadline_date, notes }
└── page_metadata[]:       { url, page_title, scraped_at, status_code }
```

- `deadline_type` is an **enum** — only `Early Decision`, `Regular Decision`, or
  `Transfer Admission`. Variants like "Early Decision II" are mapped to the nearest value
  with the specifics preserved in `notes`; anything outside the three (e.g. "Early Action")
  is dropped rather than mis-typed.
- The pipeline emits **only** these fields. Run metadata (which extractor ran, relevance
  scores) is shown in the CLI/UI but kept out of the JSON so it matches the schema exactly.

A sample for each reference university lives in [`samples/`](samples/).

## License

MIT — see [LICENSE](LICENSE).
