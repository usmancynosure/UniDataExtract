"""End-to-end orchestration: domain in, validated UniversityData out."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from urllib.parse import urlparse

from .config import CrawlSettings
from .crawl import CrawledPage, crawl, select_sources
from .extractors import GeminiExtractor, HeuristicExtractor
from .fetch import registrable_domain, utcnow
from .schema import PageMetadata, UniversityData

log = logging.getLogger("unidata.pipeline")


def run(
    domain: str,
    settings: CrawlSettings | None = None,
    use_llm: bool = True,
    on_page: Callable | None = None,
) -> UniversityData:
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

    fallback_admissions_url = (
        sources["admissions"][0].result.url if sources["admissions"] else None
    )

    # --- Transform: Gemini with deterministic fallback ------------------
    extractor = _choose_extractor(settings, use_llm)
    core = extractor.extract(sources, fallback_admissions_url)
    method = extractor.method
    if core is None:  # LLM failed at runtime -> fall back
        fallback = HeuristicExtractor(settings)
        core = fallback.extract(sources, fallback_admissions_url)
        method = fallback.method

    # --- Load: assemble + validate --------------------------------------
    # `sources` records only the pages actually handed to the extractor, in
    # priority order, deduplicated — the provenance of the extracted values.
    used = sources["homepage"] + sources["admissions"] + sources["tuition"]
    base_host = urlparse(homepage_url).hostname or domain
    data = UniversityData(
        domain=registrable_domain(base_host),
        homepage_url=homepage_url,
        sources=_page_metadata(used),
        extraction_method=method,
        extracted_at=utcnow(),
        **core,
    )
    return data


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
                title=p.result.title,
                page_type=p.category,
                depth=p.depth,
                http_status=p.result.status,
                fetched_at=p.result.fetched_at,
                content_sha1=p.result.content_sha1,
                word_count=p.result.word_count,
                relevance_score=round(p.score, 2) if p.category != "homepage" else None,
            )
        )
    return meta
