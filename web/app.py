import os
import streamlit as st
import pandas as pd

from sheet_manager import SheetManager

st.set_page_config(page_title="AI University Monitor", layout="wide")


def load_data(sheet: SheetManager):
    # SheetManager는 내부적으로 url 캐시를 쓰지만,
    # 웹에서는 "전체 데이터"를 읽어오는 게 편함.
    # 그래서 gspread로 직접 읽도록 SheetManager에 client/spreadsheet가 있다는 가정 대신,
    # SheetManager가 이미 connect() 후 _spreadsheet를 들고 있다고 가정하고 접근.
    # (오빠 코드 구조가 이 형태였음)
    ss = sheet._spreadsheet  # noqa: SLF001

    def ws_to_df(name: str) -> pd.DataFrame:
        ws = ss.worksheet(name)
        rows = ws.get_all_values()
        if not rows:
            return pd.DataFrame()
        header = rows[0]
        data = rows[1:]
        return pd.DataFrame(data, columns=header)

    df_services = ws_to_df("ai_pages")
    df_policies = ws_to_df("ai_policies") if "ai_policies" in [w.title for w in ss.worksheets()] else ws_to_df("policies")
    df_news = ws_to_df("articles")

    # 컬럼 정리(없을 수도 있어서 안전 처리)
    for df in (df_services, df_policies, df_news):
        if not df.empty:
            df.columns = [c.strip() for c in df.columns]

    return df_services, df_policies, df_news


st.title("🏫 AI University Monitor")
st.caption("국내 대학 생성형 AI 활용 현황(서비스/정책/뉴스)")

# credentials.json 위치 체크 (프로젝트 루트에 있어야 함)
if not os.path.exists("credentials.json"):
    st.error("credentials.json 파일이 프로젝트 루트에 없습니다. (universitiesAIUse/credentials.json)")
    st.stop()

# Google Sheets 연결
sheet = SheetManager()
try:
    sheet.connect()
except Exception as e:
    st.error(f"Google Sheets 연결 실패: {e}")
    st.stop()

df_services, df_policies, df_news = load_data(sheet)

# 데이터 없을 때 안내
if df_services.empty and df_policies.empty and df_news.empty:
    st.warning("시트에 데이터가 아직 없습니다. 먼저 크롤러를 실행해 데이터를 쌓아줘.")
    st.stop()

# 대학 목록 만들기
unis = set()
for df in (df_services, df_policies, df_news):
    if not df.empty and "university" in df.columns:
        unis |= set(df["university"].dropna().unique())

unis = sorted([u for u in unis if str(u).strip() != ""])

left, right = st.columns([1, 3])

with left:
    st.subheader("대학 선택")
    selected_uni = st.selectbox("University", unis if unis else ["(데이터 없음)"])
    st.divider()

    st.subheader("요약")
    svc_cnt = 0 if df_services.empty else (df_services["university"] == selected_uni).sum() if "university" in df_services.columns else 0
    pol_cnt = 0 if df_policies.empty else (df_policies["university"] == selected_uni).sum() if "university" in df_policies.columns else 0
    news_cnt = 0 if df_news.empty else (df_news["university"] == selected_uni).sum() if "university" in df_news.columns else 0

    st.metric("AI 서비스", int(svc_cnt))
    st.metric("AI 정책", int(pol_cnt))
    st.metric("관련 뉴스", int(news_cnt))

with right:
    tab1, tab2, tab3 = st.tabs(["🤖 AI 서비스", "📜 AI 정책", "📰 관련 뉴스"])

    with tab1:
        st.subheader(f"{selected_uni} - AI 서비스")
        if df_services.empty:
            st.info("ai_pages 시트 데이터가 없습니다.")
        else:
            df = df_services.copy()
            if "university" in df.columns:
                df = df[df["university"] == selected_uni]
            # 보기 좋은 컬럼 순서
            cols = [c for c in ["title", "url", "collected_at", "university"] if c in df.columns]
            df = df[cols] if cols else df
            st.dataframe(df, use_container_width=True)

    with tab2:
        st.subheader(f"{selected_uni} - AI 정책")
        if df_policies.empty:
            st.info("ai_policies(또는 policies) 시트 데이터가 없습니다.")
        else:
            df = df_policies.copy()
            if "university" in df.columns:
                df = df[df["university"] == selected_uni]
            cols = [c for c in ["title", "url", "summary", "collected_at", "university"] if c in df.columns]
            df = df[cols] if cols else df
            st.dataframe(df, use_container_width=True)

    with tab3:
        st.subheader(f"{selected_uni} - 관련 뉴스")
        if df_news.empty:
            st.info("articles 시트 데이터가 없습니다.")
        else:
            df = df_news.copy()
            if "university" in df.columns:
                df = df[df["university"] == selected_uni]
            cols = [c for c in ["date", "title", "url", "collected_at", "university"] if c in df.columns]
            df = df[cols] if cols else df
            st.dataframe(df, use_container_width=True)

st.divider()
st.caption("Tip: 데이터가 안 보이면 먼저 ai_service / ai_policy 실행해서 시트에 저장되게 해줘.")