"""Relevance scoring that turns raw links into ranked admissions/tuition candidates.

This is the heart of "discover the right pages from only a domain". A link is
scored purely from its URL slug and anchor text — no destination URL is ever
hardcoded, so the same logic works for any university.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ScoredLink:
    url: str
    anchor: str
    category: str  # "admissions" | "tuition" | "other"
    score: float


def _keyword_score(haystack: str, keywords: list[str], weight: float) -> float:
    haystack = haystack.lower()
    score = 0.0
    for kw in keywords:
        if kw in haystack:
            # Longer, more specific keywords ("cost-of-attendance") count more
            # than short generic ones ("cost").
            score += weight * (1.0 + 0.15 * kw.count("-"))
    return score


def score_link(url: str, anchor: str, settings) -> ScoredLink:
    path = urlparse(url).path.lower()

    # URL-slug hits are weighted ~3x anchor-text hits: a slug like
    # /admissions/tuition is a far stronger signal than the word "cost"
    # appearing somewhere in a link label.
    adm = _keyword_score(path, settings.admissions_keywords, 3.0)
    adm += _keyword_score(anchor, settings.admissions_keywords, 1.0)

    tui = _keyword_score(path, settings.tuition_keywords, 3.0)
    tui += _keyword_score(anchor, settings.tuition_keywords, 1.0)

    penalty = _keyword_score(path, settings.negative_keywords, 2.5)
    penalty += _keyword_score(anchor, settings.negative_keywords, 0.8)

    # Shallow paths are usually section landing pages ("/admissions/") — nudge
    # them up so we prefer hubs over deep leaf pages of equal keyword weight.
    depth_bonus = max(0.0, 1.5 - 0.3 * path.strip("/").count("/"))

    if tui > adm and tui > 0:
        category, raw = "tuition", tui
    elif adm > 0:
        category, raw = "admissions", adm
    else:
        category, raw = "other", 0.0

    score = max(0.0, raw + depth_bonus - penalty) if raw > 0 else 0.0
    return ScoredLink(url=url, anchor=anchor, category=category, score=score)


def rank_links(links: list[tuple[str, str]], settings) -> list[ScoredLink]:
    """Score and sort (url, anchor) pairs, dropping irrelevant ones."""
    scored = [score_link(url, anchor, settings) for url, anchor in links]
    relevant = [s for s in scored if s.score > 0]
    relevant.sort(key=lambda s: s.score, reverse=True)
    return relevant
