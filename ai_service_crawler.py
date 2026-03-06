"""
ai_service_crawler.py
─────────────────────
대학별 생성형 AI 도입 현황을 수집하는 크롤러 모듈.

주요 기능
──────────
1. crawl()            : 기존 로직 (홈페이지 AI 링크 탐지) — 하위 호환성 유지
2. crawl_notices()    : 공지사항 페이지에서 생성형 AI 관련 공지 수집
3. crawl_deep()       : AI 관련 하위 페이지까지 깊이 탐색 (최대 depth 2)
4. extract_ai_info()  : 페이지 텍스트에서 플랫폼명·모델명·파트너 자동 추출
5. enrich_from_kb()   : AI_KNOWLEDGE_DB 정보로 결과 보강
6. run()              : 위 모든 기능을 통합 실행 → 최종 결과 반환
"""

import re
import time
import logging
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ai_knowledge import AI_KNOWLEDGE_DB

# ── 로거 설정 ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 상수 ───────────────────────────────────────────────────────────────────

# 생성형 AI 관련 키워드 (URL·링크 텍스트 탐지용)
AI_KEYWORDS = [
    "gpt", "chatgpt", "chatbot", "gemini", "claude", "llm",
    "ai", "챗봇", "생성형", "인공지능", "factchat", "kingogpt",
    "chatkhu", "산지니", "aichat", "cnu ai",
]

# 플랫폼 이름 패턴 (페이지 내용 추출용)
PLATFORM_PATTERNS = [
    r"KingoGPT", r"ChatKHU", r"챗쿠", r"FactChat", r"팩트챗",
    r"산지니\s*AI", r"AIChat", r"UNIAI", r"CNU\s*AI\+",
    r"AI\s*KU", r"COVI", r"Dr\.KU",
    r"Pulley\s*Campus", r"ALLO",
]

# AI 모델명 패턴 (페이지 내용 추출용)
MODEL_PATTERNS = [
    r"GPT-?[34456][\w.]*", r"ChatGPT[\w\s]*", r"Gemini[\w\s]*",
    r"Claude[\w\s.-]*", r"Llama[\w\s.-]*", r"Grok[\w\s]*",
    r"Perplexity", r"Mistral[\w\s]*", r"Qwen[\w\s]*",
    r"Gemma[\w\s]*", r"Solar[\w\s]*", r"HyperCLOVA[\w\s]*",
    r"멀티\s*LLM", r"멀티LLM",
]

# 파트너·업체 패턴
PARTNER_PATTERNS = [
    r"마인드로직", r"Mindlogic", r"Microsoft\s*Azure", r"Azure\s*OpenAI",
    r"KT", r"네이버\s*클라우드", r"Naver\s*Cloud",
    r"OpenAI", r"Google", r"NVIDIA", r"삼성", r"Samsung",
    r"몬드리안\s*AI", r"Mondrian\s*AI",
    r"Upstage", r"업스테이지", r"NC\s*AI",
]

# 가이드라인·정책 관련 키워드 (공지 탐지용)
POLICY_KEYWORDS = [
    "가이드라인", "guideline", "정책", "policy", "지침", "윤리",
    "활용 안내", "ai 서비스", "생성형 ai", "플랫폼 안내",
]

# 공지사항 경로 후보 (대학 홈페이지 내 공지 URL 패턴)
NOTICE_PATH_CANDIDATES = [
    "/notice", "/notices", "/bbs", "/board",
    "/news", "/announcement", "/comm/notice",
    "/kr/notice", "/ko/notice",
]

# HTTP 요청 헤더
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

REQUEST_TIMEOUT = 12   # 초
REQUEST_DELAY   = 0.5  # 연속 요청 간격(초) — 서버 부하 방지


# ── 유틸 함수 ──────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = REQUEST_TIMEOUT) -> requests.Response | None:
    """GET 요청 래퍼 (예외 무시, None 반환)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        logger.debug("GET 실패 [%s]: %s", url, exc)
        return None


def _same_domain(base_url: str, target_url: str) -> bool:
    """두 URL이 같은 도메인인지 확인."""
    return urlparse(base_url).netloc == urlparse(target_url).netloc


def _is_ai_link(href: str, text: str) -> bool:
    """href 또는 링크 텍스트가 AI 키워드를 포함하는지 확인."""
    combined = (href + " " + text).lower()
    return any(kw in combined for kw in AI_KEYWORDS)


def _is_policy_text(text: str) -> bool:
    """텍스트가 가이드라인·정책 관련 내용인지 확인."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in POLICY_KEYWORDS)


# ── 정보 추출 함수 ─────────────────────────────────────────────────────────

def extract_ai_info(text: str) -> dict:
    """
    페이지 본문 텍스트에서 플랫폼명·모델명·파트너를 정규식으로 추출한다.

    Returns
    -------
    dict
        {
          "detected_platforms": list[str],
          "detected_models":    list[str],
          "detected_partners":  list[str],
          "has_guideline":      bool,
          "has_platform":       bool,
        }
    """
    platforms = list({
        m.group() for p in PLATFORM_PATTERNS
        for m in re.finditer(p, text, re.IGNORECASE)
    })
    models = list({
        m.group() for p in MODEL_PATTERNS
        for m in re.finditer(p, text, re.IGNORECASE)
    })
    partners = list({
        m.group() for p in PARTNER_PATTERNS
        for m in re.finditer(p, text, re.IGNORECASE)
    })

    has_guideline = bool(re.search(
        r"가이드라인|지침|정책|guideline|policy", text, re.IGNORECASE
    ))
    has_platform = len(platforms) > 0

    return {
        "detected_platforms": platforms,
        "detected_models":    models,
        "detected_partners":  partners,
        "has_guideline":      has_guideline,
        "has_platform":       has_platform,
    }


# ── 메인 크롤러 클래스 ─────────────────────────────────────────────────────

class AIServiceCrawler:
    """
    대학별 생성형 AI 서비스 정보를 수집하는 크롤러.

    Parameters
    ----------
    universities : list[dict]
        [{"name": "서울대학교", "domain": "www.snu.ac.kr"}, ...]
    """

    def __init__(self, universities: list[dict]):
        self.universities = universities

    # ── (1) 기존 메서드 — 하위 호환성 유지 ───────────────────────────────

    def crawl(self) -> list[dict]:
        """
        [기존 로직 유지]
        홈페이지 링크에서 AI 키워드를 탐지해 첫 번째 매칭 1건을 수집한다.
        KB 데이터가 있으나 링크를 못 찾은 경우에도 KB 기반 레코드를 추가한다.
        """
        results = []
        seen = set()

        for uni in self.universities:
            uni_name = uni["name"]
            if uni_name in seen:
                continue

            domain = uni["domain"]
            url    = f"https://{domain}"
            kb     = self._lookup_kb(uni_name)
            found  = False

            resp = _get(url)
            if resp:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                        continue
                    text     = a.get_text(separator=" ", strip=True)
                    full_url = urljoin(url, href)

                    if _is_ai_link(href, text):
                        results.append(self._make_record(
                            uni_name, kb, text or href, full_url
                        ))
                        found = True
                        seen.add(uni_name)
                        break

            if not found and kb:
                results.append(self._make_record(
                    uni_name, kb, "(홈페이지 기본 연결)", url
                ))
                seen.add(uni_name)

        return results

    # ── (2) 공지사항 크롤링 ───────────────────────────────────────────────

    def crawl_notices(self, uni_name: str, domain: str) -> list[dict]:
        """
        대학 공지사항 페이지에서 생성형 AI 관련 공지 목록을 수집한다.

        탐색 전략
        ─────────
        1. 홈페이지 링크 중 'notice/board/공지' 패턴 URL 후보 추출
        2. NOTICE_PATH_CANDIDATES 경로도 추가 시도
        3. 각 후보 페이지의 게시글 링크·제목을 스캔해 AI 키워드 매칭

        Returns
        -------
        list[dict]  — 수집된 공지 목록 (최대 5건)
        """
        base_url     = f"https://{domain}"
        notices      = []
        checked_urls = set()

        # 홈페이지에서 공지 후보 URL 수집
        notice_urls = self._find_notice_urls(base_url)
        # 경로 후보도 추가
        for path in NOTICE_PATH_CANDIDATES:
            notice_urls.add(urljoin(base_url, path))

        for notice_url in list(notice_urls)[:8]:  # 최대 8개 후보
            if notice_url in checked_urls:
                continue
            checked_urls.add(notice_url)
            time.sleep(REQUEST_DELAY)

            resp = _get(notice_url)
            if not resp:
                continue

            soup  = BeautifulSoup(resp.text, "html.parser")
            items = soup.find_all("a", href=True)

            for a in items:
                href  = a["href"].strip()
                title = a.get_text(separator=" ", strip=True)
                if not href or not title:
                    continue
                if not (_is_ai_link(href, title) or _is_policy_text(title)):
                    continue

                full_url = urljoin(notice_url, href)
                if not _same_domain(base_url, full_url):
                    continue

                # 공지 상세 페이지 텍스트 추출
                detail_text = self._fetch_text(full_url)
                ai_info     = extract_ai_info(detail_text) if detail_text else {}

                notices.append({
                    "university":         uni_name,
                    "source":             "notice",
                    "title":              title,
                    "url":                full_url,
                    "detected_platforms": ai_info.get("detected_platforms", []),
                    "detected_models":    ai_info.get("detected_models", []),
                    "detected_partners":  ai_info.get("detected_partners", []),
                    "has_guideline":      ai_info.get("has_guideline", False),
                })
                if len(notices) >= 5:
                    return notices

        return notices

    # ── (3) 깊이 탐색 ────────────────────────────────────────────────────

    def crawl_deep(self, uni_name: str, domain: str, max_depth: int = 2) -> list[dict]:
        """
        홈페이지 → AI 관련 하위 페이지 → 그 하위 페이지(depth 2)까지 탐색한다.
        각 페이지 본문에서 AI 정보를 추출해 반환한다.

        Returns
        -------
        list[dict]  — 수집된 페이지 정보 (최대 10건)
        """
        base_url    = f"https://{domain}"
        visited     = set()
        queue       = [(base_url, 0)]   # (url, depth)
        deep_results = []

        while queue and len(deep_results) < 10:
            url, depth = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            visited.add(url)
            time.sleep(REQUEST_DELAY)

            resp = _get(url)
            if not resp:
                continue

            text    = resp.text
            soup    = BeautifulSoup(text, "html.parser")
            content = soup.get_text(separator=" ", strip=True)
            ai_info = extract_ai_info(content)

            # AI 관련 정보가 감지된 페이지만 수집
            if ai_info["detected_platforms"] or ai_info["detected_models"]:
                deep_results.append({
                    "university":         uni_name,
                    "source":             "deep_crawl",
                    "url":                url,
                    "depth":              depth,
                    "detected_platforms": ai_info["detected_platforms"],
                    "detected_models":    ai_info["detected_models"],
                    "detected_partners":  ai_info["detected_partners"],
                    "has_guideline":      ai_info["has_guideline"],
                    "has_platform":       ai_info["has_platform"],
                })

            # 다음 탐색 대상 링크 추출
            if depth < max_depth:
                for a in soup.find_all("a", href=True):
                    href  = a["href"].strip()
                    title = a.get_text(separator=" ", strip=True)
                    if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                        continue
                    if not _is_ai_link(href, title):
                        continue
                    next_url = urljoin(url, href)
                    if _same_domain(base_url, next_url) and next_url not in visited:
                        queue.append((next_url, depth + 1))

        return deep_results

    # ── (4) KB 데이터 보강 ───────────────────────────────────────────────

    def enrich_from_kb(self, results: list[dict]) -> list[dict]:
        """
        crawl_notices() 또는 crawl_deep() 결과에
        AI_KNOWLEDGE_DB 사전 지식을 덮어씌워 보강한다.

        - KB에 플랫폼·파트너 정보가 있으면 우선 적용
        - 크롤링으로 탐지된 정보는 'crawled_*' 키로 별도 보존
        """
        enriched = []
        for item in results:
            kb = self._lookup_kb(item.get("university", ""))
            enriched_item = dict(item)

            # 크롤링 결과 보존
            enriched_item["crawled_platforms"] = item.get("detected_platforms", [])
            enriched_item["crawled_models"]    = item.get("detected_models", [])
            enriched_item["crawled_partners"]  = item.get("detected_partners", [])

            # KB 정보 우선 적용
            if kb:
                enriched_item["official_status"]  = kb.get("official_status", "확인 중")
                enriched_item["kb_ai_model"]       = kb.get("ai_model", "-")
                enriched_item["kb_platform"]       = kb.get("platform", "-")
                enriched_item["kb_application_area"] = kb.get("application_area", "-")
                enriched_item["kb_partner"]        = kb.get("partner", "-")
                enriched_item["policy_url"]        = kb.get("policy_url", "")

            enriched.append(enriched_item)
        return enriched

    # ── (5) 통합 실행 메서드 ─────────────────────────────────────────────

    def run(self, deep: bool = False) -> list[dict]:
        """
        모든 대학에 대해 KB + 공지 크롤링 (+ 선택적 깊이 탐색)을 실행하고
        통합된 최종 결과를 반환한다.

        Parameters
        ----------
        deep : bool
            True이면 crawl_deep()도 함께 실행 (시간 오래 걸림)

        Returns
        -------
        list[dict]
            통합 결과. 각 레코드에 아래 키 포함:
            university, official_status, kb_ai_model, kb_platform,
            kb_application_area, kb_partner, policy_url,
            notice_titles (list), crawled_platforms, crawled_models,
            crawled_partners, has_guideline, has_platform
        """
        final = []

        for uni in self.universities:
            uni_name = uni["name"]
            domain   = uni["domain"]
            kb       = self._lookup_kb(uni_name)

            logger.info("▶ [%s] 크롤링 시작", uni_name)

            # ① KB 기반 베이스 레코드 생성
            record = {
                "university":          uni_name,
                "official_status":     kb.get("official_status",    "확인 중") if kb else "확인 중",
                "kb_ai_model":         kb.get("ai_model",           "-")       if kb else "-",
                "kb_platform":         kb.get("platform",           "-")       if kb else "-",
                "kb_application_area": kb.get("application_area",   "-")       if kb else "-",
                "kb_partner":          kb.get("partner",            "-")       if kb else "-",
                "policy_url":          kb.get("policy_url",         "")        if kb else "",
                "notice_titles":       [],
                "crawled_platforms":   [],
                "crawled_models":      [],
                "crawled_partners":    [],
                "has_guideline":       False,
                "has_platform":        False,
            }

            # ② 공지사항 크롤링
            notices = self.crawl_notices(uni_name, domain)
            record["notice_titles"] = [n["title"] for n in notices]

            # 공지에서 탐지된 AI 정보 병합
            for n in notices:
                record["crawled_platforms"] = list(set(
                    record["crawled_platforms"] + n.get("detected_platforms", [])
                ))
                record["crawled_models"] = list(set(
                    record["crawled_models"] + n.get("detected_models", [])
                ))
                record["crawled_partners"] = list(set(
                    record["crawled_partners"] + n.get("detected_partners", [])
                ))
                if n.get("has_guideline"):
                    record["has_guideline"] = True
                if n.get("detected_platforms"):
                    record["has_platform"] = True

            # ③ (선택) 깊이 탐색
            if deep:
                deep_items = self.crawl_deep(uni_name, domain)
                for d in deep_items:
                    record["crawled_platforms"] = list(set(
                        record["crawled_platforms"] + d.get("detected_platforms", [])
                    ))
                    record["crawled_models"] = list(set(
                        record["crawled_models"] + d.get("detected_models", [])
                    ))
                    record["crawled_partners"] = list(set(
                        record["crawled_partners"] + d.get("detected_partners", [])
                    ))
                    if d.get("has_guideline"):
                        record["has_guideline"] = True
                    if d.get("has_platform"):
                        record["has_platform"] = True

            final.append(record)
            logger.info(
                "   ✓ 공지 %d건 | 플랫폼 탐지: %s | 모델 탐지: %s",
                len(notices),
                record["crawled_platforms"] or "-",
                record["crawled_models"][:3] or "-",
            )

        logger.info("=== 전체 수집 완료: %d개 대학 ===", len(final))
        return final

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────

    def _lookup_kb(self, uni_name: str) -> dict:
        """AI_KNOWLEDGE_DB에서 대학명으로 항목 조회 (부분 일치 허용)."""
        for key, val in AI_KNOWLEDGE_DB.items():
            if key in uni_name or uni_name in key:
                return val
        return {}

    def _make_record(self, uni_name: str, kb: dict, title: str, url: str) -> dict:
        """단일 결과 레코드 생성 (crawl() 전용)."""
        return {
            "university":     uni_name,
            "official_status": kb.get("official_status", "확인 중"),
            "ai_model":        kb.get("ai_model",        "-"),
            "platform":        kb.get("platform",        "-"),
            "application_area": kb.get("application_area", "-"),
            "partner":         kb.get("partner",         "-"),
            "title":           title,
            "url":             url,
        }

    def _find_notice_urls(self, base_url: str) -> set:
        """홈페이지 링크 중 공지/게시판 패턴 URL만 추출한다."""
        urls  = set()
        resp  = _get(base_url)
        if not resp:
            return urls

        soup  = BeautifulSoup(resp.text, "html.parser")
        patterns = re.compile(
            r"notice|board|bbs|공지|게시판|announcement|news", re.IGNORECASE
        )
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue
            if patterns.search(href):
                full = urljoin(base_url, href)
                if _same_domain(base_url, full):
                    urls.add(full)
        return urls

    def _fetch_text(self, url: str) -> str:
        """URL 페이지 본문 텍스트를 반환 (실패 시 빈 문자열)."""
        time.sleep(REQUEST_DELAY)
        resp = _get(url)
        if not resp:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup.get_text(separator=" ", strip=True)
