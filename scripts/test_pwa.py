"""Verification script for English PWA frontend routes and assets."""

import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from src.api.app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_pwa")


def run_pwa_tests() -> None:
    """Verify PWA HTML dashboard, manifest.json, Service Worker, and SVG icon endpoints."""
    client = TestClient(app)

    # 1. Test GET / (Main English PWA Dashboard)
    logger.info("Step 1: Testing GET / (English PWA Dashboard)...")
    res_index = client.get("/")
    assert res_index.status_code == 200, f"Expected 200 OK on GET /, got {res_index.status_code}"
    assert "text/html" in res_index.headers.get("content-type", "")
    html_text = res_index.text
    for expected_phrase in (
        "AliParser",
        "Start Scraping",
        "Export Excel",
        "Proxy Manager",
        "manifest.json",
        "bg-slate-50",
        "stepInput",
    ):
        assert expected_phrase in html_text, f"Missing expected English UI element '{expected_phrase}' in index.html"
    assert "View Item ↗" not in html_text, "Found forbidden 'View Item ↗' arrow in index.html"
    assert ">View Item<" in html_text, "Missing clean 'View Item' button in index.html"
    logger.info("  [OK] GET / returned 200 OK with Light Theme, custom steppers, and clean View Item button")

    # 2. Test GET /manifest.json
    logger.info("Step 2: Testing GET /manifest.json...")
    res_manifest = client.get("/manifest.json")
    assert res_manifest.status_code == 200
    manifest_data = res_manifest.json()
    assert "name" in manifest_data and "AliParser" in manifest_data["name"]
    assert manifest_data.get("background_color") == "#f8fafc"
    assert "icons" in manifest_data and len(manifest_data["icons"]) > 0
    logger.info("  [OK] GET /manifest.json returned valid Web App Manifest ('%s')", manifest_data["name"])

    # 3. Test GET /sw.js
    logger.info("Step 3: Testing GET /sw.js...")
    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200
    assert "javascript" in res_sw.headers.get("content-type", "")
    assert "addEventListener" in res_sw.text
    logger.info("  [OK] GET /sw.js returned Service Worker script (%d bytes)", len(res_sw.text))

    # 4. Test GET /icon.svg
    logger.info("Step 4: Testing GET /icon.svg...")
    res_icon = client.get("/icon.svg")
    assert res_icon.status_code == 200
    assert "image/svg+xml" in res_icon.headers.get("content-type", "")
    assert "<svg" in res_icon.text
    logger.info("  [OK] GET /icon.svg returned valid SVG vector icon (%d bytes)", len(res_icon.text))

    print("\nALL PWA FRONTEND TESTS PASSED")


if __name__ == "__main__":
    run_pwa_tests()
