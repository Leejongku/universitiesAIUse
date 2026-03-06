"""
news_collector.py
Fetches Google News RSS feeds and discovers official university AI pages.
"""

import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Google News RSS
# ──────────────────────────────────────────────

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
NEWS_QUERIES = [
    "생성형 AI 기술 추세",
    "ChatGPT 최신 동향",
    "클로드 (Claude) AI 업데이트",
    "구글 제미나이",
    "온디바이스 AI",
    "AI 온톨로지 (Ontology) 및 지식 그래프 실무 활용",
]

FETCH_DELAY = 2.0  # seconds between RSS fetches (be polite)
REQUEST_TIMEOUT = 15


@dataclass
class NewsItem:
    title: str
    url: str
    published: str
    summary: str = ""


@dataclass
class AIPage:
    university: str
    title: str
    url: str


# ──────────────────────────────────────────────
# News RSS collector
# ──────────────────────────────────────────────

class NewsCollector:
    """Collects articles from Google News RSS for a list of queries."""

    def __init__(self, queries: Optional[list[str]] = None, delay: float = FETCH_DELAY):
        self.queries = queries or NEWS_QUERIES
        self.delay = delay

    def collect(self) -> list[NewsItem]:
        """
        Iterate over all queries and return a deduplicated list of NewsItem.
        """
        seen_urls: set[str] = set()
        items: list[NewsItem] = []

        for query in self.queries:
            logger.info("Searching news for keyword: %s", query)
            batch = self._fetch_rss(query)
            logger.info("Found %d articles for query '%s'", len(batch), query)

            for item in batch:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    items.append(item)

            time.sleep(self.delay)

        logger.info("Total unique articles collected: %d", len(items))
        return items

    def _fetch_rss(self, query: str) -> list[NewsItem]:
        params = {
            "q": query,
            "hl": "ko",
            "gl": "KR",
            "ceid": "KR:ko",
        }
        url = f"{GOOGLE_NEWS_RSS}?{urllib.parse.urlencode(params)}"

        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # noqa: BLE001
            logger.error("RSS parse error for query '%s': %s", query, exc)
            return []

        items = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "").strip()
            summary = entry.get("summary", "").strip()

            if not link:
                continue

            # Google News links are sometimes redirect URLs – keep as-is;
            # the article_parser will follow redirects.
            items.append(NewsItem(
                title=title,
                url=link,
                published=published,
                summary=summary,
            ))

        return items


# ──────────────────────────────────────────────
# AI page discovery (site:ac.kr search via Bing)
# ──────────────────────────────────────────────

AI_PAGE_QUERIES = [
    '"{name}" 생성형 AI site:ac.kr',
    '"{name}" ChatGPT site:ac.kr',
    '"{name}" AI 가이드라인 site:ac.kr',
]

BING_SEARCH_URL = "https://www.bing.com/search"
BING_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


class AIPageCollector:
    """
    Discovers official university AI-related pages by scraping Bing search results.

    Note: Google doesn't allow automated scraping of its search results.
    We use Bing as an alternative for site: searches.
    For a more robust solution, integrate the Bing Search API or Google Custom Search API.
    """

    def __init__(self, delay: float = FETCH_DELAY):
        self.delay = delay

    def collect_for_university(self, university_name: str) -> list[AIPage]:
        """Run all AI_PAGE_QUERIES for a single university and return results."""
        pages: list[AIPage] = []
        seen: set[str] = set()

        for template in AI_PAGE_QUERIES:
            query = template.format(name=university_name)
            logger.info("Searching AI pages for: %s (query: %s)", university_name, query)
            results = self._bing_search(query, university_name)

            for page in results:
                if page.url not in seen:
                    seen.add(page.url)
                    pages.append(page)

            time.sleep(self.delay)

        return pages

    def _bing_search(self, query: str, university_name: str) -> list[AIPage]:
        params = {"q": query, "count": "10", "setlang": "ko"}
        try:
            response = requests.get(
                BING_SEARCH_URL,
                params=params,
                headers=BING_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return self._parse_bing_results(response.text, university_name)

        except requests.exceptions.RequestException as exc:
            logger.warning("Bing search failed for '%s': %s", query, exc)
            return []
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in Bing search: %s", exc)
            return []

    @staticmethod
    def _parse_bing_results(html: str, university_name: str) -> list[AIPage]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for result in soup.select("li.b_algo"):
            anchor = result.find("a", href=True)
            if not anchor:
                continue

            link = anchor["href"]
            title_el = result.find("h2")
            title = title_el.get_text(strip=True) if title_el else anchor.get_text(strip=True)

            if not link.startswith("http"):
                continue

            # Only keep .ac.kr domains
            if "ac.kr" not in link:
                continue

            results.append(AIPage(
                university=university_name,
                title=title,
                url=link,
            ))

        return results

# ──────────────────────────────────────────────
# Global AI News Collection
# ──────────────────────────────────────────────

def collect_global_top_ai_news(limit: int = 20) -> list[NewsItem]:
    import email.utils
    import datetime

    queries = [
        "대학 생성형 AI 혁신",
        "생성형 AI 대학 트렌드",
        "인공지능 교육 트렌드",
        "해외 대학 AI 사례",
    ]

    collector = NewsCollector(queries=queries, delay=1.0)
    items = collector.collect()

    def parse_date(date_str: str) -> datetime.datetime:
        try:
            dt_tuple = email.utils.parsedate_tz(date_str)
            if dt_tuple:
                return datetime.datetime.fromtimestamp(
                    email.utils.mktime_tz(dt_tuple), 
                    datetime.timezone.utc
                )
        except Exception:
            pass
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

    items.sort(key=lambda x: parse_date(x.published), reverse=True)
    return items[:limit]
