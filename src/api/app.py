"""FastAPI REST application for AliExpress Scraper, Product catalog, Excel export, and Proxy management."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from src.api.schemas import (
    ParsingTaskResponse,
    ProductListResponse,
    ProxyCreateRequest,
    ProxyResponse,
    StartParserRequest,
    TaskStatusResponse,
)
from src.db.database import get_db, init_db
from src.db.models import ParsingTask, Product, Proxy, utc_now
from src.parser.proxy_manager import check_proxy_connectivity, parse_proxy_string
from src.services.exporter import generate_products_excel
from src.services.task_runner import task_runner

# Initialize database tables on module load
init_db()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Ensure DB tables exist on startup and stop running task on shutdown."""
    init_db()
    yield
    if task_runner.get_status()["is_running"]:
        await task_runner.stop_task()


app = FastAPI(
    title="AliParser API",
    description="REST API for AliExpress product scraping, proxy management, and Excel export",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# A. Parser Control Endpoints
# =============================================================================


@app.post("/api/parser/start", response_model=TaskStatusResponse)
async def start_parser(req: StartParserRequest) -> Dict[str, Any]:
    """Start a new background scraping task."""
    try:
        await task_runner.start_task(
            target=req.target,
            max_pages=req.max_pages,
            proxy_id=req.proxy_id,
            delay_seconds=req.delay_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return task_runner.get_status()


@app.get("/api/parser/status", response_model=TaskStatusResponse)
async def get_parser_status() -> Dict[str, Any]:
    """Return current live status, progress, and ETA metrics of the parser."""
    return task_runner.get_status()


@app.post("/api/parser/stop", response_model=TaskStatusResponse)
async def stop_parser() -> Dict[str, Any]:
    """Gracefully stop the currently running scraping task."""
    return await task_runner.stop_task()


@app.get("/api/parser/tasks", response_model=List[ParsingTaskResponse])
def list_parsing_tasks(db: Session = Depends(get_db)) -> List[ParsingTask]:
    """Return the last 20 parsing task history records."""
    stmt = select(ParsingTask).order_by(ParsingTask.id.desc()).limit(20)
    return list(db.execute(stmt).scalars().all())


# =============================================================================
# B. Products & Excel Export Endpoints
# =============================================================================


def _apply_product_filters(
    stmt: Any,
    search: Optional[str] = None,
    task_id: Optional[int] = None,
) -> Any:
    """Apply optional search substring and task_id filters to a Product select statement."""
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Product.title.ilike(pattern),
                Product.store_name.ilike(pattern),
                Product.category_or_query.ilike(pattern),
            )
        )
    if task_id is not None:
        stmt = stmt.where(Product.task_id == task_id)
    return stmt


@app.get("/api/products", response_model=ProductListResponse)
def list_products(
    search: Optional[str] = None,
    task_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Query scraped products with optional search filter and pagination."""
    count_stmt = _apply_product_filters(select(func.count()).select_from(Product), search=search, task_id=task_id)
    total = db.execute(count_stmt).scalar_one()

    items_stmt = _apply_product_filters(select(Product), search=search, task_id=task_id)
    items_stmt = items_stmt.order_by(Product.scraped_at.desc(), Product.id.desc()).limit(limit).offset(offset)
    items = list(db.execute(items_stmt).scalars().all())

    return {"total": total, "items": items}


@app.get("/api/products/export")
def export_products_excel(
    search: Optional[str] = None,
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export filtered or all products to a formatted .xlsx workbook with clickable links."""
    stmt = _apply_product_filters(select(Product), search=search, task_id=task_id)
    stmt = stmt.order_by(Product.scraped_at.desc(), Product.id.desc())
    products = list(db.execute(stmt).scalars().all())

    excel_bytes = generate_products_excel(products)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="aliexpress_products.xlsx"'},
    )


@app.delete("/api/products")
def delete_products(
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> Dict[str, int]:
    """Delete products from database (optionally filtered by task_id)."""
    stmt = delete(Product)
    if task_id is not None:
        stmt = stmt.where(Product.task_id == task_id)
    result = db.execute(stmt)
    db.commit()
    return {"deleted": int(result.rowcount or 0)}


# =============================================================================
# C. Proxy Management Endpoints
# =============================================================================


@app.get("/api/proxies", response_model=List[ProxyResponse])
def list_proxies(db: Session = Depends(get_db)) -> List[Proxy]:
    """Return all configured proxies ordered by newest first."""
    stmt = select(Proxy).order_by(Proxy.id.desc())
    return list(db.execute(stmt).scalars().all())


@app.post("/api/proxies", response_model=ProxyResponse)
async def create_or_update_proxy(
    req: ProxyCreateRequest,
    db: Session = Depends(get_db),
) -> Proxy:
    """Parse, store (or update), and optionally check connectivity of a proxy server."""
    try:
        parsed = parse_proxy_string(req.raw_proxy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.execute(select(Proxy).where(Proxy.raw_proxy == parsed["raw_proxy"])).scalar_one_or_none()
    if existing is not None:
        existing.protocol = parsed["protocol"]
        existing.host = parsed["host"]
        existing.port = parsed["port"]
        existing.username = parsed["username"]
        existing.password = parsed["password"]
        existing.is_active = True
        proxy_obj = existing
    else:
        proxy_obj = Proxy(**parsed)
        db.add(proxy_obj)

    if req.check_connectivity:
        is_working, latency_ms, _ = await check_proxy_connectivity(parsed)
        proxy_obj.is_working = is_working
        proxy_obj.latency_ms = latency_ms
        proxy_obj.last_checked_at = utc_now()

    db.commit()
    db.refresh(proxy_obj)
    return proxy_obj


@app.post("/api/proxies/{proxy_id}/check", response_model=ProxyResponse)
async def check_proxy_by_id(
    proxy_id: int,
    db: Session = Depends(get_db),
) -> Proxy:
    """Test connectivity and measure latency for a specific stored proxy."""
    proxy_obj = db.execute(select(Proxy).where(Proxy.id == proxy_id)).scalar_one_or_none()
    if proxy_obj is None:
        raise HTTPException(status_code=404, detail=f"Proxy with id={proxy_id} not found.")

    is_working, latency_ms, _ = await check_proxy_connectivity(proxy_obj)
    proxy_obj.is_working = is_working
    proxy_obj.latency_ms = latency_ms
    proxy_obj.last_checked_at = utc_now()

    db.commit()
    db.refresh(proxy_obj)
    return proxy_obj


@app.delete("/api/proxies/{proxy_id}")
def delete_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a proxy server by ID."""
    proxy_obj = db.execute(select(Proxy).where(Proxy.id == proxy_id)).scalar_one_or_none()
    if proxy_obj is None:
        raise HTTPException(status_code=404, detail=f"Proxy with id={proxy_id} not found.")

    db.delete(proxy_obj)
    db.commit()
    return {"deleted": True, "id": proxy_id}


# =============================================================================
# D. Static Files & PWA Frontend Routes
# =============================================================================

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_pwa_index() -> FileResponse:
    """Serve the main English PWA dashboard HTML."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/manifest.json", include_in_schema=False)
def serve_pwa_manifest() -> FileResponse:
    """Serve the PWA Web App Manifest."""
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def serve_pwa_service_worker() -> FileResponse:
    """Serve the PWA Service Worker script."""
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/icon.svg", include_in_schema=False)
def serve_pwa_icon() -> FileResponse:
    """Serve the vector SVG app icon."""
    return FileResponse(STATIC_DIR / "icon.svg", media_type="image/svg+xml")

