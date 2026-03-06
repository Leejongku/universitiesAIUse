"""
crawler.py
Main entry point for AI University Monitor crawler.

Usage examples:
  python crawler.py                 # 서비스 + 정책만 실행
  python crawler.py --news          # 뉴스 포함 실행
  python crawler.py --news --dry-run
"""
# from news_collector import run_news_pipeline
import argparse
import csv
import logging
from pathlib import Path

from ai_service_crawler import AIServiceCrawler
from ai_policy_crawler import AIPolicyCrawler
from news_collector import collect_global_top_ai_news

from sheet_manager import SheetManager

# -------------------------------------------------
# Logging
# -------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Config
# -------------------------------------------------

BASE_DIR = Path(__file__).parent
UNIVERSITIES_FILE = BASE_DIR / "universities.csv"

# -------------------------------------------------
# Load universities
# -------------------------------------------------

def load_universities():
    universities = []

    if not UNIVERSITIES_FILE.exists():
        raise FileNotFoundError("universities.csv not found")

    with open(UNIVERSITIES_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            universities.append(
                {
                    "name": row.get("name"),
                    "alias": row.get("alias"),
                    "domain": row.get("domain"),
                }
            )

    logger.info("Loaded %s universities", len(universities))

    return universities


# -------------------------------------------------
# Main
# -------------------------------------------------

def main():

    parser = argparse.ArgumentParser(description="AI University Monitor crawler")

    parser.add_argument(
        "--news",
        action="store_true",
        help="Enable news crawling",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving to Google Sheets",
    )

    args = parser.parse_args()

    logger.info("======================================")
    logger.info("AI University Monitor Crawler Start")
    logger.info("======================================")

    # 1️⃣ 대학 목록 로드
    universities = load_universities()

    # 2️⃣ Google Sheets 연결
    sheet = SheetManager()
    sheet.connect()

    sheet.save_universities(universities)

    # -------------------------------------------------
    # NEWS CRAWLER (OPTIONAL)
    # -------------------------------------------------

    if args.news:

        logger.info("")
        logger.info("뉴스 수집 시작")

        if not args.dry_run:
            news_items = collect_global_top_ai_news(20)
            sheet.clear_sheet_data("articles")
            saved = sheet.save_global_news(news_items)
            logger.info("글로벌 AI 뉴스 저장 완료: %s개", saved)

    else:
        logger.info("")
        logger.info("뉴스 크롤링 건너뜀 (--news 옵션 없음)")

    # -------------------------------------------------
    # AI SERVICE CRAWLER
    # -------------------------------------------------

    logger.info("")
    logger.info("AI 서비스 탐지 시작")

    ai_crawler = AIServiceCrawler(universities)
    services_raw = ai_crawler.run()   # 새로운 통합 메서드 (KB + 공지 크롤링)
    logger.info("AI 서비스 %s개 발견", len(services_raw))

    # run() 출력 키(kb_ai_model 등) → save_ai_pages_batch 입력 키로 변환
    services = []
    for item in services_raw:
        notice_summary = " | ".join(item.get("notice_titles", [])[:2])
        uni_domain = next((u["domain"] for u in universities if u["name"] == item.get("university")), "")
        services.append({
            "university":      item.get("university"),
            "official_status": item.get("official_status", "확인 중"),
            "ai_model":        item.get("kb_ai_model", "-"),
            "platform":        item.get("kb_platform", "-"),
            "application_area": item.get("kb_application_area", "-"),
            "partner":         item.get("kb_partner", "-"),
            "title":           notice_summary or "(KB 기반 데이터)",
            "url":             item.get("policy_url") or f"https://{uni_domain}",
        })

    if not args.dry_run:
        sheet.clear_sheet_data("ai_pages")
        saved_services = sheet.save_ai_pages_batch(services)
        logger.info("AI 서비스 %s개 저장 완료", saved_services)

    # -------------------------------------------------
    # AI POLICY CRAWLER
    # -------------------------------------------------

    logger.info("")
    logger.info("AI 정책 탐지 시작")

    policy_crawler = AIPolicyCrawler(universities)
    policies = policy_crawler.crawl()
    logger.info("AI 정책 %s개 발견", len(policies))

    if not args.dry_run:
        sheet.clear_sheet_data("policies")
        saved_policies = sheet.save_ai_policies_batch(policies)
        logger.info("AI 정책 %s개 저장 완료", saved_policies)

    logger.info("")
    logger.info("======================================")
    logger.info("Crawler Finished")
    logger.info("======================================")


# -------------------------------------------------

if __name__ == "__main__":
    main()