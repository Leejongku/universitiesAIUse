"""
article_parser.py
Fetches article URLs and extracts readable text content.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Reasonable timeout and delay for polite crawling
REQUEST_TIMEOUT = 15  # seconds
FETCH_DELAY = 1.0     # seconds between requests
MAX_CONTENT_LENGTH = 500_000  # bytes – skip huge pages

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

# Tags whose content we discard (navigation, ads, etc.)
NOISE_TAGS = [
    "script", "style", "header", "footer", "nav",
    "aside", "form", "noscript", "iframe", "button",
]


@dataclass
class ArticleContent:
    url: str
    title: str
    text: str
    ok: bool = True
    error: str = ""


def fetch_article(url: str) -> ArticleContent:
    """
    Fetch a news article URL and return its cleaned text content.
    Never raises – errors are captured in ArticleContent.ok / .error.
    """
    try:
        time.sleep(FETCH_DELAY)
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        if len(response.content) > MAX_CONTENT_LENGTH:
            logger.warning("Page too large, skipping: %s", url)
            return ArticleContent(url=url, title="", text="", ok=False, error="page_too_large")

        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return ArticleContent(url=url, title="", text="", ok=False, error="non_html_content")

        title, text = _parse_html(response.text, url)
        return ArticleContent(url=url, title=title, text=text)

    except requests.exceptions.Timeout:
        logger.warning("Timeout fetching: %s", url)
        return ArticleContent(url=url, title="", text="", ok=False, error="timeout")
    except requests.exceptions.TooManyRedirects:
        logger.warning("Too many redirects: %s", url)
        return ArticleContent(url=url, title="", text="", ok=False, error="too_many_redirects")
    except requests.exceptions.RequestException as exc:
        logger.warning("Network error for %s: %s", url, exc)
        return ArticleContent(url=url, title="", text="", ok=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error parsing %s: %s", url, exc)
        return ArticleContent(url=url, title="", text="", ok=False, error=str(exc))


def _parse_html(html: str, url: str) -> tuple[str, str]:
    """
    Parse raw HTML and return (title, cleaned_text).
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Remove noise tags in-place
        for tag in soup(NOISE_TAGS):
            tag.decompose()

        # Try to find main content area
        body_text = _extract_main_content(soup)

        return title, body_text

    except Exception as exc:  # noqa: BLE001
        logger.warning("HTML parse error for %s: %s", url, exc)
        return "", ""


def _extract_main_content(soup: BeautifulSoup) -> str:
    """
    Attempt to extract the main article body text using heuristics.
    Falls back to full body text.
    """
    # Priority selectors for Korean news sites and general article pages
    candidates = [
        soup.find("article"),
        soup.find(id="article-body"),
        soup.find(id="articleBody"),
        soup.find(id="newsContent"),
        soup.find(id="content"),
        soup.find(class_="article-body"),
        soup.find(class_="news-content"),
        soup.find(class_="article_body"),
        soup.find(attrs={"itemprop": "articleBody"}),
    ]

    for candidate in candidates:
        if candidate:
            text = candidate.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    # Fallback: entire body
    body = soup.find("body")
    if body:
        return body.get_text(separator=" ", strip=True)

    return soup.get_text(separator=" ", strip=True)
