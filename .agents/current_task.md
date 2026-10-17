# ТЗ №1: Архітектура та базовий бекенд AliExpress парсера з API

## Мета
Створити фундамент для парсера AliExpress:
1. Базова структура проекту (FastAPI, SQLite/SQLAlchemy, Playwright).
2. Моделі бази даних (товари, завдання парсингу, проксі).
3. Парсерний модуль для AliExpress (універсальний збір за категорією/пошуковим запитом із підтримкою проксі).
4. REST API ендпоінти для керування задачами парсингу, отримання списку товарів, додавання проксі та експорту в Excel.

---

## Очікувана структура файлів
```text
/home/dofi/Dev/Aliparser/
├── .agents/
│   ├── current_task.md
│   └── skills/
│       └── execute-task/
│           └── SKILL.md
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py                # FastAPI додаток та маршрути
│   │   └── schemas.py            # Pydantic моделі (запити/відповіді)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py           # Підключення до SQLite (async/sync)
│   │   └── models.py             # SQLAlchemy моделі (Product, Task, Proxy)
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── aliexpress.py         # Ядро парсингу AliExpress (Playwright stealth + API interception)
│   │   └── proxy_manager.py      # Управління та валідація проксі
│   └── services/
│       ├── __init__.py
│       ├── exporter.py           # Експорт товарів в Excel (.xlsx з форматуванням та лінками)
│       └── task_runner.py        # Фоновий менеджер виконання задач з таймером та статусами
├── requirements.txt
├── run_app.py                    # Точка входу для запуску бекенду
└── .gitignore
```
