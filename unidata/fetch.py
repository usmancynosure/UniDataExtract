"""HTTP fetching, robots.txt politeness, HTML cleaning and auth detection.

Everything that touches the network lives here so the crawler can stay focused
on graph traversal and the extractors can work with clean text only.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import AUTH_URL_MARKERS, USER_AGENT


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    status: int
    html: str
    title: str | None
    text: str
    content_sha1: str
    word_count: int
    fetched_at: datetime

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and bool(self.html)


@dataclass
class _RawResponse:
    """Backend-agnostic raw fetch result, before any cleaning or policy checks."""

    final_url: str
    status: int
    content_type: str
    text: str


def registrable_domain(host: str) -> str:
    """Best-effort registrable domain (last two labels).

    Good enough for the ``*.edu`` domains this pipeline targets. A production
    version would use the public suffix list (e.g. tldextract) for ccTLDs.
    """
    host = host.lower().split(":")[0]
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def looks_like_auth_url(url: str) -> bool:
    low = url.lower()
    return any(marker in low for marker in AUTH_URL_MARKERS)


def _clean_html_to_text(soup: BeautifulSoup) -> str:
    """Strip chrome and return readable text, one block per line."""
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe"]):
        tag.decompose()
    # Drop obvious navigation / boilerplate containers.
    for tag in soup.find_all(["nav", "header", "footer", "form"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _has_password_field(soup: BeautifulSoup) -> bool:
    return soup.find("input", attrs={"type": "password"}) is not None


class Fetcher:
    """A polite, robots-aware HTTP client scoped to one site."""

    def __init__(self, settings, base_host: str):
        self.settings = settings
        self.base_host = base_host.lower()
        self.base_registrable = registrable_domain(base_host)
        self._last_request_at = 0.0
        self._robots: robotparser.RobotFileParser | None = None
        self._pw: Any = None  # Playwright context, started lazily (untyped SDK)
        self._pw_browser: Any = None

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        retry = Retry(
            total=2,
            backoff_factor=0.4,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # -- scope / politeness -------------------------------------------------

    def in_scope(self, url: str) -> bool:
        """True if the URL belongs to the target site (incl. subdomains)."""
        host = urlparse(url).hostname or ""
        return registrable_domain(host) == self.base_registrable

    def _load_robots(self) -> None:
        if self._robots is not None or not self.settings.respect_robots:
            return
        rp = robotparser.RobotFileParser()
        robots_url = f"https://{self.base_host}/robots.txt"
        try:
            resp = self.session.get(robots_url, timeout=self.settings.request_timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])  # no robots => allow all
        except requests.RequestException:
            rp.parse([])
        self._robots = rp

    def allowed_by_robots(self, url: str) -> bool:
        if not self.settings.respect_robots:
            return True
        self._load_robots()
        assert self._robots is not None
        return self._robots.can_fetch(USER_AGENT, url)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.settings.crawl_delay - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    # -- fetching -----------------------------------------------------------

    def fetch(self, url: str) -> FetchResult | None:
        """Fetch one HTML page. Returns None for anything we should skip.

        The transport (requests vs. headless browser) is chosen by settings, but
        all the policy — scope, robots, auth, content-type — is applied here so
        both backends behave identically. Pages are skipped when out of scope,
        blocked by robots.txt, non-HTML, authentication-gated, or failed to load.
        """
        if looks_like_auth_url(url) or not self.allowed_by_robots(url):
            return None

        self._throttle()
        raw = self._render_get(url) if self.settings.render else self._requests_get(url)
        if raw is None:
            return None

        # A redirect into an auth flow (or off-site) means the content is gated.
        if looks_like_auth_url(raw.final_url) or not self.in_scope(raw.final_url):
            return None
        if raw.status in (401, 403):
            return None
        if "html" not in raw.content_type.lower():
            return None

        soup = BeautifulSoup(raw.text, "lxml")
        if _has_password_field(soup):
            return None  # login wall rendered with 200

        title = soup.title.string.strip() if soup.title and soup.title.string else None
        text = _clean_html_to_text(soup)
        sha1 = hashlib.sha1(raw.text.encode("utf-8", "ignore")).hexdigest()

        return FetchResult(
            url=raw.final_url,
            status=raw.status,
            html=raw.text,
            title=title,
            text=text,
            content_sha1=sha1,
            word_count=len(text.split()),
            fetched_at=utcnow(),
        )

    # -- transport backends -------------------------------------------------

    def _requests_get(self, url: str) -> _RawResponse | None:
        try:
            resp = self.session.get(
                url, timeout=self.settings.request_timeout, allow_redirects=True
            )
        except requests.RequestException:
            return None
        return _RawResponse(
            final_url=resp.url,
            status=resp.status_code,
            content_type=resp.headers.get("Content-Type", ""),
            text=resp.text,
        )

    def _render_get(self, url: str) -> _RawResponse | None:
        """Fetch via a headless Chromium so client-side content is present."""
        page = self._browser().new_page(user_agent=USER_AGENT)
        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(self.settings.request_timeout * 1000),
            )
            if response is None:
                return None
            # Give late, JS-injected content a brief chance to settle.
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            return _RawResponse(
                final_url=page.url,
                status=response.status,
                content_type=response.headers.get("content-type", "text/html"),
                text=page.content(),
            )
        except Exception:
            return None
        finally:
            page.close()

    def _browser(self):
        """Lazily start Playwright/Chromium the first time it's needed."""
        if self._pw_browser is not None:
            return self._pw_browser
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # surface a clear, actionable message
            raise RuntimeError(
                "Rendering requires Playwright. Install with:\n"
                "    pip install playwright && playwright install chromium"
            ) from exc
        self._pw = sync_playwright().start()
        self._pw_browser = self._pw.chromium.launch(headless=True)
        return self._pw_browser

    def close(self) -> None:
        """Release the browser (no-op when the requests backend was used)."""
        if self._pw_browser is not None:
            self._pw_browser.close()
            self._pw_browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None
        self.session.close()

    def extract_links(self, html: str, base_url: str) -> list[tuple[str, str]]:
        """Return (absolute_url, anchor_text) for in-scope, non-auth links."""
        soup = BeautifulSoup(html, "lxml")
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = str(a["href"]).strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            url = urljoin(base_url, href).split("#")[0].rstrip("/")
            if url in seen or not self.in_scope(url) or looks_like_auth_url(url):
                continue
            seen.add(url)
            out.append((url, a.get_text(" ", strip=True)))
        return out

    def fetch_sitemap_urls(self) -> list[str]:
        """Pull candidate URLs from sitemap.xml / a sitemap index, if present."""
        urls: list[str] = []
        sitemap_url = f"https://{self.base_host}/sitemap.xml"
        try:
            resp = self.session.get(sitemap_url, timeout=self.settings.request_timeout)
            if resp.status_code != 200:
                return urls
            soup = BeautifulSoup(resp.text, "xml")
            # A sitemap index points at child sitemaps; follow a few of them.
            child_maps = [loc.get_text(strip=True) for loc in soup.select("sitemap > loc")]
            if child_maps:
                for child in child_maps[:5]:
                    try:
                        c = self.session.get(child, timeout=self.settings.request_timeout)
                        if c.status_code == 200:
                            csoup = BeautifulSoup(c.text, "xml")
                            urls += [loc.get_text(strip=True) for loc in csoup.select("url > loc")]
                    except requests.RequestException:
                        continue
            else:
                urls += [loc.get_text(strip=True) for loc in soup.select("url > loc")]
        except requests.RequestException:
            return urls
        return [u for u in urls if self.in_scope(u) and not looks_like_auth_url(u)]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
