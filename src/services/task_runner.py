"""Background TaskRunner for managing AliExpress scraping tasks, live progress, and ETA metrics."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select

from src.db.database import SessionLocal, init_db, upsert_products
from src.db.models import ParsingTask, Proxy, utc_now
from src.parser.aliexpress import AliExpressScraper
from src.parser.proxy_manager import to_playwright_proxy

logger = logging.getLogger(__name__)


class TaskRunner:
    """Asynchronous background manager for a single active AliExpress scraping task."""

    def __init__(self) -> None:
        self._status: str = "idle"
        self._task_id: Optional[int] = None
        self._target: Optional[str] = None
        self._max_pages: int = 0
        self._current_page: int = 0
        self._completed_pages: int = 0
        self._items_scraped: int = 0
        self._proxy_id: Optional[int] = None
        self._started_at: Optional[datetime] = None
        self._finished_at: Optional[datetime] = None
        self._error_message: Optional[str] = None
        self._delay_seconds: float = 1.5

        self._page_durations: List[float] = []
        self._current_page_start: Optional[float] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._bg_task: Optional[asyncio.Task[None]] = None

    async def start_task(
        self,
        target: str,
        max_pages: int = 1,
        proxy_id: Optional[int] = None,
        delay_seconds: float = 1.5,
        scraper_factory: Optional[Callable[[Optional[Dict[str, str]]], Any]] = None,
    ) -> int:
        """Start a new background scraping task.

        Args:
            target: Search query or category URL.
            max_pages: Maximum number of pages to scrape (>= 1).
            proxy_id: Optional ID of Proxy record in database.
            delay_seconds: Pause between consecutive pages.
            scraper_factory: Optional factory callable returning a scraper instance.

        Returns:
            Created ParsingTask ID.
        """
        if self._status in ("running", "stopping"):
            raise RuntimeError("A parsing task is already running.")

        if not target or not target.strip():
            raise ValueError("Target query or URL cannot be empty.")

        if max_pages < 1:
            raise ValueError("max_pages must be at least 1.")

        cleaned_target = target.strip()
        init_db()

        playwright_proxy: Optional[Dict[str, str]] = None
        now = utc_now()

        with SessionLocal() as db:
            if proxy_id is not None:
                proxy_obj = db.execute(select(Proxy).where(Proxy.id == proxy_id)).scalar_one_or_none()
                if proxy_obj is None:
                    raise ValueError(f"Proxy with id={proxy_id} not found.")
                playwright_proxy = to_playwright_proxy(proxy_obj)

            task_record = ParsingTask(
                target=cleaned_target,
                max_pages=max_pages,
                current_page=0,
                status="running",
                items_scraped=0,
                proxy_id=proxy_id,
                started_at=now,
            )
            db.add(task_record)
            db.commit()
            db.refresh(task_record)
            task_id = task_record.id

        # Initialize runtime state
        self._status = "running"
        self._task_id = task_id
        self._target = cleaned_target
        self._max_pages = max_pages
        self._current_page = 0
        self._completed_pages = 0
        self._items_scraped = 0
        self._proxy_id = proxy_id
        self._started_at = now
        self._finished_at = None
        self._error_message = None
        self._delay_seconds = max(0.0, float(delay_seconds))
        self._page_durations = []
        self._current_page_start = None

        self._stop_event = asyncio.Event()
        self._bg_task = asyncio.create_task(
            self._run_loop(
                task_id=task_id,
                target=cleaned_target,
                max_pages=max_pages,
                playwright_proxy=playwright_proxy,
                delay_seconds=self._delay_seconds,
                scraper_factory=scraper_factory,
            )
        )

        return task_id

    async def _run_loop(
        self,
        task_id: int,
        target: str,
        max_pages: int,
        playwright_proxy: Optional[Dict[str, str]],
        delay_seconds: float,
        scraper_factory: Optional[Callable[[Optional[Dict[str, str]]], Any]],
    ) -> None:
        """Background coroutine executing page-by-page scraping and DB persistence."""
        scraper = (
            scraper_factory(playwright_proxy)
            if scraper_factory is not None
            else AliExpressScraper(proxy=playwright_proxy, headless=True)
        )
        db = SessionLocal()

        try:
            if hasattr(scraper, "start") and callable(scraper.start):
                await scraper.start()

            for page_num in range(1, max_pages + 1):
                if self._stop_event.is_set():
                    break

                self._current_page = page_num
                task_row = db.execute(select(ParsingTask).where(ParsingTask.id == task_id)).scalar_one_or_none()
                if task_row is not None:
                    task_row.current_page = page_num
                    db.commit()

                page_start = time.perf_counter()
                self._current_page_start = page_start

                items = await scraper.scrape_page(target, page_number=page_num)
                page_duration = time.perf_counter() - page_start
                self._current_page_start = None

                # Always save scraped items immediately
                if items:
                    upsert_products(db, items, category_or_query=target, task_id=task_id)

                self._items_scraped += len(items)
                self._completed_pages = page_num
                self._page_durations.append(page_duration)

                task_row = db.execute(select(ParsingTask).where(ParsingTask.id == task_id)).scalar_one_or_none()
                if task_row is not None:
                    task_row.items_scraped = self._items_scraped
                    task_row.current_page = page_num
                    db.commit()

                if page_num < max_pages and not self._stop_event.is_set() and delay_seconds > 0:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=delay_seconds)
                    except asyncio.TimeoutError:
                        pass

            # Determine final status after loop
            finished_time = utc_now()
            self._finished_at = finished_time
            if self._stop_event.is_set():
                self._status = "stopped"
            else:
                self._status = "completed"

            task_row = db.execute(select(ParsingTask).where(ParsingTask.id == task_id)).scalar_one_or_none()
            if task_row is not None:
                task_row.status = self._status
                task_row.items_scraped = self._items_scraped
                task_row.finished_at = finished_time
                db.commit()

        except asyncio.CancelledError:
            finished_time = utc_now()
            self._finished_at = finished_time
            self._status = "stopped"
            try:
                task_row = db.execute(select(ParsingTask).where(ParsingTask.id == task_id)).scalar_one_or_none()
                if task_row is not None:
                    task_row.status = "stopped"
                    task_row.items_scraped = self._items_scraped
                    task_row.finished_at = finished_time
                    db.commit()
            except Exception as db_exc:
                logger.debug("Error updating task on cancel: %s", db_exc)
        except Exception as exc:
            logger.error("Error in TaskRunner loop (task_id=%d): %s", task_id, exc)
            finished_time = utc_now()
            self._finished_at = finished_time
            self._status = "error"
            self._error_message = str(exc)
            try:
                task_row = db.execute(select(ParsingTask).where(ParsingTask.id == task_id)).scalar_one_or_none()
                if task_row is not None:
                    task_row.status = "error"
                    task_row.error_message = str(exc)
                    task_row.items_scraped = self._items_scraped
                    task_row.finished_at = finished_time
                    db.commit()
            except Exception as db_exc:
                logger.debug("Error updating task on error: %s", db_exc)
        finally:
            self._current_page_start = None
            try:
                if hasattr(scraper, "close") and callable(scraper.close):
                    await scraper.close()
            except Exception as close_exc:
                logger.debug("Error closing scraper: %s", close_exc)
            try:
                db.close()
            except Exception as db_close_exc:
                logger.debug("Error closing DB session: %s", db_close_exc)

    async def stop_task(self) -> Dict[str, Any]:
        """Gracefully stop the currently running task without losing already scraped products."""
        if self._status not in ("running", "stopping"):
            return self.get_status()

        self._stop_event.set()
        self._status = "stopping"

        if self._bg_task is not None and not self._bg_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._bg_task), timeout=10.0)
            except asyncio.TimeoutError:
                self._bg_task.cancel()
                try:
                    await self._bg_task
                except (asyncio.CancelledError, Exception):
                    pass

        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Compute current task state, progress percentage, elapsed time, and ETA metrics."""
        is_running = self._status in ("running", "stopping")

        # Calculate elapsed time
        elapsed_raw = 0.0
        if self._started_at is not None:
            start_dt = (
                self._started_at
                if self._started_at.tzinfo is not None
                else self._started_at.replace(tzinfo=timezone.utc)
            )
            if self._finished_at is not None:
                end_dt = (
                    self._finished_at
                    if self._finished_at.tzinfo is not None
                    else self._finished_at.replace(tzinfo=timezone.utc)
                )
            else:
                end_dt = utc_now()
            elapsed_raw = max(0.0, (end_dt - start_dt).total_seconds())

        elapsed_seconds = round(elapsed_raw, 1)

        # Calculate progress percentage
        if self._status == "completed":
            progress_percent = 100.0
        elif self._max_pages > 0:
            progress_percent = round(min(100.0, (self._completed_pages / self._max_pages) * 100.0), 1)
        else:
            progress_percent = 0.0

        # Calculate ETA (estimated_remaining_seconds)
        estimated_remaining_seconds: Optional[float]
        if self._status == "idle":
            estimated_remaining_seconds = None
        elif not is_running:
            estimated_remaining_seconds = 0.0
        else:
            remaining_pages = max(0, self._max_pages - self._completed_pages)
            if remaining_pages == 0:
                estimated_remaining_seconds = 0.0
            elif len(self._page_durations) > 0:
                avg_scrape_time = sum(self._page_durations) / len(self._page_durations)
                avg_cycle_time = avg_scrape_time + self._delay_seconds
                spent_on_current = (
                    max(0.0, time.perf_counter() - self._current_page_start)
                    if self._current_page_start is not None
                    else 0.0
                )
                raw_eta = (avg_cycle_time * remaining_pages) - spent_on_current
                estimated_remaining_seconds = round(max(0.5, raw_eta), 1)
            else:
                raw_eta = (8.0 * self._max_pages) - elapsed_raw
                estimated_remaining_seconds = round(max(1.0, raw_eta), 1)

        items_per_second = round(self._items_scraped / elapsed_raw, 2) if elapsed_raw > 0 else 0.0

        return {
            "is_running": is_running,
            "status": self._status,
            "task_id": self._task_id,
            "target": self._target,
            "current_page": self._current_page,
            "max_pages": self._max_pages,
            "completed_pages": self._completed_pages,
            "progress_percent": progress_percent,
            "items_scraped": self._items_scraped,
            "proxy_id": self._proxy_id,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "finished_at": self._finished_at.isoformat() if self._finished_at else None,
            "elapsed_seconds": elapsed_seconds,
            "estimated_remaining_seconds": estimated_remaining_seconds,
            "items_per_second": items_per_second,
            "error_message": self._error_message,
        }


# Global singleton instance
task_runner = TaskRunner()
