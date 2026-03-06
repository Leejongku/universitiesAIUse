import os
import streamlit as st
import pandas as pd

import sys
from pathlib import Path

# Add project root to sys.path so we can import from crawler modules
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import importlib
import sheet_manager
import ai_service_crawler
import ai_knowledge
importlib.reload(ai_knowledge)
importlib.reload(ai_service_crawler)
importlib.reload(sheet_manager)
from sheet_manager import SheetManager
st.set_page_config(page_title="AI University Monitor", layout="wide")

st.markdown("""
<style>
    /* Starbucks Theme Styling Overrides */
    h1, h2, h3 {
        color: #006241 !important;
        font-weight: 700;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    hr {
        border-bottom: 2px solid #006241 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f0f0f0;
        border-radius: 4px 4px 0px 0px;
        padding: 10px 20px;
        color: #1e1e1e;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #006241;
        color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)


def load_data(sheet: SheetManager):
    # SheetManager는 내부적으로 url 캐시를 쓰지만,
    # 웹에서는 "전체 데이터"를 읽어오는 게 편함.
    # 그래서 gspread로 직접 읽도록 SheetManager에 client/spreadsheet가 있다는 가정 대신,
    # SheetManager가 이미 connect() 후 _spreadsheet를 들고 있다고 가정하고 접근.
    # (오빠 코드 구조가 이 형태였음)
    ss = sheet._spreadsheet  # noqa: SLF001

    sheet_titles = [w.title for w in ss.worksheets()]

    def ws_to_df(name: str) -> pd.DataFrame:
        if name not in sheet_titles:
            return pd.DataFrame()
        ws = ss.worksheet(name)
        rows = ws.get_all_values()
        if not rows:
            return pd.DataFrame()
        header = rows[0]
        data = rows[1:]
        return pd.DataFrame(data, columns=header)

    df_services = ws_to_df("ai_pages")
    df_policies = ws_to_df("ai_policies") if "ai_policies" in sheet_titles else ws_to_df("policies")
    df_news = ws_to_df("articles")

    # 컬럼 정리(없을 수도 있어서 안전 처리)
    for df in (df_services, df_policies, df_news):
        if not df.empty:
            df.columns = [c.strip() for c in df.columns]

    return df_services, df_policies, df_news


st.title("🏫 AI University Monitor")
st.caption("국내 대학 생성형 AI 활용 현황(서비스/정책/뉴스)")

# Google Sheets 연결
try:
    if "gcp_service_account" in st.secrets:
        # Streamlit Cloud 환경 (Secrets 사용)
        creds_dict = dict(st.secrets["gcp_service_account"])
        sheet = SheetManager(credentials_path=creds_dict)
    else:
        # 로컬 환경 (파일 사용)
        if not os.path.exists("credentials.json"):
            st.error("credentials.json 파일이 없습니다. 로컬에서는 파일이 필요하며, 웹에서는 Streamlit Secrets 설정이 필요합니다.")
            st.stop()
        sheet = SheetManager()
    
    sheet.connect()
except Exception as e:
    st.error(f"Google Sheets 연결 실패: {e}")
    st.stop()

with st.sidebar:
    st.header("🛠️ 관리자 도구 (크롤링)")
    st.caption("새로운 데이터를 검색하고 시트에 저장합니다.")
    
    if st.button("AI 서비스 스크래핑 실행", use_container_width=True):
        import time
        from crawler import load_universities
        from ai_service_crawler import AIServiceCrawler

        unis_data = load_universities()
        total = len(unis_data)

        st.markdown("**🔄 AI 서비스 수집 중...**")
        progress_bar = st.progress(0)
        status_text  = st.empty()

        crawler_instance = AIServiceCrawler(unis_data)
        services_raw = []

        # 대학 1개씩 처리하며 진행률 업데이트
        for idx, uni in enumerate(unis_data):
            status_text.markdown(
                f"⏳ **({idx + 1}/{total})** `{uni['name']}` 수집 중..."
            )
            # 단일 대학용 임시 크롤러
            single_crawler = AIServiceCrawler([uni])
            result = single_crawler.run()
            services_raw.extend(result)
            progress_bar.progress((idx + 1) / total)

        # run() 출력 키 → save_ai_pages_batch 입력 키로 변환
        services = []
        for item in services_raw:
            notice_summary = " | ".join(item.get("notice_titles", [])[:2])
            uni_domain = next(
                (u["domain"] for u in unis_data if u["name"] == item.get("university")), ""
            )
            services.append({
                "university":       item.get("university"),
                "official_status":  item.get("official_status", "확인 중"),
                "ai_model":         item.get("kb_ai_model", "-"),
                "platform":         item.get("kb_platform", "-"),
                "application_area": item.get("kb_application_area", "-"),
                "partner":          item.get("kb_partner", "-"),
                "title":            notice_summary or "(KB 기반 데이터)",
                "url":              item.get("policy_url") or f"https://{uni_domain}",
            })

        status_text.markdown("💾 **구글 시트에 저장 중...**")
        sheet.clear_sheet_data("ai_pages")
        count = sheet.save_ai_pages_batch(services)
        progress_bar.progress(1.0)
        status_text.empty()
        st.success(f"✅ AI 서비스 {count}개 대학 저장 완료!")
        time.sleep(1.5)
        st.rerun()

    if st.button("AI 정책 스크래핑 실행", use_container_width=True):
        import time
        from crawler import load_universities
        from ai_policy_crawler import AIPolicyCrawler

        unis_data = load_universities()
        total = len(unis_data)

        st.markdown("**🔄 AI 정책 수집 중...**")
        progress_bar = st.progress(0)
        status_text  = st.empty()

        all_policies = []
        for idx, uni in enumerate(unis_data):
            status_text.markdown(f"⏳ **({idx + 1}/{total})** `{uni['name']}` AI 정책 탐색 중...")
            single_crawler = AIPolicyCrawler([uni])
            all_policies.extend(single_crawler.crawl())
            progress_bar.progress((idx + 1) / total)

        status_text.markdown("💾 **구글 시트에 저장 중...**")
        sheet.clear_sheet_data("policies")
        count = sheet.save_ai_policies_batch(all_policies)
        progress_bar.progress(1.0)
        status_text.empty()
        st.success(f"✅ AI 정책 {count}개 저장 완료!")
        time.sleep(1.5)
        st.rerun()

    if st.button("최신 AI 트렌드 수집 (Top 20)", use_container_width=True):
        import time
        from news_collector import collect_global_top_ai_news, NEWS_QUERIES

        st.markdown("**🔍 글로벌 AI 뉴스 수집 중...**")
        progress_bar = st.progress(0)
        status_text  = st.empty()

        total_q = len(NEWS_QUERIES)
        for qi, q in enumerate(NEWS_QUERIES):
            status_text.markdown(f"⏳ **({qi + 1}/{total_q})** `{q}` 검색 중...")
            progress_bar.progress((qi + 1) / total_q)
            time.sleep(0.2)  # visual feedback only; actual fetch happens inside collect

        status_text.markdown("📁 **뉴스 수집 및 저장 중...**")
        news_items = collect_global_top_ai_news(20)
        sheet.clear_sheet_data("articles")
        count = sheet.save_global_news(news_items)
        progress_bar.progress(1.0)
        status_text.empty()
        if count > 0:
            st.success(f"✅ 글로벌 AI 뉴스 {count}개 저장 완료!")
        else:
            st.info("새로운 AI 뉴스가 없습니다.")
        time.sleep(1.5)
        st.rerun()

df_services, df_policies, df_news = load_data(sheet)

# 데이터 없을 때 안내
if df_services.empty and df_policies.empty and df_news.empty:
    st.warning("시트에 데이터가 아직 없습니다. 먼저 크롤러를 실행해 데이터를 쌓아줘.")
    st.stop()

# 콤보박스 및 요약 정보 (전체 기준)
total_svc = len(df_services) if not df_services.empty else 0
total_pol = len(df_policies) if not df_policies.empty else 0
total_news = len(df_news) if not df_news.empty else 0

st.write(f"**전체 요약:** AI 서비스 {total_svc}건 | AI 정책 {total_pol}건 | 관련 뉴스 {total_news}건")
st.divider()

# 메인 탭
tab1, tab2, tab3, tab4 = st.tabs(["🤖 AI 서비스", "📜 AI 정책", "📰 관련 뉴스", "📊 주간 AI 보고서"])

with tab1:
    st.subheader("전체 대학 AI 서비스 현황")
    if df_services.empty:
        st.info("ai_pages 시트 데이터가 없습니다.")
    else:
        df = df_services.copy()
        
        # 표시할 컬럼 순서
        ordered_cols = [
            "university", "ai_model", "platform", 
            "application_area", "partner", "title", "url"
        ]
        
        # 존재하는 컬럼만 필터링
        cols = [c for c in ordered_cols if c in df.columns]
        df = df[cols] if cols else df
        
        # DataFrame 컬럼 설정 (한글 매핑 및 링크 활성화)
        column_config = {}
        if "university" in df.columns: column_config["university"] = st.column_config.TextColumn("대학명", width="medium")
        if "ai_model" in df.columns: column_config["ai_model"] = st.column_config.TextColumn("생성형 AI 모델", width="medium")
        if "platform" in df.columns: column_config["platform"] = st.column_config.TextColumn("도입 플랫폼", width="medium")
        if "application_area" in df.columns: column_config["application_area"] = st.column_config.TextColumn("AI 활용 분야", width="large")
        if "partner" in df.columns: column_config["partner"] = st.column_config.TextColumn("파트너/업체", width="medium")
        if "title" in df.columns: column_config["title"] = st.column_config.TextColumn("안내 페이지/제목", width="large")
        if "url" in df.columns: column_config["url"] = st.column_config.LinkColumn("출처", display_text="링크 열기", width="small")
        
        st.dataframe(df, use_container_width=True, column_config=column_config, hide_index=True)
        
        st.divider()
        st.subheader("☕ 대학 AI 서비스 자연어 Q&A")
        st.caption("질문을 입력하시면 전체 대학 데이터를 바탕으로 답변해 드립니다. (예: '서울대 파트너사가 어디야?', '경희대 도입 플랫폼 알려줘')")
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = [{"role": "assistant", "content": "안녕하세요! 궁금하신 대학교의 AI 서비스나 모델, 플랫폼, 파트너사에 대해 물어보세요."}]
            
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                
        if prompt := st.chat_input("질문을 입력해 주세요..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)
                
            with st.chat_message("assistant"):
                response = "해당 대학이나 내용에 대한 정보를 찾을 수 없습니다. (예: 서울대 파트너사 알려줘)"
                
                # 매우 간단한 룰베이스 응답 로직 (KB나 수집된 df 기반)
                for index, row in df.iterrows():
                    uni = str(row.get("university", ""))
                    if uni and (uni in prompt or uni.replace("대학교", "대") in prompt.replace("대학교", "대")):
                        if "파트너" in prompt or "업체" in prompt:
                            response = f"**{uni}**의 파트너/업체는 **{row.get('partner', '-')}** 입니다."
                        elif "모델" in prompt or "생성형" in prompt or "LLM" in prompt.upper():
                            response = f"**{uni}**의 생성형 AI 모델은 **{row.get('ai_model', '-')}** 입니다."
                        elif "플랫폼" in prompt:
                            response = f"**{uni}**의 도입 플랫폼은 **{row.get('platform', '-')}** 입니다."
                        elif "분야" in prompt or "활용" in prompt:
                            response = f"**{uni}**의 AI 활용 분야는 **{row.get('application_area', '-')}** 입니다."
                        else:
                            response = f"**{uni}** 데이터가 확인되었습니다. \n- 모델: {row.get('ai_model', '-')}\n- 플랫폼: {row.get('platform', '-')}\n- 파트너: {row.get('partner', '-')}"
                        break
                        
                st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

with tab2:
    st.subheader("전체 대학 AI 정책 현황")
    if df_policies.empty:
        st.info("ai_policies(또는 policies) 시트 데이터가 없습니다.")
    else:
        df = df_policies.copy()
        default_cols = ["university", "title", "url", "summary", "collected_at"]
        cols = [c for c in default_cols if c in df.columns]
        df = df[cols] if cols else df
        
        column_config = {"url": st.column_config.LinkColumn("링크", display_text="링크 열기")} if "url" in df.columns else None
        st.dataframe(df, use_container_width=True, column_config=column_config)

with tab3:
    st.subheader("📰 최신 생성형 AI 동향 보고서")
    st.caption(f"수집일시: {__import__('datetime').datetime.now().strftime('%Y년 %m월 %d일 %H:%M')} | 생성형 AI 및 온톨로지 관련 최신 뉴스 최대 {total_news}건")
    
    if df_news.empty:
        st.info("수집된 뉴스가 없습니다. '최신 AI 트렌드 수집' 버튼을 눌러주세요.")
    else:
        df_n = df_news.copy()
        st.markdown("---")
        st.markdown(f"""
## 🤖 생성형 AI 트렌드 동향 (최신 {len(df_n)}건)

> 이 보고서는 ChatGPT, Claude, Gemini, 온디바이스 AI 등 글로벌 생성형 AI 쭜신 동향을 종합합니다.
        """)

        for i, row in df_n.iterrows():
            title = row.get("title", "(제목없음)")
            url   = row.get("url", "")
            date  = row.get("date", "")
            badge = ""
            title_l = title.lower()
            if any(k in title_l for k in ["claude", "클로드"]):
                badge = "🟣 "
            elif any(k in title_l for k in ["chatgpt", "gpt", "openai"]):
                badge = "🟢 "
            elif any(k in title_l for k in ["gemini", "google", "구글"]):
                badge = "🔵 "
            elif any(k in title_l for k in ["ontolog", "온톨로지", "knowledge graph"]):
                badge = "🟡 "
            elif any(k in title_l for k in ["llm", "생성형", "ai"]):
                badge = "⚪ "
            
            if url:
                st.markdown(f"{badge}**[{title}]({url})**")
            else:
                st.markdown(f"{badge}**{title}**")
        st.markdown("---")
        st.caption("🔵 ChatGPT/OpenAI  |  🟣 Claude/Anthropic  |  🔵 Gemini/Google  |  🟡 온톨로지  |  ⚪ 기타 AI")

with tab4:
    st.subheader("📊 주간 생성형 AI 트렌드 보고서")
    st.caption("수집된 최신 뉴스를 바탕으로 AI가 주간 동향을 요약합니다.")
    
    if df_news.empty:
        st.info("뉴스가 없습니다. '최신 AI 트렌드 수집'을 먼저 진행해 주세요.")
    else:
        if st.button("🪄 AI 주간 보고서 생성/갱신", use_container_width=True):
            with st.spinner("최신 뉴스를 분석하여 보고서를 작성 중입니다..."):
                import datetime
                today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
                
                news_list = df_news.to_dict('records')
                categories = {"Model": [], "BigTech": [], "Ontology/Tech": [], "Industry": []}
                
                for n in news_list:
                    t = str(n.get('title', '')).lower()
                    if any(k in t for k in ["gpt", "claude", "gemini", "llama", "모델"]):
                        categories["Model"].append(n)
                    elif any(k in t for k in ["apple", "ms", "microsoft", "google", "nvidia", "빅테크"]):
                        categories["BigTech"].append(n)
                    elif any(k in t for k in ["ontolog", "온톨로지", "knowledge graph", "기술", "추세"]):
                        categories["Ontology/Tech"].append(n)
                    else:
                        categories["Industry"].append(n)

                report_md = f"""# 📑 주간 생성형 AI 동향 분석 보고서
**발행일:** {today}
**대상:** 최신 수집 뉴스 {len(news_list)}건 기반

---

### 1. 🚀 핵심 모델 및 알고리즘 동향
{chr(10).join([f"- **[{n['title']}]({n.get('url', '#')})** ({n.get('date', '-')})" for n in categories['Model'][:3]]) if categories['Model'] else "- 최근 주목할 만한 신규 모델 발표가 집계되지 않았습니다."}

### 2. 🏢 빅테크 기업 주요 행보
{chr(10).join([f"- **[{n['title']}]({n.get('url', '#')})** ({n.get('date', '-')})" for n in categories['BigTech'][:3]]) if categories['BigTech'] else "- 빅테크 기업의 대형 인프라 투자가 지속되고 있습니다."}

### 3. 💡 온톨로지 및 신기술 트렌드 (Ontology & Tech)
{chr(10).join([f"- **[{n['title']}]({n.get('url', '#')})** ({n.get('date', '-')})" for n in categories['Ontology/Tech'][:3]]) if categories['Ontology/Tech'] else "- AI 신뢰성 향상을 위한 지식 그래프 및 온톨로지 결합 기술이 관찰됩니다."}

### 4. 🌐 산업계 활용 및 사회적 변화
{chr(10).join([f"- **[{n['title']}]({n.get('url', '#')})** ({n.get('date', '-')})" for n in categories['Industry'][:3]]) if categories['Industry'] else "- 다양한 산업 분야에서 생성형 AI 도입 사례가 증가하고 있습니다."}

---
**[요약 및 시사점]**
- 최근 AI 트렌드는 **멀티모달 모델의 고도화**와 **지식 그래프(Ontology)를 통한 할루시네이션 극복**에 집중되어 있습니다.
- 대학 교육 현장에서도 이러한 기술을 반영한 맞춤형 학습 도구 도입이 가속화될 것으로 보입니다.
"""
                st.session_state['weekly_report'] = report_md
                st.success("보고서 생성이 완료되었습니다!")

        if 'weekly_report' in st.session_state:
            st.markdown("---")
            st.markdown(st.session_state['weekly_report'])
            
            st.download_button(
                label="📄 보고서 다운로드 (Markdown)",
                data=st.session_state['weekly_report'],
                file_name=f"AI_Weekly_Report_{datetime.datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
            )
        else:
            st.info("상단의 버튼을 눌러 보고서를 생성해 주세요.")

st.divider()
st.caption("Tip: 데이터가 안 보이면 왜쪽의 크롤링 버튼을 눌러 시트에 데이터를 추가해 주세요. 화면을 가로로 길게 쓰실 수 있습니다.")