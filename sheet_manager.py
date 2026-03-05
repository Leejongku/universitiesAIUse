"""
sheet_manager.py
Manages all Google Sheets interactions: initialisation, reading, and writing.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

SPREADSHEET_NAME = "대학_AI_현황"
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Sheet → expected headers
SHEET_HEADERS: dict[str, list[str]] = {
    "universities": ["name", "alias", "domain"],
    "articles": ["university", "title", "url", "date", "collected_at"],
    "ai_pages": ["university", "title", "url", "collected_at"],
}


# ──────────────────────────────────────────────
# SheetManager
# ──────────────────────────────────────────────

class SheetManager:
    """
    Thin wrapper around gspread.
    Handles authentication, sheet initialisation, and CRUD helpers.
    """

    def __init__(self, credentials_path: Optional[Path] = None):
        self._cred_path = credentials_path or CREDENTIALS_FILE
        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None
        self._url_cache: dict[str, set[str]] = {}

    # ── Public API ────────────────────────────

    def connect(self) -> None:
        """Authenticate and open (or create) the spreadsheet."""
        logger.info("Connecting to Google Sheets …")
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            str(self._cred_path), SCOPES
        )
        self._client = gspread.authorize(credentials)
        self._spreadsheet = self._open_or_create_spreadsheet()
        self._ensure_sheets()
        self._warm_url_cache()
        logger.info("Google Sheets connection established.")

    def save_universities(self, universities: list[dict]) -> None:
        """Write the full university list to the 'universities' sheet (idempotent)."""
        ws = self._worksheet("universities")
        existing = self._get_all_values_as_sets(ws, col_index=0)

        rows_to_add = []
        for uni in universities:
            if uni["name"] not in existing:
                rows_to_add.append([uni["name"], uni.get("alias", ""), uni.get("domain", "")])

        if rows_to_add:
            ws.append_rows(rows_to_add, value_input_option="RAW")
            logger.info("Saved %d new universities to sheet.", len(rows_to_add))
        else:
            logger.info("University sheet already up to date.")

    def save_article(self, university: str, title: str, url: str, date: str) -> bool:
        """
        Append an article row. Returns True if inserted, False if duplicate.
        """
        if self._is_duplicate("articles", url):
            logger.debug("Duplicate article, skipping: %s", url)
            return False

        ws = self._worksheet("articles")
        row = [university, title, url, date, _now()]
        try:
            ws.append_row(row, value_input_option="RAW")
            self._cache_url("articles", url)
            logger.info("Saving article to Google Sheets | %s | %s", university, title[:60])
            return True
        except gspread.exceptions.APIError as exc:
            logger.error("Google Sheets API error (articles): %s", exc)
            return False

    def save_ai_page(self, university: str, title: str, url: str) -> bool:
        """
        Append an AI page row. Returns True if inserted, False if duplicate.
        """
        if self._is_duplicate("ai_pages", url):
            logger.debug("Duplicate AI page, skipping: %s", url)
            return False

        ws = self._worksheet("ai_pages")
        row = [university, title, url, _now()]
        try:
            ws.append_row(row, value_input_option="RAW")
            self._cache_url("ai_pages", url)
            logger.info("Saved AI page | %s | %s", university, url)
            return True
        except gspread.exceptions.APIError as exc:
            logger.error("Google Sheets API error (ai_pages): %s", exc)
            return False

    def get_existing_article_urls(self) -> set[str]:
        """Return all article URLs currently stored in the sheet."""
        return set(self._url_cache.get("articles", set()))

    def get_existing_ai_page_urls(self) -> set[str]:
        return set(self._url_cache.get("ai_pages", set()))

    # ── Private helpers ────────────────────────

    def _open_or_create_spreadsheet(self) -> gspread.Spreadsheet:
        try:
            spreadsheet = self._client.open(SPREADSHEET_NAME)
            logger.info("Opened existing spreadsheet: %s", SPREADSHEET_NAME)
            return spreadsheet
        except gspread.exceptions.SpreadsheetNotFound:
            spreadsheet = self._client.create(SPREADSHEET_NAME)
            logger.info("Created new spreadsheet: %s", SPREADSHEET_NAME)
            return spreadsheet

    def _ensure_sheets(self) -> None:
        """Create any missing worksheets and write headers."""
        existing_titles = {ws.title for ws in self._spreadsheet.worksheets()}

        for sheet_name, headers in SHEET_HEADERS.items():
            if sheet_name not in existing_titles:
                ws = self._spreadsheet.add_worksheet(
                    title=sheet_name, rows=1000, cols=len(headers)
                )
                ws.append_row(headers, value_input_option="RAW")
                logger.info("Created sheet '%s' with headers.", sheet_name)
            else:
                # Ensure header row exists
                ws = self._spreadsheet.worksheet(sheet_name)
                current_headers = ws.row_values(1)
                if not current_headers:
                    ws.insert_row(headers, index=1)

        # Remove the default blank "Sheet1" if it exists
        try:
            blank = self._spreadsheet.worksheet("Sheet1")
            self._spreadsheet.del_worksheet(blank)
        except gspread.exceptions.WorksheetNotFound:
            pass

    def _warm_url_cache(self) -> None:
        """Pre-load existing URLs from sheets to enable fast duplicate checking."""
        for sheet_name in ("articles", "ai_pages"):
            ws = self._worksheet(sheet_name)
            all_rows = ws.get_all_values()
            if not all_rows:
                self._url_cache[sheet_name] = set()
                continue
            # Find 'url' column index
            headers = all_rows[0]
            try:
                url_col = headers.index("url")
            except ValueError:
                self._url_cache[sheet_name] = set()
                continue

            urls = {row[url_col] for row in all_rows[1:] if len(row) > url_col and row[url_col]}
            self._url_cache[sheet_name] = urls
            logger.debug("Cached %d URLs from sheet '%s'.", len(urls), sheet_name)

    def _worksheet(self, name: str) -> gspread.Worksheet:
        return self._spreadsheet.worksheet(name)

    def _is_duplicate(self, sheet_name: str, url: str) -> bool:
        return url in self._url_cache.get(sheet_name, set())

    def _cache_url(self, sheet_name: str, url: str) -> None:
        self._url_cache.setdefault(sheet_name, set()).add(url)

    @staticmethod
    def _get_all_values_as_sets(ws: gspread.Worksheet, col_index: int) -> set[str]:
        """Return a set of all values in a specific column (excluding header)."""
        all_rows = ws.get_all_values()
        if len(all_rows) <= 1:
            return set()
        return {row[col_index] for row in all_rows[1:] if len(row) > col_index and row[col_index]}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
