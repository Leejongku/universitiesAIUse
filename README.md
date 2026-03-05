# 🎓 한국 대학교 AI 모니터 크롤러
**Korean University Generative AI Monitor Crawler**

Automatically collects news articles and official university pages related to generative AI use across 30 major Korean universities. Results are saved to a shared Google Sheets spreadsheet for easy review and tracking.

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Features](#features)
3. [Project Structure](#project-structure)
4. [Installation](#installation)
5. [Google Cloud API Setup](#google-cloud-api-setup)
6. [Configuration](#configuration)
7. [Running the Crawler](#running-the-crawler)
8. [Scheduling the Crawler](#scheduling-the-crawler)
9. [Google Sheets Output](#google-sheets-output)
10. [Example Log Output](#example-log-output)
11. [Troubleshooting](#troubleshooting)

---

## Project Overview

This is a **personal data collection system** designed to monitor how generative AI (ChatGPT, LLM, etc.) is being adopted and regulated across major Korean universities.

The crawler:
- Fetches news articles from **Google News RSS** using targeted Korean search queries
- Extracts full article text and detects **university name mentions** (including aliases like 서울대 → 서울대학교)
- Discovers **official university AI pages** from `.ac.kr` domains
- Saves all results to **Google Sheets** with deduplication

**Monitored universities (30):**

| Group | Universities |
|-------|-------------|
| 서울 주요대 | 서울대, 연세대, 고려대, 성균관대, 한양대, 중앙대, 경희대, 한국외대, 서강대, 이화여대 |
| 서울 기타 | 숙명여대, 건국대, 동국대, 홍익대, 국민대, 숭실대, 세종대, 단국대 |
| 수도권 | 아주대, 인하대 |
| 이공계 특화 | KAIST, POSTECH, UNIST, DGIST, GIST |
| 지방 거점 | 부산대, 경북대, 전남대, 충남대, 전북대 |

---

## Features

- ✅ Google News RSS collection (4 targeted queries)
- ✅ Full article content extraction with HTML parsing
- ✅ University name + alias dictionary matching
- ✅ Official AI page discovery via Bing search (site:ac.kr)
- ✅ Google Sheets integration with automatic sheet creation
- ✅ URL-level deduplication (in-memory cache + sheet check)
- ✅ Polite crawling with request delays
- ✅ Structured logging to console and `crawler.log`
- ✅ Error handling (network failures, bad HTML, Sheets API errors)
- ✅ Dry-run mode for testing without writing to Sheets
- ✅ Progress indicator for long-running operations
- ✅ Cron / Task Scheduler ready

---

## Project Structure

```
ai_university_crawler/
├── crawler.py              # Main entry point – orchestrates the pipeline
├── news_collector.py       # Google News RSS + AI page discovery
├── article_parser.py       # Fetches & extracts article text
├── university_matcher.py   # University name/alias detection
├── sheet_manager.py        # Google Sheets read/write
│
├── universities.csv        # Master list of 30 universities with aliases
│
├── credentials.json        # ⚠️ YOUR secret (not committed to Git)
├── credentials.json.example # Template – shows expected JSON structure
│
├── requirements.txt
├── README.md
└── .gitignore
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ai_university_crawler.git
cd ai_university_crawler
```

### 2. Create a virtual environment

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Google Cloud API Setup

The crawler writes data to Google Sheets using a **Service Account**. Follow these steps:

### Step 1 – Create a Google Cloud Project

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Click **"New Project"**, give it a name (e.g. `uni-ai-monitor`), and click **Create**

### Step 2 – Enable the required APIs

Inside your new project:

1. Go to **APIs & Services → Library**
2. Search for and enable:
   - **Google Sheets API**
   - **Google Drive API**

### Step 3 – Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **"+ Create Credentials" → Service Account**
3. Fill in a name (e.g. `crawler-bot`) and click **Create and Continue**
4. Skip optional role assignment and click **Done**

### Step 4 – Download the JSON key

1. On the **Credentials** page, click your new service account
2. Go to the **Keys** tab
3. Click **Add Key → Create new key → JSON**
4. The file downloads automatically – this is your `credentials.json`

### Step 5 – Place credentials in the project

```bash
cp ~/Downloads/your-key-file.json ai_university_crawler/credentials.json
```

> ⚠️ `credentials.json` is listed in `.gitignore` and will **never** be committed.

### Step 6 – Share the Google Sheet with the service account

The sheet is created automatically on first run. To give the service account write access:

1. Run the crawler once (`python crawler.py --dry-run`) to see the service account email in the logs
2. Open Google Sheets, find `대학_AI_현황`
3. Click **Share** and add the service account email with **Editor** permissions

> Alternatively, the service account creates the sheet itself, so sharing happens automatically when it is the owner.

---

## Configuration

All configuration is done through `universities.csv`. You can:

- Add or remove universities (one per row)
- Add additional aliases in the `alias` column
- Update domain names in the `domain` column

To modify the news search queries, edit `NEWS_QUERIES` in `news_collector.py`.

---

## Running the Crawler

### Full run (news + AI pages)

```bash
python crawler.py
```

### News only

```bash
python crawler.py --skip-pages
```

### AI page discovery only

```bash
python crawler.py --skip-news
```

### Test run (no Google Sheets writes)

```bash
python crawler.py --dry-run
```

### Verbose / debug output

```bash
python crawler.py --verbose
```

---

## Scheduling the Crawler

### Linux / macOS – cron

Run the crawler every day at 08:00:

```bash
crontab -e
```

Add:

```cron
0 8 * * * /path/to/.venv/bin/python /path/to/ai_university_crawler/crawler.py >> /path/to/ai_university_crawler/crawler.log 2>&1
```

### Windows – Task Scheduler

1. Open **Task Scheduler** → **Create Basic Task**
2. Set the trigger (e.g. Daily, 08:00)
3. Action: **Start a program**
   - Program: `C:\path\to\.venv\Scripts\python.exe`
   - Arguments: `C:\path\to\ai_university_crawler\crawler.py`
4. Click **Finish**

---

## Google Sheets Output

The spreadsheet **`대학_AI_현황`** is created automatically with three sheets:

### `universities`

| name | alias | domain |
|------|-------|--------|
| 서울대학교 | 서울대 | snu.ac.kr |
| KAIST | 카이스트 | kaist.ac.kr |
| … | … | … |

### `articles`

| university | title | url | date | collected_at |
|-----------|-------|-----|------|-------------|
| 연세대학교 | 연세대, 생성형 AI 가이드라인 발표 | https://… | Mon, 01 Jan 2025 | 2025-01-01 09:00:00 |

### `ai_pages`

| university | title | url | collected_at |
|-----------|-------|-----|-------------|
| 고려대학교 | 고려대학교 AI 활용 지침 | https://ai.korea.ac.kr/… | 2025-01-01 09:00:00 |

---

## Example Log Output

```
2025-01-01 09:00:00 | INFO     | Starting crawler
2025-01-01 09:00:00 | INFO     | Loaded 30 universities.
2025-01-01 09:00:01 | INFO     | Connecting to Google Sheets …
2025-01-01 09:00:03 | INFO     | Google Sheets connection established.
2025-01-01 09:00:03 | INFO     | Phase 1: News article collection
2025-01-01 09:00:03 | INFO     | Searching news for keyword: 대학 생성형 AI
2025-01-01 09:00:05 | INFO     | Found 23 articles for query '대학 생성형 AI'
2025-01-01 09:00:07 | INFO     | Matched university: 연세대학교 | 연세대, 생성형 AI 교육 도입...
2025-01-01 09:00:07 | INFO     | Saving article to Google Sheets | 연세대학교 | 연세대, 생성형 AI ...
2025-01-01 09:00:09 | INFO     | Matched university: 서울대학교 | 서울대 AI 가이드라인 공개...
2025-01-01 09:00:10 | INFO     | News pipeline complete. Checked: 45 | Saved: 12
2025-01-01 09:00:10 | INFO     | Phase 2: Official AI page discovery
2025-01-01 09:00:10 | INFO     | Searching AI pages for: 서울대학교
2025-01-01 09:00:13 | INFO     | Saved AI page | 서울대학교 | https://…
2025-01-01 09:10:42 | INFO     | AI page pipeline complete. Found: 34 | Saved: 21
2025-01-01 09:10:42 | INFO     | Crawler finished successfully.
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `credentials.json not found` | Place your Google Service Account JSON at the project root |
| `SpreadsheetNotFound` | Check service account email has been shared on the spreadsheet |
| `gspread.exceptions.APIError` | Google Sheets API quota exceeded – wait and retry |
| Articles not being fetched | Some news sites block scrapers; this is expected behaviour |
| No AI pages found | Bing may block automated requests; consider using Bing Search API |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` inside your virtual environment |

---

## GitHub Deployment

```bash
# Initialise repository
git init
git add .
git commit -m "Initial commit: Korean University AI Monitor Crawler"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/ai_university_crawler.git
git branch -M main
git push -u origin main
```

> Make sure `credentials.json` is **not** staged. Verify with `git status` before pushing.

---

## License

MIT – free to use, modify, and distribute.
