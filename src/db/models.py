"""SQLAlchemy 2.0 database models for AliParser."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""
    pass


class Proxy(Base):
    """Proxy server configuration and health status."""

    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_proxy: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    protocol: Mapped[str] = mapped_column(String, default="http", nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_working: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ParsingTask(Base):
    """History and state of scraping tasks."""

    __tablename__ = "parsing_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String, nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_page: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="idle", nullable=False)
    items_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proxy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("proxies.id"), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Product(Base):
    """Scraped AliExpress product item."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD", nullable=False)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    orders_count: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    store_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category_or_query: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("parsing_tasks.id"), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
