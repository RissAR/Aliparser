# ТЗ №4: REST API (FastAPI) та Сервіс Експорту в Excel (.xlsx)

## Мета
Побудувати повноцінний REST API на базі FastAPI для керування парсером, роботи зі списком товарів, управління проксі-серверами та вивантаження результатів у форматований Excel-файл (`.xlsx`) із клікабельними посиланнями на товари.

---

## Структура файлів до створення / модифікації
```text
/home/dofi/Dev/Aliparser/
├── requirements.txt                   # Додати fastapi, uvicorn, openpyxl
├── run_app.py                         # Точка входу для запуску FastAPI сервера через uvicorn
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py                 # Pydantic-схеми запитів та відповідей API
│   │   └── app.py                     # FastAPI додаток та всі REST ендпоінти
│   └── services/
│       └── exporter.py                # Генерація .xlsx книги з форматуванням та гіперпосиланнями
└── scripts/
    └── test_api_and_export.py         # Комплексний тест усіх ендпоінтів API та структури Excel-файлу
```

---

## Детальні вимоги до реалізації

### 1. Оновлення `requirements.txt`
Зберегти існуючі залежності та додати:
* `fastapi>=0.110.0`
* `uvicorn>=0.29.0`
* `openpyxl>=3.1.2`

---

### 2. Сервіс експорту в Excel `src/services/exporter.py`
Створити функцію `generate_products_excel(products: List[Product]) -> bytes`:
* Використовує `openpyxl.Workbook()`. Назва активного аркуша: `"AliExpress Products"`.
* **Заголовки стовпців (Рядок 1):**
  1. `ID товару` (`item_id`)
  2. `Назва товару` (`title`)
  3. `Ціна` (`price` — числовий тип float)
  4. `Стара ціна` (`original_price` — числовий тип float або порожньо)
  5. `Валюта` (`currency`)
  6. `Рейтинг` (`rating` — числовий тип float або порожньо)
  7. `Замовлення` (`orders_count`)
  8. `Магазин` (`store_name`)
  9. `Категорія / Запит` (`category_or_query`)
  10. `Посилання на товар` (`product_url`)
  11. `Посилання на фото` (`image_url`)
  12. `Дата збору (UTC)` (`scraped_at` у форматі `YYYY-MM-DD HH:MM:SS`)
* **Стилізація та зручність:**
  * Зафіксувати перший рядок: `ws.freeze_panes = "A2"`.
  * Заголовок (рядок 1): жирний білий шрифт (`Font(bold=True, color="FFFFFF")`) на темному фоні (`PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")`), вирівнювання по центру.
  * Для колонки 10 (`Посилання на товар`): у кожному рядку даних встановлювати `cell.hyperlink = product.product_url` та синій підкреслений шрифт (`Font(color="2563EB", underline="single")`), щоб користувач міг у 1 клік відкрити товар з Excel.
  * Автоматичний підбір ширини колонок за довжиною вмісту з обмеженням `min_width = 12`, `max_width = 50`.
* Зберігає книгу в `io.BytesIO()` та повертає `bytes`.

---

### 3. Pydantic-схеми `src/api/schemas.py`
Описати моделі (сумісні з Pydantic v2 `ConfigDict(from_attributes=True)`):
* `StartParserRequest`:
  * `target`: `str`
  * `max_pages`: `int = Field(default=1, ge=1, le=50)`
  * `proxy_id`: `Optional[int] = None`
  * `delay_seconds`: `float = Field(default=1.5, ge=0.0, le=30.0)`
* `TaskStatusResponse`:
  * Повторює структуру словника `task_runner.get_status()` (`is_running`, `status`, `task_id`, `target`, `current_page`, `max_pages`, `completed_pages`, `progress_percent`, `items_scraped`, `proxy_id`, `started_at`, `finished_at`, `elapsed_seconds`, `estimated_remaining_seconds`, `items_per_second`, `error_message`).
* `ProductResponse`:
  * `id`: `int`, `item_id`: `str`, `title`: `str`, `price`: `float`, `original_price`: `Optional[float]`, `currency`: `str`, `rating`: `Optional[float]`, `orders_count`: `Optional[str]`, `store_name`: `Optional[str]`, `product_url`: `str`, `image_url`: `Optional[str]`, `category_or_query`: `Optional[str]`, `task_id`: `Optional[int]`, `scraped_at`: `datetime`
* `ProductListResponse`:
  * `total`: `int`
  * `items`: `List[ProductResponse]`
* `ProxyCreateRequest`:
  * `raw_proxy`: `str`
  * `check_connectivity`: `bool = False`
* `ProxyResponse`:
  * `id`: `int`, `raw_proxy`: `str`, `protocol`: `str`, `host`: `str`, `port`: `int`, `username`: `Optional[str]`, `is_active`: `bool`, `is_working`: `Optional[bool]`, `latency_ms`: `Optional[int]`, `last_checked_at`: `Optional[datetime]`, `created_at`: `datetime`

---

### 4. FastAPI Додаток `src/api/app.py` та `run_app.py`
* Ініціалізувати `init_db()` при старті модуля / lifespan.
* Підключити `CORSMiddleware` (`allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`).
* Реалізувати маршрути:

#### А. Керування парсером
1. `POST /api/parser/start` (`response_model=TaskStatusResponse`):
   * Викликає `await task_runner.start_task(target=req.target, max_pages=req.max_pages, proxy_id=req.proxy_id, delay_seconds=req.delay_seconds)`.
   * Якщо виникає `RuntimeError` (парсер вже працює) — повертає `HTTPException(status_code=409, detail=str(exc))`.
   * Якщо виникає `ValueError` (невалідні параметри або неіснуючий `proxy_id`) — повертає `HTTPException(status_code=400, detail=str(exc))`.
   * Повертає `task_runner.get_status()`.
2. `GET /api/parser/status` (`response_model=TaskStatusResponse`):
   * Повертає поточний стан та метрики `task_runner.get_status()`.
3. `POST /api/parser/stop` (`response_model=TaskStatusResponse`):
   * Викликає `await task_runner.stop_task()` і повертає оновлений статус.
4. `GET /api/parser/tasks`:
   * Повертає останні 20 записів `ParsingTask` з БД, відсортовані за `id.desc()`.

#### Б. Робота з товарами та вивантаження в Excel
5. `GET /api/products` (`response_model=ProductListResponse`):
   * Параметри запиту: `search: Optional[str] = None`, `task_id: Optional[int] = None`, `limit: int = Query(default=100, ge=1, le=1000)`, `offset: int = Query(default=0, ge=0)`.
   * Якщо передано `search` — фільтрує товари, де `title`, `store_name` або `category_or_query` містять підрядок (`ilike(f"%{search}%")`).
   * Якщо передано `task_id` — додатково фільтрує за `Product.task_id == task_id`.
   * Сортування: за `Product.scraped_at.desc(), Product.id.desc()`.
   * Повертає загальну кількість (`total`) за фільтром та зріз `items`.
6. `GET /api/products/export`:
   * Приймає опціональні параметри фільтрації `search: Optional[str] = None`, `task_id: Optional[int] = None`.
   * Вибирає всі відповідні товари з БД, генерує байти `.xlsx` через `generate_products_excel(products)`.
   * Повертає `Response` з:
     * `content=excel_bytes`
     * `media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"`
     * `headers={"Content-Disposition": 'attachment; filename="aliexpress_products.xlsx"'}`
7. `DELETE /api/products`:
   * Приймає опціональний параметр `task_id: Optional[int] = None`. Видаляє відповідні (або всі) товари з таблиці `products`. Повертає `{"deleted": deleted_count}`.

#### В. Керування проксі
8. `GET /api/proxies` (`response_model=List[ProxyResponse]`):
   * Повертає список усіх проксі з БД (`order_by(Proxy.id.desc())`).
9. `POST /api/proxies` (`response_model=ProxyResponse`):
   * Парсить `req.raw_proxy` через `parse_proxy_string`. При `ValueError` повертає `HTTPException(status_code=400, detail=str(exc))`.
   * Якщо проксі з таким `raw_proxy` вже існує в БД — оновлює його поля, інакше створює новий запис `Proxy`.
   * Якщо `req.check_connectivity == True`, виконує `await check_proxy_connectivity(proxy_obj)`, записує `is_working`, `latency_ms` та `last_checked_at = utc_now()`.
   * Зберігає в БД та повертає `ProxyResponse`.
10. `POST /api/proxies/{proxy_id}/check` (`response_model=ProxyResponse`):
    * Знаходить проксі за `proxy_id` (якщо немає — `404 Not Found`).
    * Запускає `await check_proxy_connectivity(proxy_obj)`, оновлює `is_working`, `latency_ms`, `last_checked_at = utc_now()`, зберігає та повертає оновлений об'єкт.
11. `DELETE /api/proxies/{proxy_id}`:
    * Видаляє проксі за `proxy_id` (якщо немає — `404 Not Found`). Повертає `{"deleted": True, "id": proxy_id}`.

#### Г. Точка входу `run_app.py`
* Запускає сервер `uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=False)`.

---

### 5. Верифікаційний скрипт `scripts/test_api_and_export.py`
Написати комплексний тест із використанням `fastapi.testclient.TestClient(app)`, який перевіряє:
1. `GET /api/parser/status` — повертає 200 та валідну схему статусу.
2. `POST /api/proxies` — успішне додавання проксі (`10.20.30.40:8080:myuser:mypass`), перевірка `400 Bad Request` на некоректний рядок (`invalid_proxy_str`), отримання списку `GET /api/proxies` та видалення `DELETE /api/proxies/{id}`.
3. Додавання тестових товарів у БД та перевірка `GET /api/products` (загальний список + пошук `?search=...`).
4. Перевірка `GET /api/products/export`:
   * Статус `200`, заголовок `content-type` відповідає `.xlsx`.
   * Завантаження байтів відповіді через `openpyxl.load_workbook(io.BytesIO(response.content))`.
   * Перевірка наявності аркуша `"AliExpress Products"`, заголовків у 1-му рядку, даних у 2-му рядку та наявності клікабельного `cell.hyperlink.target` у колонці посилання на товар.
5. Вивід фінального рядка: `ALL API & EXCEL EXPORT TESTS PASSED`.

---

## Критерії приймання та верифікація (Verification)
1. **Встановлення нових залежностей:**
   ```bash
   venv/bin/pip install -r requirements.txt
   ```
2. **Запуск комплексного тесту API та Excel-експорту:**
   ```bash
   venv/bin/python scripts/test_api_and_export.py
   ```
   *Очікуваний результат:* усі перевірки проходять без помилок і виводиться `ALL API & EXCEL EXPORT TESTS PASSED`.

---

## Обов'язковий фінальний крок (Автоматичний Git Commit & Push)
Після успішного проходження верифікації агент у Чаті 2 **ЗОБОВ'ЯЗАНИЙ самостійно виконати** в терміналі команду фіксації та відправки змін на GitHub:
```bash
git add . && git commit -m "feat: implement FastAPI REST endpoints and Excel export service" && git push origin main
```

---

## Формат звіту після виконання (у Чат 2)
1. Список створених та модифікованих файлів.
2. Лог виконання `scripts/test_api_and_export.py`.
3. Підтвердження виконання `git commit` та `git push origin main` (із хешем коміту).
