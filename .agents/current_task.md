# ТЗ №2: Структура бази даних (SQLite + SQLAlchemy) та Менеджер Проксі (DB & Proxy Manager)

## Мета
Створити шар збереження даних (SQLite + SQLAlchemy) та модуль керування проксі-серверами:
1. Реалізувати моделі бази даних: `Product` (зібрані товари з захистом від дублікатів), `ParsingTask` (історія та стан запусків парсера), `Proxy` (список проксі та їхній статус).
2. Реалізувати логіку `upsert_products` для збереження та оновлення товарів за унікальним `item_id` без дублювання записів.
3. Створити модуль `proxy_manager.py`, який розпізнає різні формати проксі (`ip:port`, `ip:port:user:pass`, `http://...`, `socks5://...`), конвертує їх у формат для Playwright та асинхронно перевіряє їхню працездатність і пінг (`latency_ms`).
4. Написати та запустити верифікаційний скрипт `scripts/test_db_and_proxy.py`.
5. Виконати автоматичний git commit та git push у репозиторій GitHub.

---

## Структура файлів до створення / модифікації
```text
/home/dofi/Dev/Aliparser/
├── requirements.txt                   # Додати sqlalchemy>=2.0.0 та httpx[socks]>=0.27.0
├── src/
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                  # Моделі SQLAlchemy: Product, ParsingTask, Proxy
│   │   └── database.py                # Ініціалізація SQLite, сесії та функція upsert_products
│   └── parser/
│       └── proxy_manager.py           # Парсинг рядків проксі, конвертація для Playwright, перевірка пінгу
└── scripts/
    └── test_db_and_proxy.py           # Автономний тест БД, upsert-логіки та парсингу проксі
```

---

## Детальні вимоги до реалізації

### 1. Оновлення `requirements.txt`
Зберегти існуючі залежності та додати:
* `sqlalchemy>=2.0.0`
* `httpx[socks]>=0.27.0`

---

### 2. Моделі бази даних `src/db/models.py`
Використовувати `DeclarativeBase` із SQLAlchemy 2.0:

1. **Модель `Proxy` (таблиця `proxies`):**
   * `id`: ` int` (Primary Key, autoincrement)
   * `raw_proxy`: `str` (Unique, nullable=False) — початковий рядок або канонічний ключ `protocol://host:port:user`
   * `protocol`: `str` (default `"http"`) — `http`, `https`, `socks5`
   * `host`: `str` (nullable=False)
   * `port`: `int` (nullable=False)
   * `username`: `Optional[str]` (nullable=True)
   * `password`: `Optional[str]` (nullable=True)
   * `is_active`: `bool` (default `True`)
   * `is_working`: `Optional[bool]` (nullable=True — `None` якщо ще не перевірено, `True` / `False` після перевірки)
   * `latency_ms`: `Optional[int]` (nullable=True — пінг у мс)
   * `last_checked_at`: `Optional[datetime]` (nullable=True)
   * `created_at`: `datetime` (default UTC now)

2. **Модель `ParsingTask` (таблиця `parsing_tasks`):**
   * `id`: `int` (Primary Key, autoincrement)
   * `target`: `str` (nullable=False) — URL категорії або пошуковий запит
   * `max_pages`: `int` (default `1`)
   * `current_page`: `int` (default `0`)
   * `status`: `str` (default `"idle"`) — можливі стани: `idle`, `running`, `completed`, `stopped`, `error`
   * `items_scraped`: `int` (default `0`)
   * `proxy_id`: `Optional[int]` (ForeignKey `"proxies.id"`, nullable=True)
   * `error_message`: `Optional[str]` (Text, nullable=True)
   * `started_at`: `Optional[datetime]` (nullable=True)
   * `finished_at`: `Optional[datetime]` (nullable=True)
   * `created_at`: `datetime` (default UTC now)

3. **Модель `Product` (таблиця `products`):**
   * `id`: `int` (Primary Key, autoincrement)
   * `item_id`: `str` (Unique, Index, nullable=False) — ID товару на AliExpress
   * `title`: `str` (nullable=False)
   * `price`: `float` (nullable=False)
   * `original_price`: `Optional[float]` (nullable=True)
   * `currency`: `str` (default `"USD"`)
   * `rating`: `Optional[float]` (nullable=True)
   * `orders_count`: `Optional[str]` (nullable=True)
   * `store_name`: `Optional[str]` (nullable=True)
   * `product_url`: `str` (nullable=False)
   * `image_url`: `Optional[str]` (nullable=True)
   * `category_or_query`: `Optional[str]` (nullable=True) — запит або URL, за яким знайдено товар
   * `task_id`: `Optional[int]` (ForeignKey `"parsing_tasks.id"`, nullable=True)
   * `scraped_at`: `datetime` (default UTC now, оновлюється при повторному парсингу)

---

### 3. Підключення та операції БД `src/db/database.py`
* База даних зберігається за шляхом `data/aliparser.db` (автоматично створювати папку `data/`, якщо її немає).
* `engine = create_engine("sqlite:///data/aliparser.db", connect_args={"check_same_thread": False})`.
* `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`.
* Функція `init_db() -> None`: створює таблиці (`Base.metadata.create_all(bind=engine)`).
* Генератор `get_db()`: повертає сесію та закриває її в блоці `finally`.
* Функція `upsert_products(db: Session, items: List[AliProductItem], category_or_query: Optional[str] = None, task_id: Optional[int] = None) -> int`:
  * Для кожного `AliProductItem`: якщо запис з таким `item_id` вже є в таблиці `products` — оновлює `title`, `price`, `original_price`, `currency`, `rating`, `orders_count`, `store_name`, `product_url`, `image_url`, `category_or_query`, `task_id`, `scraped_at`. Якщо немає — додає новий `Product`.
  * Виконує `db.commit()` та повертає кількість оброблених товарів.

---

### 4. Менеджер Проксі `src/parser/proxy_manager.py`
* Функція `parse_proxy_string(raw_proxy: str) -> dict`:
  * Приймає рядок проксі у будь-якому з популярних форматів:
    1. `host:port` (за замовчуванням `http`)
    2. `host:port:username:password` (за замовчуванням `http`)
    3. `protocol://host:port` (`http`, `https`, `socks5`)
    4. `protocol://username:password@host:port`
  * Повертає словник: `{"raw_proxy": ..., "protocol": ..., "host": ..., "port": int, "username": ..., "password": ...}`.
  * Якщо формат некоректний — викидає `ValueError` зі зрозумілим описом.
* Функція `to_playwright_proxy(proxy_data: Union[Proxy, dict]) -> dict`:
  * Повертає словник для Playwright:
    `{"server": f"{protocol}://{host}:{port}"}` (+ `"username"` та `"password"`, якщо вони задані).
* Функція `to_httpx_proxy_url(proxy_data: Union[Proxy, dict]) -> str`:
  * Формує URL рядка підключення для `httpx`: `protocol://[user:pass@]host:port`.
* Асинхронна функція `check_proxy_connectivity(proxy_data: Union[Proxy, dict], timeout: float = 10.0) -> tuple[bool, Optional[int], Optional[str]]`:
  * Виконує тестовий GET-запит через `httpx.AsyncClient(proxy=proxy_url, timeout=timeout)` до `https://api.ipify.org?format=json` (або `https://www.aliexpress.com`).
  * Вимірює час відповіді у мілісекундах (`latency_ms`).
  * Повертає кортеж: `(is_working: bool, latency_ms: Optional[int], error_message: Optional[str])`.

---

### 5. Верифікаційний скрипт `scripts/test_db_and_proxy.py`
Скрипт повинен послідовно перевірити:
1. Ініціалізацію БД (`init_db()`).
2. Парсинг усіх 4 форматів проксі (`1.2.3.4:8080`, `1.2.3.4:8080:user1:pass1`, `socks5://5.6.7.8:1080`, `http://admin:secret@9.10.11.12:3128`) та конвертацію у Playwright-формат.
3. Збереження проксі та задачі `ParsingTask` у БД.
4. Роботу `upsert_products`:
   * Додавання 2 тестових `AliProductItem`.
   * Повторний виклик `upsert_products` з тим самим `item_id`, але новою ціною (перевірка, що кількість записів у БД не продублювалася, а ціна оновилася).
5. Виведення чіткого звіту `ALL DB & PROXY TESTS PASSED` у консоль.

---

## Критерії приймання та верифікація (Verification)
1. **Встановлення нових залежностей:**
   ```bash
   venv/bin/pip install -r requirements.txt
   ```
2. **Запуск тесту БД та проксі-менеджера:**
   ```bash
   venv/bin/python scripts/test_db_and_proxy.py
   ```
   *Очікуваний результат:* скрипт проходить усі перевірки без помилок і виводить `ALL DB & PROXY TESTS PASSED`.

---

## Обов'язковий фінальний крок (Автоматичний Git Commit & Push)
Після успішного проходження верифікації агент у Чаті 2 **ЗОБОВ'ЯЗАНИЙ самостійно виконати** в терміналі команду фіксації та відправки змін на GitHub:
```bash
git add . && git commit -m "feat: add SQLite database models, product upsert logic, and proxy manager" && git push origin main
```

---

## Формат звіту після виконання (у Чат 2)
1. Список створених та модифікованих файлів.
2. Лог виконання `scripts/test_db_and_proxy.py`.
3. Підтвердження виконання `git commit` та `git push origin main` (із хешем коміту).
