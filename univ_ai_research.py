import os
import re
import time
import json
import math
import hashlib
import logging
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional

import requests
import pandas as pd
import fitz  # PyMuPDF
from bs4 import BeautifulSoup


# =========================================================
# 설정
# =========================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "").strip()

INPUT_CSV = "universities.csv"
OUTPUT_XLSX = f"university_genai_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

REQUEST_TIMEOUT = 20
REQUEST_DELAY = 0.8
MAX_RESULTS_PER_QUERY = 10
MAX_PAGES_PER_QUERY = 1   # Google Custom Search는 start 파라미터로 페이지 이동 가능
MAX_TEXT_LENGTH = 20000   # 본문 너무 길면 잘라서 처리
USER_AGENT = "Mozilla/5.0 (compatible; UniversityAIResearchBot/1.0; +https://example.org/bot)"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================================================
# 키워드/분류 규칙
# =========================================================

SEARCH_GROUPS = {
    "adoption": [
        "생성형 AI", "ChatGPT", "Claude", "Gemini", "Copilot", "LLM", "AI 플랫폼",
        "대화형 AI", "생성 AI", "AI 도우미"
    ],
    "chatbot_service": [
        "챗봇", "AI 챗봇", "학사 챗봇", "상담 챗봇", "입학 챗봇",
        "AI 서비스", "AI 비서", "질의응답", "도우미"
    ],
    "policy": [
        "생성형 AI 가이드", "ChatGPT 가이드", "Copilot 가이드",
        "AI 윤리", "표절", "과제 ChatGPT", "강의계획서 ChatGPT",
        "생성형 AI 활용", "AI 활용 지침", "AI 사용 가이드"
    ],
}

AI_PRODUCTS = [
    "chatgpt", "copilot", "gemini", "claude", "bard",
    "gpt", "llm", "생성형 ai", "생성 ai", "대화형 ai"
]

CHATBOT_KEYWORDS = [
    "챗봇", "ai 챗봇", "학사 챗봇", "입학 챗봇", "상담 챗봇",
    "도우미", "qa", "질의응답", "헬프데스크"
]

POLICY_KEYWORDS = [
    "가이드", "지침", "정책", "윤리", "표절",
    "과제", "시험", "강의계획서", "출처", "허용", "금지", "제한"
]

TARGET_KEYWORDS = {
    "student": ["학생", "재학생", "학부생", "대학원생", "수강생"],
    "faculty": ["교원", "교수", "강사", "교직원", "직원", "교원·직원"],
    "all": ["구성원", "전체", "전 구성원", "학내 구성원"]
}


# =========================================================
# 유틸
# =========================================================

def safe_get(d: Dict[str, Any], key: str, default=None):
    return d[key] if key in d else default


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(text: str, max_len: int = MAX_TEXT_LENGTH) -> str:
    text = text or ""
    return text[:max_len]


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_same_university_domain(result_url: str, domain: str) -> bool:
    parsed = get_domain(result_url)
    return parsed.endswith(domain.lower())


def is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def sleep_brief():
    time.sleep(REQUEST_DELAY)


def clean_filename_text(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", text)


# =========================================================
# Google Search API
# =========================================================

def google_custom_search(query: str, start: int = 1, num: int = 10) -> List[Dict[str, Any]]:
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        raise RuntimeError("GOOGLE_API_KEY 또는 GOOGLE_CSE_ID 환경변수가 설정되지 않았습니다.")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "start": start,
        "num": min(num, 10),
        "hl": "ko",
        "gl": "kr",
    }

    logging.info(f"[SEARCH] {query}")
    resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])


def build_queries(univ_name: str, alias: str, domain: str) -> List[Dict[str, str]]:
    queries = []

    # 도입현황: 키워드들을 OR로 조합하여 1개 쿼리로 압축
    adoption_kws = ' OR '.join([f'"{kw}"' for kw in SEARCH_GROUPS["adoption"]])
    queries.append({
        "query_type": "도입현황",
        "query": f'site:{domain} ({adoption_kws})'
    })

    # 챗봇/서비스: 키워드들을 OR로 조합하여 1개 쿼리로 압축
    chatbot_kws = ' OR '.join([f'"{kw}"' for kw in SEARCH_GROUPS["chatbot_service"]])
    queries.append({
        "query_type": "챗봇/서비스",
        "query": f'site:{domain} ({chatbot_kws})'
    })

    # 정책/가이드: 키워드들을 OR로 조합하여 1개 쿼리로 압축
    policy_kws = ' OR '.join([f'"{kw}"' for kw in SEARCH_GROUPS["policy"]])
    queries.append({
        "query_type": "정책/가이드",
        "query": f'site:{domain} ({policy_kws})'
    })

    # 보강검색: 주요 키워드와 학교명을 조합하여 1개 쿼리로 압축
    bonus_terms = ["생성형 AI", "ChatGPT", "Copilot", "챗봇", "가이드"]
    bonus_kws = ' OR '.join([f'"{kw}"' for kw in bonus_terms])
    queries.append({
        "query_type": "보강검색",
        "query": f'"{univ_name}" ({bonus_kws}) site:{domain}'
    })

    return queries


# =========================================================
# 본문 수집
# =========================================================

def fetch_html_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    html = resp.text

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    # 본문성 높은 태그 우선
    candidates = []
    for selector in ["article", "main", "section", "div", "body"]:
        for tag in soup.select(selector):
            text = normalize_text(tag.get_text(" ", strip=True))
            if len(text) > 200:
                candidates.append(text)

    if candidates:
        text = max(candidates, key=len)
    else:
        text = normalize_text(soup.get_text(" ", strip=True))

    return truncate_text(text)


def fetch_pdf_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    pdf_bytes = resp.content
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    texts = []
    for page in doc:
        page_text = page.get_text("text")
        if page_text:
            texts.append(page_text)

    full_text = normalize_text("\n".join(texts))
    return truncate_text(full_text)


def fetch_document_text(url: str) -> str:
    try:
        if is_pdf_url(url):
            return fetch_pdf_text(url)
        return fetch_html_text(url)
    except Exception as e:
        logging.warning(f"[FETCH FAIL] {url} | {e}")
        return ""


# =========================================================
# 메타 추출
# =========================================================

def extract_date_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    patterns = [
        r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)",
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(1)
            normalized = raw.replace("년", "-").replace("월", "-").replace("일", "")
            normalized = normalized.replace(".", "-").replace("/", "-")
            normalized = re.sub(r"\s+", "", normalized)
            try:
                dt = datetime.strptime(normalized, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                continue

    return None


def infer_target_users(text: str) -> str:
    found = []

    lower_text = text.lower()

    for group, words in TARGET_KEYWORDS.items():
        for w in words:
            if w.lower() in lower_text:
                found.append(group)
                break

    if "all" in found:
        return "전체"
    if "student" in found and "faculty" in found:
        return "학생/교직원"
    if "student" in found:
        return "학생"
    if "faculty" in found:
        return "교직원"

    return "미상"


def infer_ai_types(text: str) -> str:
    text_lower = text.lower()
    found = []

    mapping = {
        "chatgpt": ["chatgpt", "gpt"],
        "copilot": ["copilot"],
        "gemini": ["gemini"],
        "claude": ["claude"],
        "생성형AI": ["생성형 ai", "생성 ai", "llm", "대화형 ai"],
        "자체챗봇": ["챗봇", "ai 챗봇", "학사 챗봇", "입학 챗봇", "상담 챗봇"],
    }

    for label, words in mapping.items():
        if any(w in text_lower for w in words):
            found.append(label)

    if not found:
        return "기타"

    return ", ".join(sorted(set(found)))


def infer_status(text: str) -> str:
    text_lower = text.lower()

    if any(w in text_lower for w in ["오픈", "운영", "서비스", "제공", "개시", "시범운영", "도입"]):
        return "운영/도입"
    if any(w in text_lower for w in ["가이드", "지침", "안내", "정책"]):
        return "정책/안내"
    if any(w in text_lower for w in ["교육", "특강", "세미나", "워크숍", "연수"]):
        return "교육/행사"
    return "기타"


def infer_category(title: str, text: str, query_type: str) -> str:
    combined = f"{title} {text}".lower()

    score = {
        "도입현황": 0,
        "챗봇/서비스": 0,
        "정책/가이드": 0,
    }

    if any(k in combined for k in AI_PRODUCTS):
        score["도입현황"] += 2
    if any(k in combined for k in CHATBOT_KEYWORDS):
        score["챗봇/서비스"] += 3
    if any(k in combined for k in POLICY_KEYWORDS):
        score["정책/가이드"] += 3

    if query_type in score:
        score[query_type] += 2

    best = max(score, key=score.get)
    return best


def extract_evidence(text: str, keywords: List[str], max_sentences: int = 3) -> str:
    if not text:
        return ""

    # 한국어 문장 나누기 대충 처리
    sentences = re.split(r'(?<=[.!?다요])\s+|\n+', text)
    picked = []

    for sent in sentences:
        s = normalize_text(sent)
        if len(s) < 20:
            continue
        if any(k.lower() in s.lower() for k in keywords):
            picked.append(s)
        if len(picked) >= max_sentences:
            break

    return " / ".join(picked[:max_sentences])[:1000]


# =========================================================
# 레코드 처리
# =========================================================

def process_search_item(univ_name: str, alias: str, domain: str, query_type: str, query: str, item: Dict[str, Any]) -> Dict[str, Any]:
    title = safe_get(item, "title", "") or ""
    link = safe_get(item, "link", "") or ""
    snippet = safe_get(item, "snippet", "") or ""

    if not link:
        return {}

    if not is_same_university_domain(link, domain):
        return {}

    doc_text = fetch_document_text(link)
    merged_text = normalize_text(f"{title} {snippet} {doc_text}")
    merged_text = truncate_text(merged_text)

    category = infer_category(title, merged_text, query_type)
    ai_type = infer_ai_types(merged_text)
    target = infer_target_users(merged_text)
    status = infer_status(merged_text)
    page_date = extract_date_from_text(merged_text)
    evidence = extract_evidence(
        merged_text,
        keywords=[
            "생성형 AI", "ChatGPT", "Copilot", "Claude", "Gemini",
            "챗봇", "가이드", "지침", "표절", "강의계획서", "AI"
        ]
    )

    title_or_text = f"{title} {merged_text}".lower()
    confidence = 0
    if any(w in title_or_text for w in ["chatgpt", "copilot", "gemini", "claude", "생성형 ai"]):
        confidence += 2
    if any(w in title_or_text for w in ["챗봇", "ai 챗봇", "상담 챗봇", "학사 챗봇"]):
        confidence += 2
    if any(w in title_or_text for w in ["가이드", "지침", "표절", "정책", "강의계획서"]):
        confidence += 2
    if len(doc_text) > 500:
        confidence += 1

    return {
        "대학": univ_name,
        "별칭": alias,
        "도메인": domain,
        "검색분류": query_type,
        "판정분류": category,
        "AI유형": ai_type,
        "상태": status,
        "대상": target,
        "제목": title,
        "게시일추정": page_date,
        "URL": link,
        "검색쿼리": query,
        "스니펫": snippet,
        "근거": evidence,
        "본문요약원문": merged_text[:3000],
        "신뢰점수": confidence,
        "문서해시": sha1_text(link + merged_text[:1000])
    }


def deduplicate_records(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.sort_values(
        by=["대학", "신뢰점수"],
        ascending=[True, False]
    ).copy()

    df = df.drop_duplicates(subset=["대학", "URL"], keep="first")
    df = df.drop_duplicates(subset=["문서해시"], keep="first")

    return df.reset_index(drop=True)


def summarize_by_university(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    if df.empty:
        return pd.DataFrame(columns=[
            "대학", "도입현황", "챗봇/서비스", "정책/가이드", "대표근거", "대표URL"
        ])

    for univ, g in df.groupby("대학"):
        adoption = "있음" if (g["판정분류"] == "도입현황").any() else "없음"
        chatbot = "있음" if (g["판정분류"] == "챗봇/서비스").any() else "없음"
        policy = "있음" if (g["판정분류"] == "정책/가이드").any() else "없음"

        best = g.sort_values(by=["신뢰점수"], ascending=False).iloc[0]

        rows.append({
            "대학": univ,
            "도입현황": adoption,
            "챗봇/서비스": chatbot,
            "정책/가이드": policy,
            "대표근거": best["근거"],
            "대표URL": best["URL"],
        })

    return pd.DataFrame(rows)


# =========================================================
# 메인 실행
# =========================================================

def load_universities(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    required = {"name", "alias", "domain"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV에 필요한 컬럼이 없습니다: {missing}")
    return df


def run():
    universities = load_universities(INPUT_CSV)
    all_records = []

    for idx, row in universities.iterrows():
        univ_name = row["name"].strip()
        alias = row["alias"].strip()
        domain = row["domain"].strip()

        logging.info(f"========== [{idx + 1}/{len(universities)}] {univ_name} ==========")

        queries = build_queries(univ_name, alias, domain)

        for qinfo in queries:
            query_type = qinfo["query_type"]
            query = qinfo["query"]

            try:
                for page in range(MAX_PAGES_PER_QUERY):
                    start = 1 + page * MAX_RESULTS_PER_QUERY
                    items = google_custom_search(query=query, start=start, num=MAX_RESULTS_PER_QUERY)

                    if not items:
                        break

                    for item in items:
                        try:
                            rec = process_search_item(
                                univ_name=univ_name,
                                alias=alias,
                                domain=domain,
                                query_type=query_type,
                                query=query,
                                item=item
                            )
                            if rec:
                                all_records.append(rec)
                        except Exception as inner_e:
                            logging.warning(f"[ITEM FAIL] {univ_name} | {query} | {inner_e}")

                    sleep_brief()

            except Exception as e:
                logging.warning(f"[QUERY FAIL] {univ_name} | {query} | {e}")
                sleep_brief()
                continue

    raw_df = pd.DataFrame(all_records)

    if raw_df.empty:
        logging.warning("수집 결과가 없습니다.")
        with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
            pd.DataFrame(columns=["message"]).to_excel(writer, sheet_name="README", index=False)
        print(f"완료: {OUTPUT_XLSX}")
        return

    clean_df = deduplicate_records(raw_df)

    adoption_df = clean_df[clean_df["판정분류"] == "도입현황"].copy()
    chatbot_df = clean_df[clean_df["판정분류"] == "챗봇/서비스"].copy()
    policy_df = clean_df[clean_df["판정분류"] == "정책/가이드"].copy()
    summary_df = summarize_by_university(clean_df)

    # 보기 좋게 정렬
    sort_cols = ["대학", "신뢰점수", "게시일추정"]
    for d in [clean_df, adoption_df, chatbot_df, policy_df]:
        if not d.empty:
            d.sort_values(by=[c for c in sort_cols if c in d.columns], ascending=[True, False, False], inplace=True)

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="00_요약", index=False)
        clean_df.to_excel(writer, sheet_name="01_전체수집", index=False)
        adoption_df.to_excel(writer, sheet_name="02_도입현황", index=False)
        chatbot_df.to_excel(writer, sheet_name="03_챗봇_서비스", index=False)
        policy_df.to_excel(writer, sheet_name="04_정책_가이드", index=False)

    logging.info(f"완료: {OUTPUT_XLSX}")
    print(f"완료: {OUTPUT_XLSX}")


if __name__ == "__main__":
    run()