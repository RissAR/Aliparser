"""Autonomous test runner for AliExpressScraper."""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.parser.aliexpress import AliProductItem, AliExpressScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_scraper")


def parse_proxy_argument(proxy_str: Optional[str]) -> Optional[Dict[str, str]]:
    """Convert proxy CLI string to Playwright proxy dict format."""
    if not proxy_str:
        return None

    proxy_str = proxy_str.strip()
    if "://" not in proxy_str:
        # Check if ip:port:user:pass
        parts = proxy_str.split(":")
        if len(parts) == 4:
            ip, port, user, password = parts
            return {
                "server": f"http://{ip}:{port}",
                "username": user,
                "password": password,
            }
        proxy_str = f"http://{proxy_str}"

    parsed = urlparse(proxy_str)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"

    config: Dict[str, str] = {"server": server}
    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password

    return config


def print_products_table(items: List[AliProductItem], limit: int = 10) -> None:
    """Print formatted summary table for first N items."""
    header = f"{'[ID]':<18} | {'[Price]':<14} | {'[Rating]':<10} | {'[Orders]':<16} | {'[Title]':<35} | {'[URL]'}"
    separator = "-" * len(header)
    print("\n" + separator)
    print(header)
    print(separator)

    for item in items[:limit]:
        item_id = item.item_id[:16]
        price_str = f"{item.price:.2f} {item.currency}"
        rating_str = f"{item.rating:.1f}" if item.rating is not None else "N/A"
        orders_str = item.orders_count or "N/A"
        if len(orders_str) > 14:
            orders_str = orders_str[:12] + ".."
        title_str = (item.title[:32] + "...") if len(item.title) > 35 else item.title
        url_str = item.product_url

        print(
            f"{item_id:<18} | {price_str:<14} | {rating_str:<10} | {orders_str:<16} | {title_str:<35} | {url_str}"
        )

    print(separator + "\n")


async def main() -> None:
    """Main verification routine."""
    parser = argparse.ArgumentParser(description="Test runner for AliExpress Playwright Scraper")
    parser.add_argument(
        "--query",
        type=str,
        default="wireless mouse",
        help="Search query keyword or direct category URL (default: 'wireless mouse')",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of pages to scrape (default: 1)",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Optional proxy string (e.g. http://ip:port or http://user:pass@ip:port)",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        default=False,
        help="Run browser in headful mode for debugging",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="test_results.json",
        help="File path to save JSON results (default: test_results.json)",
    )

    args = parser.parse_args()
    proxy_config = parse_proxy_argument(args.proxy)

    logger.info("Initializing AliExpressScraper (headless=%s, proxy=%s)...", not args.headful, bool(proxy_config))
    scraper = AliExpressScraper(proxy=proxy_config, headless=not args.headful)

    all_items: List[AliProductItem] = []
    total_start_time = time.time()

    try:
        await scraper.start()

        for page_num in range(1, args.pages + 1):
            logger.info("Starting scrape: target='%s', page=%d", args.query, page_num)
            page_start = time.time()

            items = await scraper.scrape_page(args.query, page_number=page_num)
            page_duration = time.time() - page_start

            logger.info(
                "Completed page %d in %.2fs: found %d valid products",
                page_num,
                page_duration,
                len(items),
            )
            all_items.extend(items)

    finally:
        await scraper.close()

    total_duration = time.time() - total_start_time
    logger.info(
        "Scrape finished. Total items gathered: %d (Total time: %.2fs)",
        len(all_items),
        total_duration,
    )

    if all_items:
        print_products_table(all_items, limit=10)
    else:
        print("\n[WARNING] No products extracted. Check if page layout changed or access was blocked.\n")

    # Save to test_results.json
    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([item.model_dump() for item in all_items], f, indent=2, ensure_ascii=False)

    logger.info("Full test results saved to %s", output_path)


if __name__ == "__main__":
    asyncio.run(main())
