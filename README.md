# AliParser — AliExpress Scraper & PWA Dashboard

**AliParser** is an asynchronous web scraping and product catalog management application for AliExpress. It combines a **Playwright** stealth scraping engine with a **FastAPI** REST backend, **SQLAlchemy 2.0 (SQLite WAL)** persistence, **OpenPyXL** spreadsheet export, and an installable **Progressive Web App (PWA)** dashboard.

---

## Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Scraper Core** | `Playwright` (Async Chromium) | Headless stealth browser automation, resource blocking, and DOM + `_dida_config_` state extraction |
| **Backend API** | `FastAPI` + `Uvicorn` | Asynchronous REST API endpoints, background task orchestration, and static PWA hosting |
| **Data Validation** | `Pydantic v2` | Strict schema validation for scraped items, task status telemetry, and REST payloads |
| **Database & ORM** | `SQLAlchemy 2.0` + `SQLite (WAL)` | Concurrent persistence for products, parsing tasks, and proxies (`PRAGMA journal_mode=WAL`) |
| **Proxy Networking** | `HTTPX` (`httpx[socks]`) | Asynchronous proxy connectivity & latency (`ms`) verification (`HTTP`, `HTTPS`, `SOCKS5`) |
| **Excel Export** | `OpenPyXL` | Formatted `.xlsx` generation with frozen headers, auto-sized columns, and clickable hyperlinks |
| **Frontend UI** | `HTML5` + `Tailwind CSS` + `Vanilla JS` | Light-theme responsive dashboard, 1-second live telemetry polling, and installable PWA (`manifest.json` + `sw.js`) |

---

## Key Features

- **Hybrid Playwright + `_dida_config_` Extraction:**
  - Scrapes AliExpress search queries (e.g., `wireless mouse`, `usb c hub`) or direct category/catalog URLs (`https://www.aliexpress.com/w/wholesale-...`).
  - Extracts structured product data and high-resolution product images from `window._dida_config_._init_data_` combined with DOM cards, automatically filtering out promotional badges (`Choice`, `Brand+`, rating/store icons).
  - Blocks heavy static assets (`image`, `media`, `font`) at the network route level for 3–5x faster page loads and performs an automatic soft retry if initial DOM hydration returns zero items.
- **Background `TaskRunner` with Live Telemetry & ETA:**
  - Executes multi-page scraping jobs asynchronously in the background without blocking the API loop.
  - Computes real-time progress percentage, elapsed time, scraping speed (`items/s`), and dynamic **Estimated Time Remaining (ETA)**.
  - Supports instant **Graceful Stop** (`POST /api/parser/stop`) and automatic recovery of interrupted tasks on server startup.
- **Multi-Format Proxy Manager:**
  - Parses and validates `host:port`, `host:port:user:pass`, and `protocol://user:pass@host:port` (`http`, `https`, `socks5`).
  - Measures live proxy latency (`ms`) and routes Playwright browser contexts through the selected proxy.
  - Excludes proxy passwords from API responses (`ProxyResponse`) to prevent credential exposure.
- **Universal Excel (`.xlsx`) Export:**
  - Generates clean `.xlsx` workbooks with English column headers, frozen top row (`A2`), numeric prices and ratings, clickable `Product URL` and `Image URL` hyperlinks, XML control-character sanitization, and normalized relative ZIP relationships compatible with Microsoft Excel, LibreOffice Calc, WPS Office, and Google Sheets.
- **Installable Light-Theme PWA Dashboard:**
  - Clean light-mode UI with custom number steppers, real-time progress bar, instant product search & task filtering, proxy management modal, and Service Worker caching (`sw.js`).

---

## Project Structure

```text
Aliparser/
├── README.md                      # Project documentation
├── requirements.txt               # Python package dependencies
├── run_app.py                     # Uvicorn server entry point (0.0.0.0:8000)
├── data/
│   └── aliparser.db               # SQLite database (auto-created at runtime, git-ignored)
├── src/
│   ├── api/
│   │   ├── app.py                 # FastAPI application, REST endpoints & PWA static routes
│   │   └── schemas.py             # Pydantic v2 request and response models
│   ├── db/
│   │   ├── database.py            # SQLite WAL engine, session generator & product upsert logic
│   │   └── models.py              # SQLAlchemy 2.0 ORM models (Product, ParsingTask, Proxy)
│   ├── parser/
│   │   ├── aliexpress.py          # Async Playwright stealth scraper & _dida_config_ extractor
│   │   └── proxy_manager.py       # Multi-format proxy parser & async connectivity checker
│   ├── services/
│   │   ├── exporter.py            # OpenPyXL .xlsx workbook builder & XML sanitizer
│   │   └── task_runner.py         # Singleton background scraping orchestrator with live ETA
│   └── web/
│       └── static/
│           ├── index.html         # Light-theme English PWA dashboard
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

## Installation & Setup

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Python dependencies and Playwright Chromium:**
   ```bash
   venv/bin/pip install -r requirements.txt
   venv/bin/playwright install chromium
   ```

---

## Running the Application

Start the FastAPI server using the unified launcher:

```bash
venv/bin/python run_app.py
```

- **Web Dashboard (PWA):** `http://127.0.0.1:8000`
- **Interactive API Docs (Swagger UI):** `http://127.0.0.1:8000/docs`

---

## REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/parser/start` | Start a background scraping task (`target`, `max_pages`, `proxy_id`, `delay_seconds`) |
| `GET` | `/api/parser/status` | Poll live task status, progress percentage, speed (`items/s`), and ETA |
| `POST` | `/api/parser/stop` | Gracefully stop the active scraping task |
| `GET` | `/api/parser/tasks` | List the last 20 scraping task records |
| `GET` | `/api/products` | List scraped products with optional `search`, `task_id`, `limit`, and `offset` filters |
| `GET` | `/api/products/export` | Download filtered or all products as a formatted `.xlsx` spreadsheet |
| `DELETE` | `/api/products` | Clear all products or delete products for a specific `task_id` |
| `GET` | `/api/proxies` | List all configured proxy servers |
| `POST` | `/api/proxies` | Add/update a proxy server and optionally check connectivity |
| `POST` | `/api/proxies/{id}/check` | Run a live connectivity and latency check for a stored proxy |
| `DELETE` | `/api/proxies/{id}` | Delete a proxy server by ID |

---

## Running Verification & E2E Tests

- **Full End-to-End (E2E) & Architecture Audit:**
  ```bash
  venv/bin/python scripts/test_e2e_full.py
  ```

- **Module & Integration Test Suite:**
  ```bash
  venv/bin/python scripts/test_db_and_proxy.py && \
  venv/bin/python scripts/test_task_runner.py && \
  venv/bin/python scripts/test_api_and_export.py && \
  venv/bin/python scripts/test_pwa.py
  ```

- **Standalone CLI Scraper Check:**
  ```bash
  venv/bin/python scripts/test_scraper.py --query "usb c hub" --pages 1
  ```
