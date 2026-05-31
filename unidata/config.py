"""Tunable settings and the keyword vocabulary that drives page discovery.

Keeping the keywords in one place means the discovery logic stays declarative:
to support a new kind of page you add words here, not branches in the crawler.
"""

from __future__ import annotations

from dataclasses import dataclass, field

USER_AGENT = (
    "UniDataExtractBot/1.0 (+ETL coursework crawler; contact: example@example.com)"
)

# Words that, when they appear in a URL slug or anchor text, suggest the page is
# about admissions or about tuition/cost. Weighted: a hit in the URL path is a
# much stronger signal than a hit in free-floating link text.
ADMISSIONS_KEYWORDS = [
    "admission",
    "admissions",
    "apply",
    "applying",
    "application",
    "first-year",
    "freshman",
    "transfer",
    "undergraduate-admission",
    "how-to-apply",
    "requirements",
    "deadline",
    "deadlines",
    "dates",
]

TUITION_KEYWORDS = [
    "tuition",
    "cost",
    "costs",
    "cost-of-attendance",
    "fees",
    "fee",
    "financial-aid",
    "affordability",
    "net-price",
    "price",
    "billing",
    "bursar",
    "student-accounts",
    "paying",
    "expenses",
    "rates",
]

# Slugs that almost never carry the data we want; expanding these wastes budget.
NEGATIVE_KEYWORDS = [
    "news",
    "event",
    "events",
    "blog",
    "story",
    "stories",
    "athletics",
    "sports",
    "give",
    "giving",
    "donate",
    "alumni",
    "calendar/athletics",
    "directory",
    "search",
]

# URL fragments that indicate an authentication-gated area. We never fetch these.
AUTH_URL_MARKERS = [
    "/login",
    "/log-in",
    "/signin",
    "/sign-in",
    "/auth",
    "/sso",
    "/saml",
    "/shibboleth",
    "/idp",
    "/oauth",
    "/portal",
    "/account",
    "/my.",
    "myaccount",
    "okta",
    "/secure/",
]


@dataclass
class CrawlSettings:
    max_depth: int = 2
    # Hard ceiling on total pages fetched, to keep a run fast and polite.
    max_pages: int = 30
    # How many of the highest-scoring links we expand from any single page.
    max_links_per_page: int = 12
    request_timeout: float = 15.0
    # Seconds to pause between requests to the same host.
    crawl_delay: float = 0.5
    respect_robots: bool = True
    # When True, fetch pages through a headless browser (Playwright) so that
    # JavaScript-rendered tuition tables / deadline widgets are captured. Off by
    # default: the requests backend is lighter and handles the common case.
    render: bool = False
    # How many pages of each category we hand to the extractor. Kept at 3 so a
    # "tuition" hub plus the actual cost-of-attendance table both make the cut.
    pages_per_category: int = 3
    # Characters of cleaned text passed to the LLM per page (cost guard).
    max_chars_per_page: int = 12000

    # Keyword tables, copied in so a caller can override per run if needed.
    admissions_keywords: list[str] = field(default_factory=lambda: list(ADMISSIONS_KEYWORDS))
    tuition_keywords: list[str] = field(default_factory=lambda: list(TUITION_KEYWORDS))
    negative_keywords: list[str] = field(default_factory=lambda: list(NEGATIVE_KEYWORDS))
