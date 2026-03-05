"""
crawler.py
──────────────────────────────────────────────────────────────
Main entry point for the Korean University AI Monitor Crawler.

Usage:
    python crawler.py [--skip-news] [--skip-pages] [--dry-run]

Options:
    --skip-news    Skip Google News RSS collection
    --skip-pages   Skip official AI page discovery
    --dry-run      Run without writing to Google Sheets (for testing)
──────────────────────────────────────────────────────────────
"""

import argparse
import logging
import sys
from pathlib import Path

from article_parser import fetch_article
from news_collector import NewsCollector, AIPageCollector
from sheet_manager import SheetManager
from university_matcher import UniversityMatcher

# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Path(__file__).parent / "crawler.log", encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Pipeline steps
# ──────────────────────────────────────────────

def run_news_pipeline(
    matcher: UniversityMatcher,
    sheet: SheetManager,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Collect news articles → parse → match universities → save.
    Returns (articles_checked, articles_saved).
    """
    collector = NewsCollector()
    news_items = collector.collect()

    checked = 0
    saved = 0

    for i, item in enumerate(news_items, start=1):
        _progress(i, len(news_items), label="articles")

        # Skip if URL already in sheet
        if item.url in sheet.get_existing_article_urls():
            logger.debug("Already in sheet, skipping: %s", item.url)
            continue

        # Fetch full article content
        content = fetch_article(item.url)
        checked += 1

        if not content.ok:
            logger.debug("Could not fetch article: %s (%s)", item.url, content.error)
            continue

        # Combine title + body for matching
        full_text = f"{item.title} {content.title} {content.text}"
        matched_unis = matcher.find_in_text(full_text)

        if not matched_unis:
            logger.debug("No university matched for: %s", item.title[:60])
            continue

        for uni in matched_unis:
            logger.info("Matched university: %s | %s", uni.name, item.title[:60])
            if not dry_run:
                inserted = sheet.save_article(
                    university=uni.name,
                    title=item.title,
                    url=item.url,
                    date=item.published,
                )
                if inserted:
                    saved += 1
            else:
                logger.info("[DRY RUN] Would save article: %s – %s", uni.name, item.title[:60])
                saved += 1

    return checked, saved


def run_ai_page_pipeline(
    matcher: UniversityMatcher,
    sheet: SheetManager,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Search for official AI pages for each university → save.
    Returns (pages_found, pages_saved).
    """
    page_collector = AIPageCollector()
    found = 0
    saved = 0

    universities = matcher.all_universities()

    for i, uni in enumerate(universities, start=1):
        _progress(i, len(universities), label="universities (AI pages)")
        logger.info("Searching AI pages for: %s", uni.name)

        pages = page_collector.collect_for_university(uni.name)
        found += len(pages)

        for page in pages:
            if page.url in sheet.get_existing_ai_page_urls():
                logger.debug("AI page already saved: %s", page.url)
                continue

            if not dry_run:
                inserted = sheet.save_ai_page(
                    university=page.university,
                    title=page.title,
                    url=page.url,
                )
                if inserted:
                    saved += 1
            else:
                logger.info("[DRY RUN] Would save AI page: %s – %s", uni.name, page.url)
                saved += 1

    return found, saved


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _progress(current: int, total: int, label: str = "") -> None:
    pct = int(current / total * 100) if total else 0
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    sys.stdout.write(f"\r  [{bar}] {pct:3d}% – {current}/{total} {label}  ")
    sys.stdout.flush()
    if current == total:
        sys.stdout.write("\n")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Korean University AI Monitor Crawler"
    )
    parser.add_argument("--skip-news", action="store_true", help="Skip news RSS collection")
    parser.add_argument("--skip-pages", action="store_true", help="Skip AI page discovery")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to Google Sheets (test mode)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    logger.info("=" * 60)
    logger.info("Starting crawler")
    if args.dry_run:
        logger.info("DRY RUN mode – nothing will be written to Google Sheets")
    logger.info("=" * 60)

    # ── 1. Load university data ─────────────────
    matcher = UniversityMatcher()
    logger.info("Loaded %d universities.", len(matcher.all_universities()))

    # ── 2. Connect to Google Sheets ─────────────
    sheet = SheetManager()
    if not args.dry_run:
        try:
            sheet.connect()
        except FileNotFoundError:
            logger.error(
                "credentials.json not found. "
                "Place your Google Service Account credentials at: credentials.json"
            )
            sys.exit(1)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to connect to Google Sheets: %s", exc)
            sys.exit(1)

        # Sync university list to sheet
        uni_dicts = [
            {"name": u.name, "alias": u.alias, "domain": u.domain}
            for u in matcher.all_universities()
        ]
        sheet.save_universities(uni_dicts)
    else:
        logger.info("[DRY RUN] Skipping Google Sheets connection.")

    # ── 3. News pipeline ────────────────────────
    if not args.skip_news:
        logger.info("-" * 40)
        logger.info("Phase 1: News article collection")
        logger.info("-" * 40)
        checked, saved = run_news_pipeline(matcher, sheet, dry_run=args.dry_run)
        logger.info("News pipeline complete. Checked: %d | Saved: %d", checked, saved)
    else:
        logger.info("Skipping news pipeline (--skip-news).")

    # ── 4. AI page discovery ────────────────────
    if not args.skip_pages:
        logger.info("-" * 40)
        logger.info("Phase 2: Official AI page discovery")
        logger.info("-" * 40)
        found, saved_pages = run_ai_page_pipeline(matcher, sheet, dry_run=args.dry_run)
        logger.info("AI page pipeline complete. Found: %d | Saved: %d", found, saved_pages)
    else:
        logger.info("Skipping AI page pipeline (--skip-pages).")

    logger.info("=" * 60)
    logger.info("Crawler finished successfully.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
