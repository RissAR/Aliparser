"""Database connection, session management, and product upsert operations."""

import os
from datetime import datetime, timezone
from typing import Generator, List, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base, Product
from src.parser.aliexpress import AliProductItem

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

SQLALCHEMY_DATABASE_URL = "sqlite:///data/aliparser.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create database directory and initialize all SQLAlchemy tables."""
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)


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
