"""Verification script for SQLite database models, upsert logic, and proxy manager."""

import asyncio
import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import delete, func, select

from src.db.database import SessionLocal, init_db, upsert_products
from src.db.models import ParsingTask, Product, Proxy
from src.parser.aliexpress import AliProductItem
from src.parser.proxy_manager import (
    check_proxy_connectivity,
    parse_proxy_string,
    to_httpx_proxy_url,
    to_playwright_proxy,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_db_and_proxy")


async def run_tests() -> None:
    """Execute sequential tests for DB initialization, proxy parsing, ORM persistence, and product upsert."""
    # 1. Initialize database
    logger.info("Step 1: Initializing SQLite database...")
    init_db()
    assert os.path.exists("data/aliparser.db"), "Database file data/aliparser.db was not created!"
    logger.info("Database initialized successfully at data/aliparser.db")

    # 2. Test parsing all 4 proxy formats & conversion to Playwright format
    logger.info("Step 2: Testing proxy string parser and Playwright conversion...")
    test_proxies = [
        (
            "1.2.3.4:8080",
            {"protocol": "http", "host": "1.2.3.4", "port": 8080, "username": None, "password": None},
            {"server": "http://1.2.3.4:8080"},
        ),
        (
            "1.2.3.4:8080:user1:pass1",
            {"protocol": "http", "host": "1.2.3.4", "port": 8080, "username": "user1", "password": "pass1"},
            {"server": "http://1.2.3.4:8080", "username": "user1", "password": "pass1"},
        ),
        (
            "socks5://5.6.7.8:1080",
            {"protocol": "socks5", "host": "5.6.7.8", "port": 1080, "username": None, "password": None},
            {"server": "socks5://5.6.7.8:1080"},
        ),
        (
            "http://admin:secret@9.10.11.12:3128",
            {"protocol": "http", "host": "9.10.11.12", "port": 3128, "username": "admin", "password": "secret"},
            {"server": "http://9.10.11.12:3128", "username": "admin", "password": "secret"},
        ),
    ]

    parsed_dicts = []
    for raw_str, expected_fields, expected_pw in test_proxies:
        parsed = parse_proxy_string(raw_str)
        for key, val in expected_fields.items():
            assert parsed[key] == val, f"Mismatch for {raw_str} key {key}: {parsed[key]} != {val}"
        pw_proxy = to_playwright_proxy(parsed)
        assert pw_proxy == expected_pw, f"Playwright proxy mismatch for {raw_str}: {pw_proxy} != {expected_pw}"
        httpx_url = to_httpx_proxy_url(parsed)
        assert httpx_url.startswith(expected_fields["protocol"] + "://")
        parsed_dicts.append(parsed)
        logger.info("  [OK] Parsed '%s' -> Playwright: %s", raw_str, pw_proxy)

    # Verify invalid proxy raises ValueError
    try:
        parse_proxy_string("invalid_proxy_format")
        raise AssertionError("Expected ValueError for invalid proxy string")
    except ValueError as exc:
        logger.info("  [OK] Invalid proxy properly rejected: %s", exc)

    # Verify async connectivity check function signature and graceful error handling on unreachable local port
    is_working, latency_ms, err = await check_proxy_connectivity(
        parse_proxy_string("127.0.0.1:59999"), timeout=1.5
    )
    assert is_working is False and latency_ms is None and err is not None
    logger.info("  [OK] Connectivity check handled unreachable proxy gracefully (is_working=%s)", is_working)

    # 3. Test saving Proxy and ParsingTask to DB
    logger.info("Step 3: Testing Proxy and ParsingTask persistence...")
    with SessionLocal() as db:
        # Clean previous test artifacts if re-running
        db.execute(delete(Product).where(Product.item_id.in_(["TEST_ITEM_1001", "TEST_ITEM_1002"])))
        db.execute(delete(ParsingTask).where(ParsingTask.target == "test wireless headphones"))
        db.execute(
            delete(Proxy).where(Proxy.raw_proxy.in_([p["raw_proxy"] for p in parsed_dicts]))
        )
        db.commit()

        saved_proxies = []
        for p_dict in parsed_dicts:
            proxy_obj = Proxy(**p_dict)
            db.add(proxy_obj)
            saved_proxies.append(proxy_obj)
        db.commit()

        for proxy_obj in saved_proxies:
            db.refresh(proxy_obj)
            assert proxy_obj.id is not None

        # Verify to_playwright_proxy works with Proxy ORM model as well
        orm_pw = to_playwright_proxy(saved_proxies[1])
        assert orm_pw == {"server": "http://1.2.3.4:8080", "username": "user1", "password": "pass1"}
        logger.info("  [OK] Saved %d proxies to DB (first ID=%d)", len(saved_proxies), saved_proxies[0].id)

        task = ParsingTask(
            target="test wireless headphones",
            max_pages=2,
            current_page=1,
            status="running",
            proxy_id=saved_proxies[0].id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        assert task.id is not None
        assert task.status == "running"
        logger.info("  [OK] Created ParsingTask ID=%d (target='%s', proxy_id=%d)", task.id, task.target, task.proxy_id)

        # 4. Test upsert_products (insert + update without duplicates)
        logger.info("Step 4: Testing upsert_products (insert and deduplicated update)...")
        initial_items = [
            AliProductItem(
                item_id="TEST_ITEM_1001",
                title="TWS Wireless Earbuds Bluetooth 5.3",
                price=15.99,
                original_price=29.99,
                currency="USD",
                rating=4.8,
                orders_count="1,000+ sold",
                store_name="Audio Official Store",
                product_url="https://www.aliexpress.com/item/TEST_ITEM_1001.html",
                image_url="https://ae01.alicdn.com/kf/test1001.jpg",
            ),
            AliProductItem(
                item_id="TEST_ITEM_1002",
                title="Active Noise Cancelling Headphones Over-Ear",
                price=45.50,
                original_price=79.00,
                currency="USD",
                rating=4.9,
                orders_count="500+ sold",
                store_name="SoundPro Store",
                product_url="https://www.aliexpress.com/item/TEST_ITEM_1002.html",
                image_url="https://ae01.alicdn.com/kf/test1002.jpg",
            ),
        ]

        count_inserted = upsert_products(
            db,
            initial_items,
            category_or_query=task.target,
            task_id=task.id,
        )
        assert count_inserted == 2, f"Expected 2 processed items, got {count_inserted}"

        total_in_db = db.execute(
            select(func.count()).select_from(Product).where(Product.item_id.in_(["TEST_ITEM_1001", "TEST_ITEM_1002"]))
        ).scalar_one()
        assert total_in_db == 2, f"Expected 2 records in DB after initial insert, found {total_in_db}"
        logger.info("  [OK] Inserted 2 initial products (DB count for test items = %d)", total_in_db)

        # Upsert again with updated price for TEST_ITEM_1001
        updated_items = [
            AliProductItem(
                item_id="TEST_ITEM_1001",
                title="TWS Wireless Earbuds Bluetooth 5.3 (Updated Promo)",
                price=12.49,
                original_price=29.99,
                currency="USD",
                rating=4.9,
                orders_count="1,500+ sold",
                store_name="Audio Official Store",
                product_url="https://www.aliexpress.com/item/TEST_ITEM_1001.html",
                image_url="https://ae01.alicdn.com/kf/test1001.jpg",
            )
        ]

        count_updated = upsert_products(
            db,
            updated_items,
            category_or_query=task.target,
            task_id=task.id,
        )
        assert count_updated == 1

        total_after_upsert = db.execute(
            select(func.count()).select_from(Product).where(Product.item_id.in_(["TEST_ITEM_1001", "TEST_ITEM_1002"]))
        ).scalar_one()
        assert total_after_upsert == 2, f"Duplicate created! Expected 2 records, found {total_after_upsert}"

        item_1001 = db.execute(
            select(Product).where(Product.item_id == "TEST_ITEM_1001")
        ).scalar_one()
        assert item_1001.price == 12.49, f"Price did not update: expected 12.49, got {item_1001.price}"
        assert item_1001.orders_count == "1,500+ sold"
        assert item_1001.title == "TWS Wireless Earbuds Bluetooth 5.3 (Updated Promo)"
        logger.info(
            "  [OK] Upsert verified: count remained %d, item TEST_ITEM_1001 price updated 15.99 -> %.2f",
            total_after_upsert,
            item_1001.price,
        )

        # Clean up test records so production DB stays clean
        db.execute(delete(Product).where(Product.item_id.in_(["TEST_ITEM_1001", "TEST_ITEM_1002"])))
        db.execute(delete(ParsingTask).where(ParsingTask.id == task.id))
        db.execute(delete(Proxy).where(Proxy.id.in_([p.id for p in saved_proxies])))
        db.commit()
        logger.info("  [OK] Cleaned up temporary test records from DB.")

    print("\nALL DB & PROXY TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(run_tests())
