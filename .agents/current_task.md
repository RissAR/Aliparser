# ТЗ №6: Виправлення збору фото, оновлення експорту Excel (.xlsx), кастомні поля пагінації, очищення кнопок та Світла Тема (Light Theme UI)

## СУВОРЕ ОБМЕЖЕННЯ БЕЗПЕКИ
* **КАТЕГОРИЧНО ЗАБОРОНЕНО** запускати системні пакетні менеджери або команди підвищення привілеїв (`sudo`, `pkexec`, `apt`, `apt-get`, `dpkg`, `snap`, `flatpak`) чи встановлювати будь-які системні пакети в ОС.
* Працювати **виключно** з файлами проекту всередині `/home/dofi/Dev/Aliparser` та локальним інтерпретатором `venv/bin/python`.

---

## Мета
Усунути всі зауваження після ручного тестування та перевести інтерфейс на чисту сучасну **Світлу Тему (Light Theme)**:
1. **Виправити збір фотографій товарів (`src/parser/aliexpress.py` та `src/db/database.py`):** усунути потрапляння промо-бейджів (`Choice` `154x64.png`, `Brand+`, іконок зірочок) замість фото товару; брати оригінальні фото продукту з внутрішнього JSON-стейту `_dida_config_._init_data_` та відфільтрованої галереї картки; очистити вже збережені в БД бейджі.
2. **Оновити генерацію та скачування Excel-файлів (`src/services/exporter.py`, `src/web/static/index.html`):**
   * У `src/services/exporter.py`: англомовні заголовки, очистка рядків від заборонених у XML керуючих символів, 8-значні ARGB-кольори (`FF...`), нормалізація відносних шляхів у `xl/_rels/workbook.xml.rels`.
   * На фронтенді (`index.html`) реалізувати скачування Excel через `fetch` $\rightarrow$ `Blob` замість `window.location.href`.
3. **Замінити системні стрілочки полів `Max Pages` та `Page Delay`:** приховати старі браузерні спінери у стилі Windows XP за допомогою CSS і додати акуратні вбудовані кнопки **`−` / `+`**.
4. **Прибрати емодзі-стрілочку з кнопки `View Item`:** замінити `View Item ↗` на чистий текст `View Item` без юнікод-емодзі.
5. **Перевести весь інтерфейс на Світлу Тему (Light Theme):** білі картки (`bg-white`), світло-сірий фон сторінки (`bg-slate-50`), високий контраст тексту (`text-slate-900`), акуратні тіні та бордери (`border-slate-200`).

---

## Структура файлів до модифікації
```text
/home/dofi/Dev/Aliparser/
├── src/
│   ├── db/
│   │   └── database.py                # Очищення старих промо-бейджів з image_url при init_db()
│   ├── parser/
│   │   └── aliexpress.py              # Вилучення чистих фото з _dida_config_._init_data_ + фільтрація бейджів
│   ├── services/
│   │   └── exporter.py                # Англомовні заголовки, XML-санітизація, суворий OOXML формат
│   └── web/
│       └── static/
│           ├── index.html             # Світла тема, кастомні кнопки -/+, чиста кнопка View Item, Blob-експорт Excel
│           └── manifest.json          # Оновлення background_color під світлу тему
└── scripts/
    ├── test_api_and_export.py         # Оновлення перевірки англомовних заголовків Excel
    └── test_pwa.py                    # Перевірка світлої теми та відсутності емодзі-стрілки
```

---

## Детальні вимоги до реалізації

### 1. Виправлення парсингу фотографій `src/parser/aliexpress.py` та очищення БД `src/db/database.py`
У методі `scrape_page` (`page.evaluate`) файлу `src/parser/aliexpress.py`:
1. **Вилучення з JSON-стейту сторінки (`window._dida_config_._init_data_`):**
   * Зчитати масив `window._dida_config_?._init_data_?.data?.data?.root?.fields?.mods?.itemList?.content || []`.
   * Побудувати мапу `jsonItemsById` за ключем `String(item.productId || item.redirectedId)` із полями:
     * `img`: `item.image?.imgUrl || (item.images && item.images[0]?.imgUrl) || ""`
     * `title`: `item.title?.displayTitle || ""`
     * `saleText`: `item.prices?.salePrice?.formattedPrice || String(item.prices?.salePrice?.minPrice || "")`
     * `origText`: `item.prices?.originalPrice?.formattedPrice || String(item.prices?.originalPrice?.minPrice || "")`
     * `currency`: `item.prices?.salePrice?.currencyCode || "USD"`
     * `ratingText`: `item.evaluation?.starRating ? String(item.evaluation.starRating) : ""`
     * `tradeText`: `item.trade?.tradeDesc || ""`
     * `storeText`: `item.store?.storeName || ""`
2. **Селектори DOM-карток та фільтрація зображень:**
   * Шукати картки за селектором `.search-card-item, [class*="search-card-item"], [class*="cards--card--"]` (не використовувати `[class*="multi--content--"]` як кореневий елемент картки, бо він не містить блоку фотографії).
   * Написати допоміжну JS-функцію `isBadgeOrIconUrl(url, imgEl)`:
     * Повертає `true` (ігнорувати це зображення), якщо:
       * `url` містить будь-який із підрядків: `154x64`, `110x42`, `48x48`, `60x60`, `702x72`, `116x64`, `S1887a285b60743859ac7bdbfca5e0896Z`, `Sb008eb53e92f463eb0a2c17c539df530h`, `S5efe9a37755e44cfa878e2e714900709h`, `Sca75952228bb4507ac311d1b43e10721q`, `S135d2af8d57840b28092ceba069bdb6c4`.
       * `imgEl.className` або `imgEl.parentElement?.className` містить: `titleIcon`, `scarf`, `starScore`, `cpvIcon`, `badge`, `logo`, `icon`.
   * При виборі фото картки:
     * Спочатку брати `jsonItemsById[itemId]?.img` (якщо не порожнє).
     * Якщо в JSON немає — перебирати всі `card.querySelectorAll('img')`, пропускати ті, де `isBadgeOrIconUrl(src, img)` дорівнює `true`, і брати першу справжню фотографію товару (пріоритет `img[class*="images--item"]`).
   * Якщо після обходу DOM-карток у `jsonItemsById` залишилися товари, яких ще немає у `seen` (наприклад, картки внизу сторінки, які ще не підвантажили DOM), додати їх у список результатів напряму з `jsonItemsById`.
3. **Очищення старих бейджів у базі даних (`src/db/database.py`):**
   * У функції `init_db()` після `Base.metadata.create_all(bind=engine)` виконати безпечне очищення старих некоректних URL у таблиці `products`: для записів, де `image_url` містить `154x64.png`, `Sb008eb53e92f463eb0a2c17c539df530h.png`, `110x42.png`, `48x48.png` або `60x60.png`, встановити `image_url = ""`.

---

### 2. Оновлення генерації Excel `src/services/exporter.py`
* Англомовні заголовки `EXCEL_HEADERS`:
  ```python
  EXCEL_HEADERS = [
      "Item ID",
      "Product Title",
      "Price",
      "Original Price",
      "Currency",
      "Rating",
      "Orders",
      "Store",
      "Category / Query",
      "Product URL",
      "Image URL",
      "Scraped At (UTC)",
  ]
  ```
* Додати функцію `_clean_xml_string(value: Optional[str]) -> str`, яка видаляє заборонені в XML керуючі символи (`re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]", "", str(value))`).
* Використовувати повні 8-символьні ARGB кольори та явні шрифти:
  * `header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")`
  * `header_fill = PatternFill(start_color="FF1E293B", end_color="FF1E293B", fill_type="solid")`
  * `data_font = Font(name="Calibri", size=10, color="FF0F172A")`
  * `link_font = Font(name="Calibri", size=10, color="FF2563EB", underline="single")`
* Після `wb.save(buffer)` нормалізувати ZIP-архів у пам'яті: замінити у `xl/_rels/workbook.xml.rels` абсолютні шляхи `Target="/xl/` на відносні `Target="`.

---

### 3. Світла Тема (Light Theme) та UI-виправлення `src/web/static/index.html`

#### А. Світла кольорова палітра
* Прибрати `class="dark"` з тегу `<html>`.
* Фон `<body>`: `bg-slate-50 text-slate-900 min-h-screen font-sans antialiased selection:bg-indigo-600 selection:text-white`.
* Шапка `<header>`: `sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-slate-200 shadow-xs`.
* Картки (`Scraper Control Center`, `Live Telemetry & Progress`, `Scraped Products Catalog`): `bg-white border border-slate-200 rounded-2xl shadow-sm`.
* Поля вводу та селекти: `bg-slate-50 hover:bg-white focus:bg-white border border-slate-300 focus:border-indigo-600 focus:ring-2 focus:ring-indigo-500/15 text-slate-900 placeholder-slate-400`.
* Чіпси `Quick Presets`: `bg-slate-100 hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 border border-slate-200 hover:border-indigo-200`.
* Картки телеметрії (`Elapsed Time`, `Estimated Remaining`, `Items Collected`, `Collection Speed`): `bg-slate-50 border border-slate-200 rounded-xl p-3`:
  * `Elapsed Time`: `text-slate-900`
  * `Estimated Remaining`: `text-amber-600`
  * `Items Collected`: `text-emerald-600`
  * `Collection Speed`: `text-indigo-600`
* Таблиця товарів:
  * Заголовок `<thead>`: `bg-slate-50 border-b border-slate-200 text-slate-500`.
  * Рядки `<tbody>`: `divide-y divide-slate-200/70`, `hover:bg-slate-50/90`.
  * Назва товару: `font-medium text-slate-900 hover:text-indigo-600`.
  * Ціна: `font-bold text-emerald-600`, стара ціна: `text-slate-400 line-through`.
  * Рейтинг: `text-amber-500 font-semibold`, бейдж замовлень: `bg-slate-100 text-slate-700 border border-slate-200`.
* Модальне вікно `Proxy Manager`: `bg-white text-slate-900 border border-slate-200 shadow-2xl`.
* У `src/web/static/manifest.json`: оновити `"background_color": "#f8fafc"`, `"theme_color": "#4f46e5"`.

#### Б. Заміна системних стрілочок `Max Pages` та `Page Delay` на кастомні кнопки `−` / `+`
* Додати в `<style>` повне вимкнення браузерних спінерів:
  ```css
  input[type="number"]::-webkit-inner-spin-button,
  input[type="number"]::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  input[type="number"] {
    -moz-appearance: textfield;
    appearance: textfield;
  }
  ```
* Для `maxPagesInput` та `delayInput` зробити акуратний комбінований контрол (`flex items-center rounded-xl bg-slate-50 border border-slate-300 focus-within:border-indigo-600 focus-within:bg-white overflow-hidden`):
  * Зліва кнопка `−` (`onclick="stepInput('maxPagesInput', -1)"`), посередині числовий `<input>` (`text-center bg-transparent border-0 focus:ring-0`), справа кнопка `+` (`onclick="stepInput('maxPagesInput', 1)"`).
  * Аналогічно для `delayInput` із кроком `-0.5` та `+0.5`.

#### В. Прибирання емодзі-стрілки у кнопці `View Item`
* У шаблоні рядка таблиці замінити `<span>View Item ↗</span>` на чистий текст `<span>View Item</span>` (без символу `↗` і без емодзі). Стиль кнопки: `inline-flex items-center justify-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white border border-indigo-200 hover:border-indigo-600 transition-colors`.

#### Г. Надійне завантаження Excel через `fetch` + `Blob`
* Оновити JS-функцію `exportExcel()`: виконувати `fetch('/api/products/export?...')`, отримувати `const blob = await res.blob()`, створювати тимчасовий `URL.createObjectURL(blob)` та викликати клік по `<a download="aliexpress_products.xlsx">`.

---

## Критерії приймання та верифікація (Verification)
1. **Перевірка оновленого скрапера фотографій на реальному запиті:**
   ```bash
   venv/bin/python scripts/test_scraper.py --query "usb c hub" --pages 1
   ```
   *Перевірити:* жоден із зібраних товарів не має `154x64.png` або `Sb008eb53e92f463eb0a2c17c539df530h.png` у полі `image_url`.
2. **Перевірка API та Excel-експорту:**
   ```bash
   venv/bin/python scripts/test_api_and_export.py
   ```
3. **Перевірка тестів PWA:**
   ```bash
   venv/bin/python scripts/test_pwa.py
   ```

---

## Обов'язковий фінальний крок (Автоматичний Git Commit & Push)
Після успішного проходження верифікації агент у Чаті 2 **ЗОБОВ'ЯЗАНИЙ самостійно виконати** в терміналі команду фіксації та відправки змін на GitHub:
```bash
git add . && git commit -m "fix: resolve product image badges, fix Excel export format, add custom number steppers, and switch to Light Theme UI" && git push origin main
```

---

## Формат звіту після виконання (у Чат 2)
1. Список модифікованих файлів.
2. Лог перевірки `test_scraper.py`, `test_api_and_export.py` та `test_pwa.py`.
3. Підтвердження виконання `git commit` та `git push origin main` (із хешем коміту).
