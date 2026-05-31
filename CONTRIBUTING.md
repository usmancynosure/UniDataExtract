# Contributing

Thanks for taking a look. This project is a small, self-contained ETL pipeline; the
goal is readable, well-typed code with fast offline tests.

## Setup

```bash
make install-all      # venv + core/render/ui/dev dependencies
make render-setup     # (optional) download Chromium for --render
cp .env.example .env  # (optional) add a Gemini key
```

## Before you push

```bash
make check            # ruff + mypy + pytest  (all must pass)
```

- **Lint/format:** `ruff` (`make lint`, `make format`). Line length 100.
- **Types:** `mypy` (`make typecheck`). The package is fully typed; new code should be too.
- **Tests:** `pytest` (`make test`). Tests must stay **offline** — no network. Mock or feed
  fixed inputs to extractors/normalizers instead of hitting real sites or the LLM.

## Where things live

| Area | Module |
|---|---|
| Crawl / discovery | `unidata/{fetch,discover,crawl}.py` |
| Extraction + normalization | `unidata/{extractors,normalize}.py` |
| Output schema | `unidata/schema.py` (provided — keep field names exact) |
| Presentation (CLI/UI/report) | `unidata/{console,present,report}.py` |
| Orchestration | `unidata/pipeline.py` |

## Conventions

- The JSON output must match `unidata/schema.py` exactly — don't add fields to it. Run
  metadata belongs on `PipelineResult`, not in the document.
- Never fabricate: prefer `null` over a guess, and keep the grounding pass (`extractors.ground`)
  intact so no value survives that isn't on the page.
- Add keywords in `unidata/config.py` rather than branching in the crawler.
