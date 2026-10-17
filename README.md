# AliParser — AliExpress Scraper & PWA Dashboard

**AliParser** is a full-stack asynchronous web scraping and catalog analytics application for AliExpress, built with **Playwright (Stealth)**, **FastAPI**, **SQLAlchemy 2.0 (SQLite WAL)**, **OpenPyXL**, and an installable **Light Theme Progressive Web App (PWA)** dashboard.

---

## Key Features (Можливості системи)

- **Playwright Stealth + Hybrid `_dida_config_` JSON Extraction:**
  - Scrapes AliExpress search queries (e.g. `wireless mouse`, `usb c hub`) and direct category/catalog URLs (`https://www.aliexpress.com/w/wholesale-...`).
  - Extracts structured product metadata and clean product photos directly from `window._dida_config_._init_data_` combined with DOM cards, filtering out promotional badges (`Choice`, `Brand+`, rating icons).
  - Blocks heavy media/font requests for **3–5x faster page loads** and includes automatic soft-retry resilience when slow network responses occur.
- **Live Telemetry & Dynamic ETA (`TaskRunner`):**
  - Background asynchronous task runner with real-time progress percentage, elapsed time, scraping speed (`items/s`), and dynamic **Estimated Time Remaining (ETA)**.
  - Supports instant **Graceful Stop** (`POST /api/parser/stop`) and automatic recovery of interrupted tasks on startup.
- **SQLite WAL Concurrency:**
  - Configured with `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and `busy_timeout=30000` to prevent `database is locked` errors during simultaneous background writes and 1-second UI polling.
- **Proxy Manager:**
  - Supports `ip:port`, `ip:port:user:pass`, and `protocol://user:pass@host:port` (`http`, `https`, `socks5`) with live connectivity and latency (`ms`) checks.
- **Universal Excel (`.xlsx`) Export:**
  - Generates formatted `.xlsx` spreadsheets with English headers, frozen top row, auto-fitted column widths, numeric prices/ratings, clickable product/image hyperlinks, XML control-character sanitization, and normalized relative ZIP relationships compatible with Microsoft Excel, LibreOffice Calc, WPS Office, and Google Sheets.
- **Light Theme PWA Dashboard:**
  - Responsive English interface with custom number steppers, live status telemetry, product grid/table with instant search & task filtering, proxy management modal, and standalone desktop/mobile PWA installation (`manifest.json` + `sw.js`).

---

## Project Structure (Структура проекту)

```text
/home/dofi/Dev/Aliparser/
├── run_app.py                     # Unified application launcher (FastAPI + standalone PWA window)
├── requirements.txt               # Python dependencies
├── data/
│   └── aliparser.db               # SQLite database (WAL mode enabled automatically)
├── src/
│   ├── api/
│   │   ├── app.py                 # FastAPI REST endpoints & PWA static asset routes
│   │   └── schemas.py             # Pydantic v2 request/response schemas
│   ├── db/
│   │   ├── database.py            # Engine, WAL pragmas, session management, product upsert
│   │   └── models.py              # SQLAlchemy 2.0 ORM models (Product, ParsingTask, Proxy)
│   ├── parser/
│   │   ├── aliexpress.py          # Async Playwright stealth scraper & _dida_config_ extractor
│   │   └── proxy_manager.py       # Multi-format proxy parser & async connectivity checker
│   ├── services/
│   │   ├── exporter.py            # OpenPyXL .xlsx generator with XML sanitization
│   │   └── task_runner.py         # Singleton background scraping orchestrator with live ETA
│   └── web/
│       └── static/
│           ├── index.html         # Light Theme English PWA Dashboard
│           ├── manifest.json      # Web App Manifest
│           ├── sw.js              # Service Worker (aliparser-pwa-v2)
│           └── icon.svg           # Vector application icon
└── scripts/
    ├── test_scraper.py            # CLI scraper verification utility
    ├── test_db_and_proxy.py       # Unit tests for SQLite upsert & proxy parser
    ├── test_task_runner.py        # Unit tests for background TaskRunner & Graceful Stop
    ├── test_api_and_export.py     # Integration tests for REST API & Excel export
    ├── test_pwa.py                # Verification tests for PWA routes & assets
    └── test_e2e_full.py           # Full End-to-End (E2E) & architectural audit suite
```

---

## Quick Start (Швидкий запуск)

1. **Start the server and open the PWA dashboard (Запуск сервера та відкриття інтерфейсу):**
   ```bash
   venv/bin/python run_app.py
   ```
   The server starts at **`http://127.0.0.1:8000`** (and interactive Swagger API docs are available at `http://127.0.0.1:8000/docs`).

2. **Start without opening a browser window (Тільки бекенд-сервер):**
   ```bash
   venv/bin/uvicorn src.api.app:app --host 127.0.0.1 --port 8000
   ```

---

## Running Verification & E2E Tests (Запуск тестів)

- **Full End-to-End (E2E) & Architecture Audit (Повний наскрізний E2E-тест на реальних даних AliExpress):**
  ```bash
  venv/bin/python scripts/test_e2e_full.py
  ```

- **All Module & Integration Tests (Усі модульні та інтеграційні тести):**
  ```bash
  venv/bin/python scripts/test_db_and_proxy.py && \
  venv/bin/python scripts/test_task_runner.py && \
  venv/bin/python scripts/test_api_and_export.py && \
  venv/bin/python scripts/test_pwa.py
  ```

- **CLI Scraper Test (Тестовий запуск парсера з терміналу):**
  ```bash
  venv/bin/python scripts/test_scraper.py --query "usb c hub" --pages 1
  ```
