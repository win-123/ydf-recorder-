from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def chromium_browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


@pytest.fixture
def popup_page(chromium_browser):
    page = chromium_browser.new_page()
    yield page
    page.close()
