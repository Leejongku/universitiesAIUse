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
    "ai_pages": ["university", "title", "url", "collected_at"],
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