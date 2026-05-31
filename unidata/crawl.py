"""Priority breadth-first crawl, bounded to depth 2.

Rather than crawl blindly, we expand the highest-scoring links first and cap the
fan-out at every node. The result is a small, highly relevant set of pages for a
fraction of the requests a naive BFS would make.
"""

from __future__ import annotations

import heapq
import logging
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from .discover import rank_links, score_link
from .fetch import Fetcher, FetchResult
from .normalize import count_money

log = logging.getLogger("unidata.crawl")


@dataclass
class CrawledPage:
    result: FetchResult
    depth: int
    category: str  # homepage | admissions | tuition | other
    score: float


def crawl(
    domain: str,
    settings,
    on_page: Callable[[CrawledPage], None] | None = None,
) -> tuple[str, list[CrawledPage]]:
    """Crawl from a domain and return (homepage_url, fetched pages).

    The frontier is a max-heap keyed on relevance score, so even though we stop
    after `max_pages` fetches we spend that budget on the most promising links.
    `on_page`, if given, is called with each page as it is fetched (used by the
    CLI to render live progress).
    """
    homepage_url = _homepage_url(domain)
    base_host = urlparse(homepage_url).hostname or domain
    fetcher = Fetcher(settings, base_host)

    visited: set[str] = set()
    pages: list[CrawledPage] = []

    # Max-heap via negated score; counter breaks ties and keeps ordering stable.
    counter = 0
    frontier: list[tuple[float, int, str, int, str]] = []

    def push(url: str, depth: int, score: float, category: str) -> None:
        nonlocal counter
        url = url.split("#")[0].rstrip("/")
        if url in visited or depth > settings.max_depth:
            return
        heapq.heappush(frontier, (-score, counter, url, depth, category))
        counter += 1

    # Seed: the homepage (forced first) plus anything the sitemap reveals.
    push(homepage_url, 0, float("inf"), "homepage")
    for url in fetcher.fetch_sitemap_urls():
        sl = score_link(url, "", settings)
        if sl.score > 0:
            push(url, 1, sl.score, sl.category)

    try:
        while frontier and len(pages) < settings.max_pages:
            neg_score, _, url, depth, category = heapq.heappop(frontier)
            if url in visited:
                continue
            visited.add(url)

            result = fetcher.fetch(url)
            if result is None:
                continue
            # Re-key on the final (post-redirect) URL to avoid duplicate content.
            if result.url.rstrip("/") != url:
                if result.url.rstrip("/") in visited:
                    continue
                visited.add(result.url.rstrip("/"))

            score = 0.0 if category == "homepage" else -neg_score
            page = CrawledPage(result=result, depth=depth, category=category, score=score)
            pages.append(page)
            log.info("fetched [d%d %-10s %.1f] %s", depth, category, score, result.url)
            if on_page is not None:
                on_page(page)

            if depth < settings.max_depth:
                ranked = rank_links(fetcher.extract_links(result.html, result.url), settings)
                for sl in ranked[: settings.max_links_per_page]:
                    push(sl.url, depth + 1, sl.score, sl.category)
    finally:
        fetcher.close()

    return homepage_url, pages


def select_sources(pages: list[CrawledPage], settings) -> dict[str, list[CrawledPage]]:
    """Pick the homepage and the top-N admissions/tuition pages for extraction."""
    homepage = next((p for p in pages if p.category == "homepage"), None)
    admissions = sorted(
        (p for p in pages if p.category == "admissions"),
        key=lambda p: p.score,
        reverse=True,
    )[: settings.pages_per_category]
    # For tuition, a page that actually lists dollar figures beats a higher-scoring
    # landing/calculator page with no numbers, so we rank on (has costs, score).
    tuition = sorted(
        (p for p in pages if p.category == "tuition"),
        key=lambda p: (min(count_money(p.result.text), 8), p.score),
        reverse=True,
    )[: settings.pages_per_category]
    return {
        "homepage": [homepage] if homepage else [],
        "admissions": admissions,
        "tuition": tuition,
    }


def _homepage_url(domain: str) -> str:
    domain = domain.strip()
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    parsed = urlparse(domain)
    return f"{parsed.scheme}://{parsed.netloc}/"
