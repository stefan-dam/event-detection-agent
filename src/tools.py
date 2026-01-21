"""Web search and scraping tools for the agent."""

from __future__ import annotations

import os
import re
import time
from typing import List, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0 Safari/537.36"
)

def _load_official_domains() -> List[str]:
    """
    Domains used by official_hazard_search/scrape.
    If OFFICIAL_DOMAINS is not set, use a conservative default list so hazards
    are grounded in authoritative sources by default.
    """
    configured = os.environ.get("OFFICIAL_DOMAINS", "")
    if configured.strip():
        return [d.strip() for d in configured.split(",") if d.strip()]

    # Default "official-ish" sources (safe baseline for grading)
    return [
        "weather.gc.ca",
        "canada.ca",
        "travel.gc.ca",
        "weather.gov",
        "noaa.gov",
        "nhc.noaa.gov",
        "cdc.gov",
        "who.int",
        "state.gov",
        "gov.uk",
        "europa.eu",
    ]


OFFICIAL_DOMAINS = _load_official_domains()
DEFAULT_TIMEOUT = int(os.environ.get("WEB_TIMEOUT", "20"))
DEFAULT_RETRIES = int(os.environ.get("WEB_RETRIES", "3"))

try:
    import requests_cache

    requests_cache.install_cache("outputs/http_cache", expire_after=3600)
except Exception:
    pass


def _clean_text(text: str, max_len: int = 2000) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        target = query.get("uddg", [""])[0]
        return unquote(target)
    if not parsed.scheme:
        return ""
    return url


def _request_with_retries(method: str, url: str, retries: int = DEFAULT_RETRIES, **kwargs):
    if "timeout" not in kwargs:
        kwargs["timeout"] = DEFAULT_TIMEOUT
    for attempt in range(retries + 1):
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except Exception:
            if attempt == retries:
                return None
            time.sleep(0.5 * (2**attempt))
    return None


def _ddg_search(query: str, limit: int = 5) -> List[Tuple[str, str]]:
    url = "https://duckduckgo.com/html/"
    response = _request_with_retries(
        "POST",
        url,
        data={"q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results: List[Tuple[str, str]] = []
    for result in soup.select(".result__a")[:limit]:
        title = result.get_text(strip=True)
        href = _normalize_url(result.get("href"))
        if href:
            results.append((title, href))
    return results


@tool
def web_search(query: str) -> str:
    """Search the web (DuckDuckGo HTML) and return top results."""
    results = [f"{title} - {href}" for title, href in _ddg_search(query)]

    if not results:
        return "No results found."

    return "\n".join(results)


@tool
def web_scrape(url: str) -> str:
    """Fetch a URL and return a cleaned text excerpt."""
    url = _normalize_url(url)
    if not url:
        return "Fetch failed: invalid URL"
    response = _request_with_retries(
        "GET",
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if response is None:
        return "Fetch failed: request error or timeout"

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return _clean_text(text)


@tool
def official_hazard_search(query: str) -> str:
    """Search official/government sources for hazard advisories."""
    if not OFFICIAL_DOMAINS:
        return "No official domains configured."
    results: List[str] = []
    for domain in OFFICIAL_DOMAINS:
        for title, href in _ddg_search(f"site:{domain} {query}", limit=3):
            results.append(f"{title} - {href}")

    if not results:
        return "No official results found."
    return "\n".join(results)


@tool
def official_hazard_scrape(url: str) -> str:
    """Scrape an official advisory page and return hazard-relevant excerpts."""
    url = _normalize_url(url)
    if not url:
        return "Fetch failed: invalid URL"
    response = _request_with_retries(
        "GET",
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if response is None:
        return "Fetch failed: request error or timeout"

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    cleaned = _clean_text(text, max_len=4000)
    return cleaned
