"""
university_matcher.py
Handles loading university data and matching university names/aliases in text.
"""

import csv
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class University:
    name: str
    alias: str
    domain: str
    # All tokens (name + alias) used for matching
    tokens: list[str] = field(default_factory=list)

    def __post_init__(self):
        tokens = set()
        tokens.add(self.name)
        if self.alias:
            tokens.add(self.alias)
        self.tokens = sorted(tokens, key=len, reverse=True)  # longest first


class UniversityMatcher:
    """
    Loads university list from CSV and detects mentions in text.
    Supports both full names and aliases.
    """

    CSV_PATH = Path(__file__).parent / "universities.csv"

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = csv_path or self.CSV_PATH
        self.universities: list[University] = []
        self._load()

    def _load(self):
        if not self.csv_path.exists():
            raise FileNotFoundError(f"University CSV not found: {self.csv_path}")

        with open(self.csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uni = University(
                    name=row["name"].strip(),
                    alias=row.get("alias", "").strip(),
                    domain=row.get("domain", "").strip(),
                )
                self.universities.append(uni)

        logger.info("Loaded %d universities from %s", len(self.universities), self.csv_path)

    def find_in_text(self, text: str) -> list[University]:
        """
        Return a deduplicated list of universities found in the given text.
        Matches both full names and aliases (longest token first to avoid partial matches).
        """
        if not text:
            return []

        found: dict[str, University] = {}

        for uni in self.universities:
            if uni.name in found:
                continue
            for token in uni.tokens:
                if token and token in text:
                    found[uni.name] = uni
                    logger.debug("Matched university '%s' via token '%s'", uni.name, token)
                    break

        return list(found.values())

    def all_universities(self) -> list[University]:
        return list(self.universities)

    def get_by_name(self, name: str) -> Optional[University]:
        for uni in self.universities:
            if uni.name == name or uni.alias == name:
                return uni
        return None
