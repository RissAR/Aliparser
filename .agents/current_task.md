# ТЗ №3: Фоновий таск-менеджер (Task Runner), керування станами та розрахунок часу (ETA)

## Мета
Створити асинхронний фоновий менеджер задач (`TaskRunner`), який керує життєвим циклом парсингу, зберігає знайдені товари в БД у реальному часі, дозволяє безпечно зупиняти збір (Graceful Stop) без втрати даних і обчислює точні метрики часу для фронтенд-індикаторів (`elapsed_seconds`, `estimated_remaining_seconds`, `progress_percent`, `items_per_second`).

---

## Структура файлів до створення / модифікації
```text
/home/dofi/Dev/Aliparser/
├── src/
│   └── services/
│       ├── __init__.py
│       └── task_runner.py             # Клас TaskRunner, стани, розрахунок ETA та глобальний екземпляр task_runner
└── scripts/
    └── test_task_runner.py            # Автономний тест життєвого циклу, таймінгів, ETA та Graceful Stop
```

---

## Детальні вимоги до реалізації

### 1. Менеджер задач `src/services/task_runner.py`

Створити клас `TaskRunner` та глобальний синглтон `task_runner = TaskRunner()`.

#### А. Стани та захист від паралельного запуску
* Допустимі стани (`status`): `"idle"`, `"running"`, `"stopping"`, `"completed"`, `"stopped"`, `"error"`.
* Одночасно може виконуватися лише одна задача парсингу. Якщо при виклику `start_task` поточний статус `"running"` або `"stopping"`, викидати `RuntimeError("A parsing task is already running.")`.

#### Б. Запуск задачі `async def start_task(...) -> int`
Сигнатура:
```python
async def start_task(
    self,
    target: str,
    max_pages: int = 1,
    proxy_id: Optional[int] = None,
    delay_seconds: float = 1.5,
    scraper_factory: Optional[Callable[[Optional[Dict[str, str]]], Any]] = None,
) -> int:
```
* Перевіряє, що `target` не порожній, а `max_pages >= 1`.
* Якщо передано `proxy_id`, отримує запис `Proxy` з БД (`SessionLocal`) і конвертує його через `to_playwright_proxy(proxy_obj)`. Якщо `proxy_id` не знайдено в БД — викидає `ValueError(f"Proxy with id={proxy_id} not found.")`.
* Створює запис `ParsingTask` у БД зі статусом `"running"`, `target=target`, `max_pages=max_pages`, `current_page=0`, `items_scraped=0`, `proxy_id=proxy_id`, `started_at=utc_now()`.
* Ініціалізує внутрішній `asyncio.Event` (`self._stop_event.clear()`) та запускає фонову корутину `self._bg_task = asyncio.create_task(self._run_loop(...))`.
* Повертає `task.id`.

#### В. Фоновий цикл виконання `async def _run_loop(...)`
* Використовує `AliExpressScraper(proxy=playwright_proxy, headless=True)` за замовчуванням, або викликає переданий `scraper_factory(playwright_proxy)` (це дозволяє ін'єктувати тестовий скрапер під час unit/integration тестування).
* Проходить у циклі `for page_num in range(1, max_pages + 1)`:
  1. Перевіряє `if self._stop_event.is_set(): break`.
  2. Оновлює поточну сторінку (`current_page = page_num`) у пам'яті та в записі `ParsingTask` у БД.
  3. Засікає час початку сторінки, викликає `items = await scraper.scrape_page(target, page_number=page_num)`.
  4. Зберігає отримані товари через `upsert_products(db, items, category_or_query=target, task_id=task_id)`.
  5. Оновлює `items_scraped += len(items)` та зберігає тривалість обробки сторінки у список `self._page_durations` для точного розрахунку ETA.
  6. Якщо `page_num < max_pages` і не встановлено `_stop_event`, очікує `delay_seconds` між сторінками за допомогою `asyncio.wait_for(self._stop_event.wait(), timeout=delay_seconds)` (щоб при натисканні «Стоп» пауза переривалася миттєво).
* Завершення циклу:
  * Якщо було викликано зупинку (`self._stop_event.is_set()` або `asyncio.CancelledError`): встановлює `status = "stopped"`, `finished_at = utc_now()`. Усі вже зібрані товари залишаються збереженими в БД.
  * Якщо всі сторінки пройдено успішно: встановлює `status = "completed"`, `finished_at = utc_now()`.
  * Якщо сталася виняткова ситуація (`Exception as exc`): логує помилку, встановлює `status = "error"`, `error_message = str(exc)`, `finished_at = utc_now()`.
* У блоці `finally` гарантовано закриває скрапер та сесію БД.

#### Г. Примусова зупинка `async def stop_task(self) -> Dict[str, Any]`
* Якщо задача не запущена (`status not in ("running", "stopping")`), повертає поточний `get_status()`.
* Встановлює `self._stop_event.set()` та змінює статус на `"stopping"`.
* Очікує завершення `self._bg_task` (із таймаутом, наприклад `10.0` секунд; якщо за цей час не завершилась — викликає `self._bg_task.cancel()`).
* Повертає оновлений `get_status()`.

#### Д. Отримання статусу та динамічних метрик `def get_status(self) -> Dict[str, Any]`
Повертає словник з повною інформацією про поточну (або останню виконану) задачу:
* `is_running`: `bool` (`status in ("running", "stopping")`)
* `status`: `str` (`"idle"`, `"running"`, `"stopping"`, `"completed"`, `"stopped"`, `"error"`)
* `task_id`: `Optional[int]`
* `target`: `Optional[str]`
* `current_page`: `int`
* `max_pages`: `int`
* `completed_pages`: `int` (кількість повністю оброблених сторінок)
* `progress_percent`: `float` — від `0.0` до `100.0` (коли `status == "completed"`, дорівнює `100.0`; під час роботи розраховується на основі `completed_pages / max_pages * 100`, округлено до 1 знака).
* `items_scraped`: `int`
* `proxy_id`: `Optional[int]`
* `started_at`: `Optional[str]` (ISO-формат або `None`)
* `finished_at`: `Optional[str]` (ISO-формат або `None`)
* `elapsed_seconds`: `float` (округлено до 1 знака: різниця між поточним часом `utc_now()` і `started_at` під час роботи, або між `finished_at` і `started_at` після завершення).
* `estimated_remaining_seconds`: `Optional[float]` (ETA в секундах):
  * Якщо `status not in ("running", "stopping")` — повертає `0.0` (або `None` для `"idle"`).
  * Якщо вже оброблено хоча б 1 сторінку (`len(self._page_durations) > 0`): середній час на сторінку (включно з `delay_seconds`) помножити на кількість сторінок, що залишилися (`max_pages - completed_pages`), мінус час, вже витрачений на поточну сторінку (не менше `0.5` с).
  * Якщо перша сторінка ще завантажується (`completed_pages == 0`): оцінка за замовчуванням `max(1.0, (8.0 * max_pages) - elapsed_seconds)`.
* `items_per_second`: `float` (`round(items_scraped / elapsed_seconds, 2)` якщо `elapsed_seconds > 0`, інакше `0.0`).
* `error_message`: `Optional[str]`

---

### 2. Верифікаційний скрипт `scripts/test_task_runner.py`
Написати комплексний асинхронний тест, який перевіряє 3 сценарії:
1. **Сценарій 1 (Повне виконання та розрахунок метрик):**
   * Запуск `task_runner.start_task(target="usb hub", max_pages=3, delay_seconds=0.2, scraper_factory=...)` із контрольованим фейк-скрапером (який імітує роботу по 0.3 с на сторінку та повертає по 5 `AliProductItem`).
   * Перевірка статусу посеред роботи (`is_running == True`, `elapsed_seconds > 0`, `estimated_remaining_seconds > 0`, `progress_percent` зростає).
   * Очікування завершення та перевірка фінального стану (`status == "completed"`, `items_scraped == 15`, `progress_percent == 100.0`, записи `Product` та `ParsingTask` збережені в SQLite).
2. **Сценарій 2 (Graceful Stop посеред роботи):**
   * Запуск задачі на 5 сторінок.
   * Після обробки 1–2 сторінок виклик `await task_runner.stop_task()`.
   * Перевірка, що статус став `"stopped"`, `finished_at` заповнено, а зібрані на перших сторінках товари збережені в БД.
3. **Сценарій 3 (Обробка помилки скрапера):**
   * Запуск із скрапером, що кидає `RuntimeError("Simulated network failure")`.
   * Перевірка, що `status == "error"`, а `error_message` містить текст помилки як у `get_status()`, так і в таблиці `parsing_tasks`.
4. Вивід фінального рядка: `ALL TASK RUNNER TESTS PASSED`.

---

## Критерії приймання та верифікація (Verification)
1. **Запуск тесту Task Runner:**
   ```bash
   venv/bin/python scripts/test_task_runner.py
   ```
   *Очікуваний результат:* усі 3 сценарії проходять успішно, виводиться `ALL TASK RUNNER TESTS PASSED`.

---

## Обов'язковий фінальний крок (Автоматичний Git Commit & Push)
Після успішного проходження верифікації агент у Чаті 2 **ЗОБОВ'ЯЗАНИЙ самостійно виконати** в терміналі команду фіксації та відправки змін на GitHub:
```bash
git add . && git commit -m "feat: implement async TaskRunner with live progress, ETA metrics, and graceful stop" && git push origin main
```

---

## Формат звіту після виконання (у Чат 2)
1. Список створених та модифікованих файлів.
2. Лог виконання `scripts/test_task_runner.py`.
3. Підтвердження виконання `git commit` та `git push origin main` (із хешем коміту).
