# ТЗ №7: Фінальний архітектурний аудит, стабілізація (WAL & Recovery), наскрізне E2E тестування та документація

## СУВОРЕ ОБМЕЖЕННЯ БЕЗПЕКИ
* **КАТЕГОРИЧНО ЗАБОРОНЕНО** запускати системні пакетні менеджери або команди підвищення привілеїв (`sudo`, `pkexec`, `apt`, `apt-get`, `dpkg`, `snap`, `flatpak`) чи встановлювати будь-які системні пакети в ОС.
* Працювати **виключно** з файлами проекту всередині `/home/dofi/Dev/Aliparser` та локальним інтерпретатором `venv/bin/python`.

---

## Мета
Провести фінальний інженерний аудит архітектури, усунути потенційні вузькі місця при одночасній роботі фонового парсера та веб-інтерфейсу, перевірити систему наскрізним E2E-тестом на реальних даних AliExpress та оформити фінальну документацію проекту:
1. **Стабілізація конкурентного доступу до SQLite (`src/db/database.py`):** увімкнути режим `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;` та `timeout=30`, щоб виключити помилки `database is locked` під час одночасного запису товарів фоновим парсером і щосекундного опитування API з фронтенду.
2. **Автоматичне відновлення станів після перезапуску (`src/db/database.py`):** під час `init_db()` переводити будь-які «завислі» з минулих сесій задачі зі статусом `"running"` або `"stopping"` у `"stopped"`, щоб база завжди мала чистий стан при старті сервера.
3. **Підвищення надійності скрапера (`src/parser/aliexpress.py`):** додати автоматичний м'який ретрай усередині `scrape_page`, якщо через повільну мережу перше зчитування сторінки повернуло 0 товарів (додаткове очікування 2 с + прокрутка + повторне вилучення).
4. **Оновлення кешу Service Worker (`src/web/static/sw.js`):** оновити `CACHE_NAME = "aliparser-pwa-v2"`, щоб браузер завжди віддавав актуальну світлу тему.
5. **Створення комплексного наскрізного E2E-тесту (`scripts/test_e2e_full.py`):** перевірка повного циклу роботи (реальний парсинг через API, живі метрики та ETA, фільтрація товарів, експорт реальних даних в Excel, робота з проксі, стрес-тест паралельних запитів та Graceful Stop).
6. **Оформлення `README.md`:** чітка інструкція зі структурою проекту, запуском сервера та перевіркою тестів.

---

## Структура файлів до створення / модифікації
```text
/home/dofi/Dev/Aliparser/
├── README.md                          # Фінальна документація проекту (архітектура, запуск, API, тести)
├── src/
│   ├── db/
│   │   └── database.py                # SQLite WAL-режим, busy_timeout=30000, очистка завислих running-задач при старті
│   ├── parser/
│   │   └── aliexpress.py              # Захист від порожньої видачі (auto-retry при 0 товарів на сторінці)
│   └── web/
│       └── static/
│           └── sw.js                  # Оновлення CACHE_NAME до aliparser-pwa-v2
└── scripts/
    └── test_e2e_full.py               # Повний наскрізний E2E тест та архітектурний аудит усіх вузлів
```

---

## Детальні вимоги до реалізації

### 1. Стабілізація БД та конкурентного доступу `src/db/database.py`
* У `create_engine`: передати `connect_args={"check_same_thread": False, "timeout": 30}`.
* Додати обробник події підключення SQLAlchemy (`@event.listens_for(engine, "connect")`):
  ```python
  @event.listens_for(engine, "connect")
  def _set_sqlite_pragma(dbapi_connection, _connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL;")
      cursor.execute("PRAGMA synchronous=NORMAL;")
      cursor.execute("PRAGMA busy_timeout=30000;")
      cursor.close()
  ```
* У функції `init_db()`:
  * Крім існуючого очищення старих бейджів у `products`, додати скидання незавершених задач у таблиці `parsing_tasks`: якщо є записи зі `status IN ('running', 'stopping')`, оновити їм `status = 'stopped'` та `finished_at = utc_now()`.

---

### 2. Підвищення надійності `scrape_page` у `src/parser/aliexpress.py`
* Винести JS-логіку збору даних зі сторінки в допоміжний метод `async def _extract_items_from_page(self, page: Page) -> List[Dict[str, Any]]`.
* У `scrape_page`:
  * Якщо перший виклик `_extract_items_from_page(page)` повернув порожній список (`len(raw_data) == 0`), виконати 1 автоматичний повтор: почекати `await page.wait_for_timeout(2000)`, прокрутити сторінку `await page.evaluate("window.scrollTo(0, 600)")`, почекати `800ms` і повторно викликати `_extract_items_from_page(page)`.

---

### 3. Оновлення версії кешу PWA `src/web/static/sw.js`
* Змінити `const CACHE_NAME = "aliparser-pwa-v2";`, щоб при оновленні додатка старий кеш автоматично видалявся під час події `activate`.

---

### 4. Наскрізний E2E та архітектурний тест `scripts/test_e2e_full.py`
Створити скрипт `scripts/test_e2e_full.py`, який послідовно виконує повний аудит системи:
1. **Перевірка конфігурації SQLite WAL:**
   * Перевіряє, що `PRAGMA journal_mode` повертає `"wal"`.
2. **E2E Реальний збір за пошуковим запитом через FastAPI + TaskRunner:**
   * Викликає `await start_parser(StartParserRequest(target="wireless mouse", max_pages=1, delay_seconds=0.5))` (або через `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`).
   * Опитує `GET /api/parser/status` кожні `0.5` с, перевіряючи роботу живих індикаторів (`is_running`, `elapsed_seconds`, `estimated_remaining_seconds`) до переходу в `status == "completed"`.
   * Перевіряє, що зібрано `>= 15` реальних товарів з AliExpress, і жоден товар не має промо-бейджа (`154x64`, `48x48`, `S1887a285b60743859ac7bdbfca5e0896Z`) у `image_url`.
3. **E2E Реальний збір за прямим URL каталогу/категорії:**
   * Запускає задачу на 1 сторінку за прямим URL (`https://www.aliexpress.com/w/wholesale-usb-flash-drive.html`), очікує завершення та перевіряє збереження нових товарів у БД.
4. **E2E Перевірка фільтрації, проксі та експорту реальних товарів у Excel (`.xlsx`):**
   * Перевіряє `GET /api/products?search=usb` та фільтр за `task_id`.
   * Викликає `GET /api/products/export`, завантажує згенерований `.xlsx` у `openpyxl.load_workbook`, перевіряє англомовні заголовки, кількість рядків, числові ціни, клікабельні гіперпосилання та відносні шляхи у `xl/_rels/workbook.xml.rels`.
5. **E2E Стрес-тест станів (409 Conflict при подвійному запуску + Graceful Stop):**
   * Запускає довгу задачу (на 3 сторінки), перевіряє, що повторний `POST /api/parser/start` повертає `409 Conflict`, після чого викликає `POST /api/parser/stop` і підтверджує чистий перехід у статус `"stopped"`.
6. Виводить фінальний вердикт: `ALL E2E & ARCHITECTURE AUDIT TESTS PASSED`.

---

### 5. Фінальна документація `README.md`
Створити охайний `README.md` англійською та українською мовами з описом:
* Можливостей системи (Playwright Stealth + `_dida_config_` JSON extraction, Live Telemetry & ETA, Proxy Manager, Light Theme PWA, Excel Export).
* Структури проекту.
* Інструкції швидкого запуску (`venv/bin/python run_app.py` $\rightarrow$ `http://localhost:8000`).
* Команд для запуску всіх тестів.

---

## Критерії приймання та верифікація (Verification)
1. **Запуск повного E2E аудиту:**
   ```bash
   venv/bin/python scripts/test_e2e_full.py
   ```
   *Очікуваний результат:* проходження всіх 5 етапів наскрізного тестування та вивід `ALL E2E & ARCHITECTURE AUDIT TESTS PASSED`.
2. **Запуск усіх модульних тестів для підтвердження відсутності регресій:**
   ```bash
   venv/bin/python scripts/test_db_and_proxy.py && venv/bin/python scripts/test_task_runner.py && venv/bin/python scripts/test_api_and_export.py && venv/bin/python scripts/test_pwa.py
   ```

---

## Обов'язковий фінальний крок (Автоматичний Git Commit & Push)
Після успішного проходження верифікації агент у Чаті 2 **ЗОБОВ'ЯЗАНИЙ самостійно виконати** в терміналі команду фіксації та відправки змін на GitHub:
```bash
git add . && git commit -m "chore: complete E2E test suite, SQLite WAL stabilization, scraper retry resilience, and README" && git push origin main
```

---

## Формат звіту після виконання (у Чат 2)
1. Список створених та модифікованих файлів.
2. Лог виконання `scripts/test_e2e_full.py` та модульних тестів.
3. Підтвердження виконання `git commit` та `git push origin main` (із хешем коміту).
