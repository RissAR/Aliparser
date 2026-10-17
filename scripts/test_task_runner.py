"""Comprehensive verification test for TaskRunner lifecycle, ETA metrics, and Graceful Stop."""

import asyncio
import logging
import os
import sys
from typing import Dict, List, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import delete, func, select

from src.db.database import SessionLocal, init_db
from src.db.models import ParsingTask, Product
from src.parser.aliexpress import AliProductItem
from src.services.task_runner import task_runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_task_runner")


class FakeSuccessScraper:
    """Controlled fake scraper simulating 0.3s per page and returning 5 products per page."""

    def __init__(self, proxy: Optional[Dict[str, str]] = None, prefix: str = "TR_ITEM"):
        self.proxy = proxy
        self.prefix = prefix
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def scrape_page(self, target: str, page_number: int = 1) -> List[AliProductItem]:
        await asyncio.sleep(0.3)
        items: List[AliProductItem] = []
        for idx in range(1, 6):
            item_id = f"{self.prefix}_P{page_num_id(page_number, idx)}"
            items.append(
                AliProductItem(
                    item_id=item_id,
                    title=f"{target.title()} Product p{page_number}-#{idx}",
                    price=round(10.0 + page_number + idx * 0.5, 2),
                    original_price=25.0,
                    currency="USD",
                    rating=4.8,
                    orders_count="200+ sold",
                    store_name="Test Store",
                    product_url=f"https://www.aliexpress.com/item/{item_id}.html",
                    image_url=f"https://ae01.alicdn.com/kf/{item_id}.jpg",
                )
            )
        return items


class FakeFailingScraper:
    """Controlled fake scraper that raises a RuntimeError to test error state handling."""

    def __init__(self, proxy: Optional[Dict[str, str]] = None):
        self.proxy = proxy

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def scrape_page(self, target: str, page_number: int = 1) -> List[AliProductItem]:
        await asyncio.sleep(0.1)
        raise RuntimeError("Simulated network failure")


def page_num_id(page: int, idx: int) -> str:
    return f"{page}_{idx}"


async def run_all_tests() -> None:
    """Run all 3 TaskRunner verification scenarios."""
    init_db()

    # Clean up any leftover test products/tasks
    with SessionLocal() as db:
        db.execute(delete(Product).where(Product.item_id.like("SC1_%") | Product.item_id.like("SC2_%")))
        db.execute(delete(ParsingTask).where(ParsingTask.target.in_(["usb hub", "mechanical keyboard", "broken query"])))
        db.commit()

    # =========================================================================
    # Scenario 1: Full execution and live metrics / ETA calculation
    # =========================================================================
    logger.info("Scenario 1: Testing full execution, live progress, and ETA calculation...")
    task1_id = await task_runner.start_task(
        target="usb hub",
        max_pages=3,
        delay_seconds=0.2,
        scraper_factory=lambda proxy: FakeSuccessScraper(proxy=proxy, prefix="SC1"),
    )
    assert task1_id > 0

    # Verify concurrent execution guard raises RuntimeError
    try:
        await task_runner.start_task(target="concurrent test", max_pages=1)
        raise AssertionError("Expected RuntimeError when starting a second concurrent task!")
    except RuntimeError as exc:
        logger.info("  [OK] Concurrent start guard worked: %s", exc)

    # Check status mid-flight (after page 1 finishes ~0.35s)
    await asyncio.sleep(0.42)
    mid_status = task_runner.get_status()
    logger.info(
        "  [MID-RUN] status=%s, page=%d/%d (completed=%d), progress=%.1f%%, elapsed=%.1fs, ETA=%ss, speed=%.2f items/s",
        mid_status["status"],
        mid_status["current_page"],
        mid_status["max_pages"],
        mid_status["completed_pages"],
        mid_status["progress_percent"],
        mid_status["elapsed_seconds"],
        mid_status["estimated_remaining_seconds"],
        mid_status["items_per_second"],
    )
    assert mid_status["is_running"] is True
    assert mid_status["elapsed_seconds"] > 0
    assert mid_status["estimated_remaining_seconds"] is not None and mid_status["estimated_remaining_seconds"] > 0
    assert mid_status["progress_percent"] > 0.0

    # Wait for full completion
    while task_runner.get_status()["is_running"]:
        await asyncio.sleep(0.1)

    final_s1 = task_runner.get_status()
    logger.info(
        "  [COMPLETED] status=%s, items=%d, progress=%.1f%%, elapsed=%.1fs, ETA=%s",
        final_s1["status"],
        final_s1["items_scraped"],
        final_s1["progress_percent"],
        final_s1["elapsed_seconds"],
        final_s1["estimated_remaining_seconds"],
    )
    assert final_s1["status"] == "completed", f"Expected completed, got {final_s1['status']}"
    assert final_s1["items_scraped"] == 15, f"Expected 15 items, got {final_s1['items_scraped']}"
    assert final_s1["progress_percent"] == 100.0
    assert final_s1["finished_at"] is not None

    with SessionLocal() as db:
        db_task1 = db.execute(select(ParsingTask).where(ParsingTask.id == task1_id)).scalar_one()
        assert db_task1.status == "completed"
        assert db_task1.items_scraped == 15
        assert db_task1.finished_at is not None

        db_prod_count1 = db.execute(
            select(func.count()).select_from(Product).where(Product.task_id == task1_id)
        ).scalar_one()
        assert db_prod_count1 == 15, f"Expected 15 products in DB for task 1, found {db_prod_count1}"
        logger.info("  [OK] Scenario 1 verified in SQLite: ParsingTask='completed', Products=%d", db_prod_count1)

    # =========================================================================
    # Scenario 2: Graceful Stop mid-run
    # =========================================================================
    logger.info("Scenario 2: Testing Graceful Stop mid-execution...")
    task2_id = await task_runner.start_task(
        target="mechanical keyboard",
        max_pages=5,
        delay_seconds=0.25,
        scraper_factory=lambda proxy: FakeSuccessScraper(proxy=proxy, prefix="SC2"),
    )

    # Wait until 1 or 2 pages have completed (~0.45s)
    await asyncio.sleep(0.45)
    stopped_status = await task_runner.stop_task()
    logger.info(
        "  [STOPPED] status=%s, completed_pages=%d/%d, items_scraped=%d, finished_at=%s",
        stopped_status["status"],
        stopped_status["completed_pages"],
        stopped_status["max_pages"],
        stopped_status["items_scraped"],
        stopped_status["finished_at"],
    )
    assert stopped_status["status"] == "stopped", f"Expected 'stopped', got {stopped_status['status']}"
    assert stopped_status["is_running"] is False
    assert stopped_status["finished_at"] is not None
    assert 5 <= stopped_status["items_scraped"] < 25

    with SessionLocal() as db:
        db_task2 = db.execute(select(ParsingTask).where(ParsingTask.id == task2_id)).scalar_one()
        assert db_task2.status == "stopped"
        assert db_task2.finished_at is not None

        db_prod_count2 = db.execute(
            select(func.count()).select_from(Product).where(Product.task_id == task2_id)
        ).scalar_one()
        assert db_prod_count2 == stopped_status["items_scraped"]
        logger.info(
            "  [OK] Scenario 2 verified: Graceful stop preserved %d already-scraped products in DB.",
            db_prod_count2,
        )

    # =========================================================================
    # Scenario 3: Scraper exception handling
    # =========================================================================
    logger.info("Scenario 3: Testing error handling on scraper exception...")
    task3_id = await task_runner.start_task(
        target="broken query",
        max_pages=2,
        delay_seconds=0.1,
        scraper_factory=lambda proxy: FakeFailingScraper(proxy=proxy),
    )

    while task_runner.get_status()["is_running"]:
        await asyncio.sleep(0.05)

    err_status = task_runner.get_status()
    logger.info(
        "  [ERROR STATE] status=%s, error_message='%s'",
        err_status["status"],
        err_status["error_message"],
    )
    assert err_status["status"] == "error", f"Expected 'error', got {err_status['status']}"
    assert err_status["error_message"] is not None and "Simulated network failure" in err_status["error_message"]

    with SessionLocal() as db:
        db_task3 = db.execute(select(ParsingTask).where(ParsingTask.id == task3_id)).scalar_one()
        assert db_task3.status == "error"
        assert db_task3.error_message is not None and "Simulated network failure" in db_task3.error_message
        logger.info("  [OK] Scenario 3 verified: error state and message persisted in DB.")

        # Clean up temporary test artifacts
        db.execute(delete(Product).where(Product.task_id.in_([task1_id, task2_id, task3_id])))
        db.execute(delete(ParsingTask).where(ParsingTask.id.in_([task1_id, task2_id, task3_id])))
        db.commit()
        logger.info("  [OK] Cleaned up temporary test tasks and products.")

    print("\nALL TASK RUNNER TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
