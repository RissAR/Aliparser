"""Database connection, session management, and product upsert operations."""

import os
from datetime import datetime, timezone
from typing import Any, Generator, List, Optional

from sqlalchemy import create_engine, event, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base, ParsingTask, Product, utc_now
from src.parser.aliexpress import AliProductItem

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

SQLALCHEMY_DATABASE_URL = "sqlite:///data/aliparser.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
    """Configure SQLite WAL journal mode and busy timeout for concurrent access."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

BADGE_IMAGE_SUBSTRINGS = (
    "154x64.png",
    "Sb008eb53e92f463eb0a2c17c539df530h.png",
    "S1887a285b60743859ac7bdbfca5e0896Z",
    "S5efe9a37755e44cfa878e2e714900709h",
    "110x42.png",
    "48x48.png",
    "60x60.png",
    "702x72.png",
    "116x64.png",
)


def init_db() -> None:
    """Create database directory, initialize all SQLAlchemy tables, clean legacy badge URLs, and recover stale tasks."""
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        conditions = [Product.image_url.like(f"%{pat}%") for pat in BADGE_IMAGE_SUBSTRINGS]
        stmt = update(Product).where(or_(*conditions)).values(image_url="")
        db.execute(stmt)

        stale_tasks_stmt = (
            update(ParsingTask)
            .where(ParsingTask.status.in_(["running", "stopping"]))
            .values(status="stopped", finished_at=utc_now())
        )
        db.execute(stale_tasks_stmt)
        db.commit()


def get_db() -> Generator[Session, None, None]:
    """Dependency generator yielding a SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def upsert_products(
    db: Session,
    items: List[AliProductItem],
    category_or_query: Optional[str] = None,
    task_id: Optional[int] = None,
) -> int:
    """Insert new products or update existing ones by unique item_id.

    Args:
        db: Active SQLAlchemy Session.
        items: List of scraped AliProductItem objects.
        category_or_query: Query or category URL that produced these items.
        task_id: Associated ParsingTask ID, if any.

    Returns:
        Number of processed product items.
    """
    if not items:
        return 0

    now = datetime.now(timezone.utc)
    processed_count = 0

    for item in items:
        stmt = select(Product).where(Product.item_id == item.item_id)
        existing = db.execute(stmt).scalar_one_or_none()

        if existing is not None:
            existing.title = item.title
            existing.price = item.price
            existing.original_price = item.original_price
            existing.currency = item.currency
            existing.rating = item.rating
            existing.orders_count = item.orders_count
            existing.store_name = item.store_name
            existing.product_url = item.product_url
            existing.image_url = item.image_url
            if category_or_query is not None:
                existing.category_or_query = category_or_query
            if task_id is not None:
                existing.task_id = task_id
            existing.scraped_at = now
        else:
            new_product = Product(
                item_id=item.item_id,
                title=item.title,
                price=item.price,
                original_price=item.original_price,
                currency=item.currency,
                rating=item.rating,
                orders_count=item.orders_count,
                store_name=item.store_name,
                product_url=item.product_url,
                image_url=item.image_url,
                category_or_query=category_or_query,
                task_id=task_id,
                scraped_at=now,
            )
            db.add(new_product)

        processed_count += 1

    db.commit()
    return processed_count
