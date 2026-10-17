"""Pydantic v2 request and response schemas for the AliParser REST API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StartParserRequest(BaseModel):
    """Request payload for starting a new parsing task."""

    target: str = Field(description="Search query keyword or category URL")
    max_pages: int = Field(default=1, ge=1, le=50, description="Number of pages to scrape")
    proxy_id: Optional[int] = Field(default=None, description="Optional database Proxy ID")
    delay_seconds: float = Field(default=1.5, ge=0.0, le=30.0, description="Delay between pages in seconds")


class TaskStatusResponse(BaseModel):
    """Live status and timing metrics of the background TaskRunner."""

    is_running: bool
    status: str
    task_id: Optional[int] = None
    target: Optional[str] = None
    current_page: int
    max_pages: int
    completed_pages: int
    progress_percent: float
    items_scraped: int
    proxy_id: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: float
    estimated_remaining_seconds: Optional[float] = None
    items_per_second: float
    error_message: Optional[str] = None


class ParsingTaskResponse(BaseModel):
    """Historical ParsingTask record representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target: str
    max_pages: int
    current_page: int
    status: str
    items_scraped: int
    proxy_id: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class ProductResponse(BaseModel):
    """Scraped product record representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: str
    title: str
    price: float
    original_price: Optional[float] = None
    currency: str
    rating: Optional[float] = None
    orders_count: Optional[str] = None
    store_name: Optional[str] = None
    product_url: str
    image_url: Optional[str] = None
    category_or_query: Optional[str] = None
    task_id: Optional[int] = None
    scraped_at: datetime


class ProductListResponse(BaseModel):
    """Paginated product list response."""

    total: int
    items: List[ProductResponse]


class ProxyCreateRequest(BaseModel):
    """Request payload for adding or updating a proxy server."""

    raw_proxy: str = Field(description="Proxy string in host:port, host:port:user:pass, or protocol://... format")
    check_connectivity: bool = Field(default=False, description="Whether to immediately test proxy connectivity")


class ProxyResponse(BaseModel):
    """Proxy record representation (excluding password for security)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_proxy: str
    protocol: str
    host: str
    port: int
    username: Optional[str] = None
    is_active: bool
    is_working: Optional[bool] = None
    latency_ms: Optional[int] = None
    last_checked_at: Optional[datetime] = None
    created_at: datetime
