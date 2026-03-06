"""
sheet_manager.py
Google Sheets manager for AI university crawler
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

SPREADSHEET_NAME = "대학_AI_현황"

CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = {
    "universities": ["name", "alias", "domain"],
    "articles": ["university", "title", "url", "date", "collected_at"],
    "ai_pages": ["university", "official_status", "ai_model", "platform", "application_area", "partner", "title", "url", "collected_at"],
    "policies": ["university", "title", "url", "collected_at"],
}


# ---------------------------------------------------------
# Sheet Manager
# ---------------------------------------------------------

class SheetManager:

    def __init__(self, credentials_path: Optional[Path] = None):

        self._cred_path = credentials_path or CREDENTIALS_FILE
        self._client = None
        self._spreadsheet = None
        self._url_cache = {}

    # -----------------------------------------------------

    def connect(self):

        logger.info("Connecting to Google Sheets ...")

        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            str(self._cred_path),
            SCOPES,
        )

        self._client = gspread.authorize(credentials)

        # 반드시 기존 시트 열기
        try:

            self._spreadsheet = self._client.open(SPREADSHEET_NAME)

            logger.info("Opened spreadsheet: %s", SPREADSHEET_NAME)

        except gspread.exceptions.SpreadsheetNotFound:

            raise Exception(
                f"""
Google Sheet '{SPREADSHEET_NAME}' not found.

1️⃣ Google Drive에서 새 Sheet 생성
2️⃣ 이름을 정확히 '{SPREADSHEET_NAME}' 로 설정
3️⃣ 아래 서비스 계정 이메일 공유 (편집자 권한)

service account:
{credentials.service_account_email}
"""
            )

        self._ensure_sheets()

        self._warm_url_cache()

        logger.info("Google Sheets ready.")

    # -----------------------------------------------------

    def save_universities(self, universities):

        ws = self._worksheet("universities")

        existing = self._get_column_values(ws, 0)

        rows = []

        for uni in universities:

            if uni["name"] not in existing:

                rows.append([
                    uni["name"],
                    uni.get("alias", ""),
                    uni.get("domain", ""),
                ])

        if rows:

            ws.append_rows(rows)

            logger.info("Saved %d universities", len(rows))

    # -----------------------------------------------------

    def save_article(self, university, title, url, date):

        if self._is_duplicate("articles", url):

            return False

        ws = self._worksheet("articles")

        row = [
            university,
            title,
            url,
            date,
            self._now(),
        ]

        ws.append_row(row)

        self._cache_url("articles", url)

        logger.info("Saved article | %s | %s", university, title[:50])

        return True

    # -----------------------------------------------------

    def save_ai_page(self, university, title, url):

        if self._is_duplicate("ai_pages", url):

            return False

        ws = self._worksheet("ai_pages")

        row = [
            university,
            title,
            url,
            self._now(),
        ]

        ws.append_row(row)

        self._cache_url("ai_pages", url)

        logger.info("Saved AI page | %s", url)

        return True

    # -----------------------------------------------------

    def save_ai_pages_batch(self, ai_pages: list[dict]) -> int:
        ws = self._worksheet("ai_pages")
        rows_to_append = []
        count = 0

        for item in ai_pages:
            url = item.get("url")
            if self._is_duplicate("ai_pages", url):
                continue
            
            rows_to_append.append([
                item.get("university"),
                item.get("official_status", ""),
                item.get("ai_model", ""),
                item.get("platform", ""),
                item.get("application_area", ""),
                item.get("partner", ""),
                item.get("title"),
                url,
                self._now()
            ])
            self._cache_url("ai_pages", url)
            count += 1
            
        if rows_to_append:
            ws.append_rows(rows_to_append)
            logger.info("Batch saved %d AI pages", count)
            
        return count

    # -----------------------------------------------------

    def save_ai_policy(self, university, title, url):

        if self._is_duplicate("policies", url):

            return False

        ws = self._worksheet("policies")

        row = [
            university,
            title,
            url,
            self._now(),
        ]

        ws.append_row(row)

        self._cache_url("policies", url)

        logger.info("Saved AI policy | %s", url)

        return True

    # -----------------------------------------------------

    def save_ai_policies_batch(self, policies: list[dict]) -> int:
        ws = self._worksheet("policies")
        rows_to_append = []
        count = 0

        for item in policies:
            url = item.get("url")
            if self._is_duplicate("policies", url):
                continue
            
            rows_to_append.append([
                item.get("university"),
                item.get("title"),
                url,
                self._now()
            ])
            self._cache_url("policies", url)
            count += 1
            
        if rows_to_append:
            ws.append_rows(rows_to_append)
            logger.info("Batch saved %d AI policies", count)
            
        return count

    # -----------------------------------------------------

    def clear_sheet_data(self, sheet_name: str):
        """Clears all data in the specified sheet except for the header row."""
        try:
            ws = self._worksheet(sheet_name)
            # Find how many rows exist
            rows = ws.get_all_values()
            if len(rows) > 1:
                # Delete rows starting from the second row (index 2 in 1-based gspread)
                # up to the total number of rows.
                ws.delete_rows(2, len(rows))
                logger.info("Cleared %d existing rows from '%s'", len(rows) - 1, sheet_name)
            
            # Ensure headers match current code configuration
            if sheet_name in SHEET_HEADERS:
                try:
                    # Gspread 6.0+ syntax
                    ws.update(values=[SHEET_HEADERS[sheet_name]], range_name='A1')
                except TypeError:
                    # Older gspread syntax
                    ws.update('A1', [SHEET_HEADERS[sheet_name]])
            
            # Reset cache for this sheet
            self._url_cache[sheet_name] = set()
            return True
        except Exception as e:
            logger.warning("Failed to clear sheet '%s': %s", sheet_name, e)
            return False

    # -----------------------------------------------------

    def save_global_news(self, news_items):
        self.clear_sheet_data("articles")
        
        ws = self._worksheet("articles")
        count = 0
        rows_to_append = []
        for item in news_items:
            if self._is_duplicate("articles", item.url):
                continue
            row = [
                "전체",
                item.title,
                item.url,
                item.published,
                self._now(),
            ]
            ws.append_row(row)
            self._cache_url("articles", item.url)
            count += 1
        
        logger.info("Saved %d global news items", count)
        return count

    # -----------------------------------------------------
    # Helpers
    # -----------------------------------------------------

    def _ensure_sheets(self):

        existing = {ws.title for ws in self._spreadsheet.worksheets()}

        for name, headers in SHEET_HEADERS.items():

            if name not in existing:

                ws = self._spreadsheet.add_worksheet(
                    title=name,
                    rows=2000,
                    cols=len(headers),
                )

                ws.append_row(headers)

                logger.info("Created sheet '%s'", name)

    # -----------------------------------------------------

    def _warm_url_cache(self):

        for sheet_name in ["articles", "ai_pages"]:

            ws = self._worksheet(sheet_name)

            rows = ws.get_all_values()

            if len(rows) <= 1:

                self._url_cache[sheet_name] = set()

                continue

            headers = rows[0]

            if "url" not in headers:

                self._url_cache[sheet_name] = set()

                continue

            url_index = headers.index("url")

            urls = set()

            for r in rows[1:]:

                if len(r) > url_index:

                    urls.add(r[url_index])

            self._url_cache[sheet_name] = urls

    # -----------------------------------------------------

    def _worksheet(self, name):

        return self._spreadsheet.worksheet(name)

    # -----------------------------------------------------

    def _get_column_values(self, ws, index):

        rows = ws.get_all_values()

        values = set()

        for r in rows[1:]:

            if len(r) > index:

                values.add(r[index])

        return values

    # -----------------------------------------------------

    def _is_duplicate(self, sheet, url):

        return url in self._url_cache.get(sheet, set())

    # -----------------------------------------------------

    def _cache_url(self, sheet, url):

        self._url_cache.setdefault(sheet, set()).add(url)

    # -----------------------------------------------------

    @staticmethod
    def _now():

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    def get_existing_article_urls(self):

        return set(self._url_cache.get("articles", set()))


    def get_existing_ai_page_urls(self):

        return set(self._url_cache.get("ai_pages", set()))        