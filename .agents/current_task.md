# ТЗ №5: Англомовний PWA Веб-Інтерфейс (Progressive Web App Dashboard)

## Мета
Створити легкий, сучасний та повністю англомовний PWA-додаток (Progressive Web App), інтегрований із FastAPI бекендом, який дозволяє:
1. Запускати та зупиняти парсер для будь-якої категорії або пошукового запиту AliExpress.
2. Відстежувати живі індикатори роботи в реальному часі: поточний статус, анімований прогрес-бар, таймер витраченого часу (`Elapsed Time`), розрахунковий час до завершення (`ETA`), кількість зібраних товарів та швидкість збору.
3. Керувати списком проксі-серверів (додавання, тестування пінгу/працездатності, видалення, вибір активного проксі для парсингу).
4. Переглядати, шукати та фільтрувати зібрані товари прямо в таблиці з фотографіями, цінами, рейтингами та прямими клікабельними посиланнями на AliExpress.
5. Вивантажувати зібрані товари в Excel (`.xlsx`) у 1 клік.

---

## Структура файлів до створення / модифікації
```text
/home/dofi/Dev/Aliparser/
├── src/
│   ├── api/
│   │   └── app.py                     # Підключення статики та маршрутів PWA (/, /manifest.json, /sw.js, /icon.svg)
│   └── web/
│       └── static/
│           ├── index.html             # Головний англомовний інтерфейс (Tailwind CSS + Lucide Icons + JS)
│           ├── manifest.json          # PWA Web App Manifest
│           ├── sw.js                  # Service Worker для PWA
│           └── icon.svg               # Векторна іконка додатка
└── scripts/
    └── test_pwa.py                    # Автономний тест доступності PWA-маршрутів та ресурсів
```

---

## Детальні вимоги до реалізації

### 1. Роздача статики та PWA маршрутів у `src/api/app.py`
Додати в `src/api/app.py` (зберегти всі існуючі API-ендпоінти без змін):
* Підключити `StaticFiles` для `/static` із папки `src/web/static`.
* Додати маршрути (через `FileResponse`):
  * `GET /` $\rightarrow$ `src/web/static/index.html`
  * `GET /manifest.json` $\rightarrow$ `src/web/static/manifest.json` (`media_type="application/manifest+json"`)
  * `GET /sw.js` $\rightarrow$ `src/web/static/sw.js` (`media_type="application/javascript"`)
  * `GET /icon.svg` $\rightarrow$ `src/web/static/icon.svg` (`media_type="image/svg+xml"`)

---

### 2. PWA Конфігурація (`manifest.json`, `sw.js`, `icon.svg`)
* `src/web/static/icon.svg`: стильна мінімалістична SVG-іконка (512x512 viewBox, градієнт indigo/orange, символ радара/кошика).
* `src/web/static/manifest.json`:
  * `name`: `"AliParser — AliExpress Scraper"`
  * `short_name`: `"AliParser"`
  * `start_url`: `"/"`
  * `display`: `"standalone"`
  * `background_color`: `"#0f172a"`
  * `theme_color`: `"#4f46e5"`
  * `icons`: посилання на `/icon.svg` (`sizes: "any"`, `type: "image/svg+xml"`, `purpose: "any maskable"`).
* `src/web/static/sw.js`:
  * Кешує базову оболонку (`/`, `/manifest.json`, `/icon.svg`).
  * Для всіх запитів `/api/*` використовує `fetch(event.request)` (Network-only, без кешування динамічних даних API).

---

### 3. Англомовний Інтерфейс `src/web/static/index.html`
Усі написи, кнопки, підказки, статуси та таблиці мають бути **виключно англійською мовою**. Дизайн — сучасний темний дашборд (`bg-slate-950 text-slate-100`, картки `bg-slate-900 border-slate-800`, акценти `indigo-600` / `emerald-500`).

#### А. Верхня панель (Header)
* Логотип (`icon.svg`) + назва **"AliParser"** та підзаголовок `"Universal AliExpress Catalog & Search Scraper"`.
* Живий індикатор стану парсера у шапці (`Status Pill`: `IDLE`, `RUNNING`, `STOPPING`, `COMPLETED`, `STOPPED`, `ERROR` з пульсуючою точкою під час роботи).
* Кнопка **"Proxies (N)"** — відкриває модальне вікно керування проксі (`<dialog>`).
* Кнопка **"Export Excel (.xlsx)"** — завантажує файл `/api/products/export` (з урахуванням поточного пошукового фільтра та обраної задачі).

#### Б. Панель керування парсером (Scraper Control Card)
* **Target Input (`target`):**
  * Label: `"Search Query or Category URL"`
  * Placeholder: `"e.g. wireless mechanical keyboard or https://www.aliexpress.com/category/..."`
  * Швидкі чіпси (Quick Presets) під полем для зручного тестування в 1 клік: `wireless mouse`, `mechanical keyboard`, `usb c hub`, `smart watch`.
* **Max Pages (`max_pages`):** числове поле (`1` – `50`, за замовчуванням `1`).
* **Page Delay (`delay_seconds`):** числове поле (`0` – `30` sec, за замовчуванням `1.5`, крок `0.5`).
* **Proxy Selector (`proxy_id`):** випадаючий список:
  * За замовчуванням: `"Direct Connection (No Proxy)"` (`value=""`).
  * Усі збережені проксі з `/api/proxies` із відображенням їхнього статусу та пінгу (`http://1.2.3.4:8080 [OK 120ms]`).
* **Кнопки керування:**
  * **"Start Scraping"**: відправляє `POST /api/parser/start`. Під час виконання парсингу кнопка стає неактивною (`disabled`) та показує обертовий спінер.
  * **"Stop Parser"**: активна лише коли `is_running == true`, відправляє `POST /api/parser/stop` для безпечної зупинки.

#### В. Панель живих індикаторів та таймерів (Live Telemetry & Progress Panel)
Відображає телеметрію активного або останнього запуску (опитування `GET /api/parser/status` кожні `1000ms` під час роботи):
1. **Progress Bar:** плавний смугастий прогрес-бар (`0%` – `100%`) + текст `"Page X of Y (Z%)"`.
2. **Elapsed Time (Таймер роботи):** форматований час `MM:SS` на основі `elapsed_seconds`.
3. **Estimated Remaining (ETA — Скільки часу залишилось):** форматований час `MM:SS` на основі `estimated_remaining_seconds` (наприклад, `"~00:14 remaining"`, або `"—"`, коли парсер у стані `idle`/`completed`).
4. **Items Collected & Speed:** лічильник зібраних у поточній задачі товарів (`items_scraped`) та швидкість (`items_per_second` items/sec).
5. **Error Banner:** якщо API повертає помилку або в статусі є `error_message` — показувати помітний червоний банер із текстом помилки та кнопкою закриття `"Dismiss"`.

#### Г. Таблиця зібраних товарів (Scraped Products Catalog)
* **Панель інструментів таблиці:**
  * Поле пошуку `"Search products by title, store, or category..."` (із debounce 300ms).
  * Випадаючий список фільтрації за задачею `"All Scraping Runs"` + список останніх задач із `GET /api/parser/tasks` (`#ID - target (N items)`).
  * Лічильник: `"Total Products: N"`.
  * Кнопка **"Refresh"** та кнопка **"Clear All"** (`DELETE /api/products` з підтвердженням).
* **Стовпці таблиці:**
  1. **Product** — мініатюра фото (`referrerpolicy="no-referrer"`, з акуратним fallback-іконкою при помилці завантаження), повна назва товару, ID товару (`ID: 100500...`) та тег категорії/запиту (`category_or_query`).
  2. **Price** — актуальна ціна з валютою (`$19.99` або `UAH ...`), а поруч закреслена стара ціна (`original_price`), якщо вона є.
  3. **Rating & Orders** — зірочка з рейтингом (`4.8`) та бейдж кількості замовлень (`500+ sold`).
  4. **Store** — назва магазину (`store_name` або `"—"`).
  5. **Scraped At** — дата та час збору.
  6. **Action** — пряма кнопка-посилання **"View Item ↗"** (`href="${product_url}" target="_blank" rel="noopener noreferrer"`), що відкриває картку товару на AliExpress у новій вкладці.
* Під час активного парсингу таблиця автоматично оновлюється при збільшенні `items_scraped`, щоб користувач одразу бачив нові товари на екрані.

#### Д. Модальне вікно Проксі (Proxy Manager Modal)
* Поле введення нового проксі (`host:port`, `host:port:user:pass`, `http://...`, `socks5://...`).
* Чекбокс `"Test connectivity immediately"` (за замовчуванням увімкнений) + кнопка **"Add Proxy"**.
* Список доданих проксі з відображенням:
  * Адреса та протокол (`SOCKS5` / `HTTP`), наявність авторизації.
  * Статус: зелений бейдж `"Online (115 ms)"`, червоний `"Offline"`, або сірий `"Untested"`.
  * Кнопка **"Check"** (`POST /api/proxies/{id}/check`) зі спінером під час перевірки.
  * Кнопка **"Delete"** (`DELETE /api/proxies/{id}`).

---

### 4. Верифікаційний скрипт `scripts/test_pwa.py`
Написати тестовий скрипт з `TestClient(app)`, який перевіряє:
1. `GET /` повертає `200 OK`, `text/html`, і містить ключові англомовні елементи інтерфейсу (`AliParser`, `Start Scraping`, `Export Excel`, `Proxy Manager`, `manifest.json`).
2. `GET /manifest.json` повертає `200 OK` та валідний JSON з `"name"` та `"icons"`.
3. `GET /sw.js` повертає `200 OK` та код Service Worker.
4. `GET /icon.svg` повертає `200 OK` та `<svg`.
5. Виводить у консоль: `ALL PWA FRONTEND TESTS PASSED`.

---

## Критерії приймання та верифікація (Verification)
1. **Запуск тесту PWA:**
   ```bash
   venv/bin/python scripts/test_pwa.py
   ```
   *Очікуваний результат:* виводиться `ALL PWA FRONTEND TESTS PASSED`.
2. **Повторна перевірка існуючих API тестів (щоб переконатися у відсутності регресій):**
   ```bash
   venv/bin/python scripts/test_api_and_export.py
   ```

---

## Обов'язковий фінальний крок (Автоматичний Git Commit & Push)
Після успішного проходження верифікації агент у Чаті 2 **ЗОБОВ'ЯЗАНИЙ самостійно виконати** в терміналі команду фіксації та відправки змін на GitHub:
```bash
git add . && git commit -m "feat: implement English PWA frontend dashboard with live telemetry, proxy manager, and Excel export" && git push origin main
```

---

## Формат звіту після виконання (у Чат 2)
1. Список створених та модифікованих файлів.
2. Лог виконання `scripts/test_pwa.py` та `scripts/test_api_and_export.py`.
3. Підтвердження виконання `git commit` та `git push origin main` (із хешем коміту).
