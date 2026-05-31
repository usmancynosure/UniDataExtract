"""End-to-end orchestration: domain in, validated UniversityData out.

`run` returns a `PipelineResult` so the CLI/UI can show run metadata (extractor
used, domain, how many pages were crawled) WITHOUT polluting the output JSON —
`result.data` is exactly the provided schema and nothing more.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from .config import CrawlSettings
from .crawl import CrawledPage, crawl, select_sources
from .extractors import GeminiExtractor, HeuristicExtractor, ground
from .schema import PageMetadata, UniversityData

log = logging.getLogger("unidata.pipeline")


@dataclass
class PipelineResult:
    data: UniversityData  # exactly the provided schema
    method: str  # gemini | heuristic
    domain: str
    homepage_url: str
    pages_crawled: int


def run(
    domain: str,
    settings: CrawlSettings | None = None,
    use_llm: bool = True,
    on_page: Callable | None = None,
) -> PipelineResult:
    """Run extract -> transform -> load for one university domain."""
    settings = settings or CrawlSettings()

    # --- Extract: discover + crawl --------------------------------------
    homepage_url, pages = crawl(domain, settings, on_page=on_page)
    sources = select_sources(pages, settings)
    log.info(
        "selected %d admissions / %d tuition page(s) from %d fetched",
        len(sources["admissions"]),
        len(sources["tuition"]),
        len(pages),
    )

    # --- Transform: Gemini with deterministic fallback ------------------
    extractor = _choose_extractor(settings, use_llm)
    core = extractor.extract(sources)
    method = extractor.method
    if core is None:  # LLM failed at runtime -> fall back
        fallback = HeuristicExtractor(settings)
        core = fallback.extract(sources)
        method = fallback.method

    # Grounding: drop any value that does not actually appear on the fetched
    # pages, so nothing hallucinated by the LLM survives into the output.
    used = sources["homepage"] + sources["admissions"] + sources["tuition"]
    source_text = "\n".join(p.result.text for p in used)
    core = ground(core, source_text)

    # --- Load: assemble + validate --------------------------------------
    data = UniversityData(page_metadata=_page_metadata(used), **core)
    return PipelineResult(
        data=data,
        method=method,
        domain=domain,
        homepage_url=homepage_url,
        pages_crawled=len(pages),
    )


def _choose_extractor(settings, use_llm: bool):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if use_llm and api_key:
        try:
            return GeminiExtractor(settings, api_key=api_key)
        except Exception as exc:  # SDK missing / bad key
            log.warning("Could not init Gemini (%s); using heuristic extractor", exc)
    elif use_llm:
        log.warning("No GEMINI_API_KEY set; using heuristic extractor")
    return HeuristicExtractor(settings)


def _page_metadata(pages: list[CrawledPage]) -> list[PageMetadata]:
    meta: list[PageMetadata] = []
    seen: set[str] = set()
    for p in pages:
        if p.result.url in seen:
            continue
        seen.add(p.result.url)
        meta.append(
            PageMetadata(
                url=p.result.url,
                page_title=p.result.title,
                scraped_at=p.result.fetched_at.isoformat(),
                status_code=str(p.result.status),
            )
        )
    return meta
