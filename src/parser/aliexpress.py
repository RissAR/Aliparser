"""AliExpress Playwright Scraper Core."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AliProductItem(BaseModel):
    """AliExpress product item model."""

    item_id: str = Field(description="Unique numeric product ID on AliExpress")
    title: str = Field(description="Product title")
    price: float = Field(description="Current sale price")
    original_price: Optional[float] = Field(default=None, description="Original price before discount")
    currency: str = Field(description="Currency code (e.g. USD, UAH, EUR)")
    rating: Optional[float] = Field(default=None, description="Average product rating")
    orders_count: Optional[str] = Field(default=None, description="Orders or sold count (e.g. '500+ sold')")
    store_name: Optional[str] = Field(default=None, description="Store or seller name")
    product_url: str = Field(description="Clean direct product URL without tracking parameters")
    image_url: str = Field(description="Main product image URL")


def parse_price_and_currency(text: Optional[str], default_currency: str = "USD") -> tuple[Optional[float], str]:
    """Parse numeric price and currency code from raw text string."""
    if not text:
        return None, default_currency

    curr = default_currency
    clean = text.strip()

    if "грн" in clean or "UAH" in clean:
        curr = "UAH"
    elif "$" in clean or "USD" in clean:
        curr = "USD"
    elif "€" in clean or "EUR" in clean:
        curr = "EUR"
    elif "£" in clean or "GBP" in clean:
        curr = "GBP"
    elif "zł" in clean or "PLN" in clean:
        curr = "PLN"
    elif "¥" in clean or "JPY" in clean:
        curr = "JPY"

    match = re.search(r'(\d[\d\s.,]*\d|\d+)', clean)
    if not match:
        return None, curr

    num_str = match.group(1).replace(" ", "")

    if "," in num_str and "." in num_str:
        if num_str.rfind(",") > num_str.rfind("."):
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            num_str = num_str.replace(",", "")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            num_str = f"{parts[0]}.{parts[1]}"
        else:
            num_str = num_str.replace(",", "")

    try:
        val = round(float(num_str), 2)
        return val, curr
    except ValueError:
        return None, curr


class AliExpressScraper:
    """Async Playwright scraper for AliExpress catalog and search results."""

    def __init__(self, proxy: Optional[Dict[str, str]] = None, headless: bool = True):
        """Initialize scraper with optional proxy and headless configuration."""
        self.proxy = proxy
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def start(self) -> None:
        """Initialize Playwright browser and context with stealth settings."""
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--window-size=1440,900",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
            proxy=self.proxy,
        )

        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Stealth evasion scripts
        await self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            """
        )

    async def close(self) -> None:
        """Safely close browser context and Playwright instance."""
        try:
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.debug("Error closing context: %s", e)
        finally:
            self._context = None

        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.debug("Error closing browser: %s", e)
        finally:
            self._browser = None

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug("Error stopping playwright: %s", e)
        finally:
            self._playwright = None

    async def __aenter__(self) -> "AliExpressScraper":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _build_target_url(self, target: str, page_number: int = 1) -> str:
        """Construct full URL from either search query or category URL."""
        target = target.strip()
        if target.startswith("http://") or target.startswith("https://"):
            parsed = urlsplit(target)
            qs = parse_qs(parsed.query)
            if page_number > 1 or "page" in qs:
                qs["page"] = [str(page_number)]
            new_query = urlencode(qs, doseq=True)
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))

        query_clean = re.sub(r"\s+", "-", target)
        encoded_query = quote(query_clean, safe="-")
        return f"https://www.aliexpress.com/w/wholesale-{encoded_query}.html?page={page_number}"

    async def _setup_page_routes(self, page: Page) -> None:
        """Intercept and block heavy static resources for 3-5x faster scraping."""
        async def route_handler(route: Any) -> None:
            try:
                if route.request.resource_type in ["image", "media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                pass

        await page.route("**/*", route_handler)

    async def scrape_page(self, target: str, page_number: int = 1) -> List[AliProductItem]:
        """Scrape product listings from a target search query or category URL.

        Args:
            target: Search query (e.g. "wireless mouse") or full category/catalog URL.
            page_number: Target page number (1-indexed).

        Returns:
            List of parsed AliProductItem models.
        """
        if self._context is None:
            await self.start()

        if self._context is None:
            raise RuntimeError("Scraper browser context failed to initialize.")

        page = await self._context.new_page()
        try:
            await self._setup_page_routes(page)

            url = self._build_target_url(target, page_number)
            logger.info("Navigating to target URL: %s", url)

            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if response and response.status >= 400:
                    logger.warning("Target URL responded with status %d", response.status)
            except Exception as e:
                logger.warning("Initial navigation warning/timeout: %s", e)

            # Wait briefly for dynamic DOM hydration
            await page.wait_for_timeout(1500)

            # Progressive scroll to trigger lazy-loaded cards
            for _ in range(4):
                try:
                    await page.evaluate("window.scrollBy(0, 1000)")
                    await page.wait_for_timeout(700)
                except Exception:
                    break

            # Extract raw item structures from DOM cards and scripts
            raw_data = await page.evaluate(
                """() => {
                const results = [];
                const seen = new Set();

                const cards = document.querySelectorAll(
                    '.search-card-item, [class*="search-card-item"], [class*="search-item"], [class*="multi--content--"]'
                );

                for (const card of cards) {
                    let a = card.tagName.toLowerCase() === 'a' ? card : card.querySelector('a[href*="/item/"], a[href*="productIds="]');
                    if (!a) continue;

                    const href = a.getAttribute('href') || a.href || '';
                    let itemId = null;

                    const m1 = href.match(/\\/item\\/(\\d+)\\.html/);
                    if (m1) {
                        itemId = m1[1];
                    } else {
                        const m2 = href.match(/productIds=(\\d+)/);
                        if (m2) {
                            itemId = m2[1];
                        } else {
                            const m3 = href.match(/x_object_id%3A(\\d+)/);
                            if (m3) itemId = m3[1];
                        }
                    }

                    if (!itemId || seen.has(itemId)) continue;
                    seen.add(itemId);

                    const titleEl = card.querySelector('h3, [class*="titleText"], [class*="title--"]');
                    const title = titleEl ? titleEl.textContent.trim() : '';

                    const imgEl = card.querySelector('img');
                    let img = imgEl ? (imgEl.src || imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || imgEl.getAttribute('image-src') || '') : '';
                    if (img.startsWith('//')) img = 'https:' + img;

                    const saleEl = card.querySelector('[class*="price-sale--"], [class*="salePrice"]');
                    const saleText = saleEl ? saleEl.textContent.trim() : '';

                    const origEl = card.querySelector('[class*="price-original--"], [class*="originalPrice"]');
                    const origText = origEl ? origEl.textContent.trim() : '';

                    const ratingEl = card.querySelector('[class*="starRating--"], [class*="starRating"]');
                    const ratingText = ratingEl ? ratingEl.textContent.trim() : '';

                    const tradeEl = card.querySelector('[class*="trade--"]');
                    const tradeText = tradeEl ? tradeEl.textContent.trim() : '';

                    const storeEl = card.querySelector('a[href*="/store/"], [class*="store--"], [class*="shopName"]');
                    const storeText = storeEl ? storeEl.textContent.trim() : '';

                    const lines = card.innerText ? card.innerText.split('\\n').map(s => s.trim()).filter(Boolean) : [];

                    results.push({
                        itemId: itemId,
                        title: title,
                        img: img,
                        saleText: saleText,
                        origText: origText,
                        ratingText: ratingText,
                        tradeText: tradeText,
                        storeText: storeText,
                        lines: lines
                    });
                }

                return results;
            }"""
            )

            items: List[AliProductItem] = []
            seen_ids = set()

            for raw in raw_data:
                item_id = str(raw.get("itemId", "")).strip()
                if not item_id or item_id in seen_ids:
                    continue

                # Title resolution
                title = raw.get("title", "").strip()
                lines = raw.get("lines", [])
                if not title and lines:
                    for l in lines:
                        if len(l) > 15 and not l.startswith("грн") and not l.startswith("$"):
                            title = l
                            break
                if not title:
                    continue

                # Price resolution
                price, curr = parse_price_and_currency(raw.get("saleText"))
                orig_price = None
                if raw.get("origText"):
                    orig_price, _ = parse_price_and_currency(raw.get("origText"), curr)

                if price is None and lines:
                    for line in lines:
                        p_val, p_curr = parse_price_and_currency(line)
                        if p_val is not None:
                            price = p_val
                            curr = p_curr
                            break

                if price is None or price <= 0:
                    continue

                # Rating resolution
                rating: Optional[float] = None
                rating_text = raw.get("ratingText", "").strip()
                if rating_text:
                    try:
                        val = float(rating_text.replace(",", "."))
                        if 1.0 <= val <= 5.0:
                            rating = val
                    except ValueError:
                        pass

                if rating is None and lines:
                    for line in lines:
                        if re.match(r"^\d(\.\d)?$", line):
                            try:
                                val = float(line)
                                if 1.0 <= val <= 5.0:
                                    rating = val
                                    break
                            except ValueError:
                                pass

                # Orders count resolution
                orders_count: Optional[str] = raw.get("tradeText", "").strip() or None
                if not orders_count and lines:
                    for line in lines:
                        if re.search(r"\d[\d,]*\+?\s*sold", line, re.I):
                            orders_count = line
                            break

                # Store name
                store_name: Optional[str] = raw.get("storeText", "").strip() or None

                # Clean URLs
                product_url = f"https://www.aliexpress.com/item/{item_id}.html"
                image_url = raw.get("img", "").strip()
                if image_url.startswith("//"):
                    image_url = f"https:{image_url}"

                item = AliProductItem(
                    item_id=item_id,
                    title=title,
                    price=price,
                    original_price=orig_price,
                    currency=curr,
                    rating=rating,
                    orders_count=orders_count,
                    store_name=store_name,
                    product_url=product_url,
                    image_url=image_url,
                )
                items.append(item)
                seen_ids.add(item_id)

            return items

        finally:
            try:
                await page.close()
            except Exception as e:
                logger.debug("Error closing page: %s", e)
