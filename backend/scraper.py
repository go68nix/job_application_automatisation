from __future__ import annotations

import asyncio
import random
import re
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

REMOTE_PATTERNS = ("remote", "hybrid", "work from home", "home office")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


async def scrape_job(url: str) -> dict[str, Any] | None:
    await asyncio.sleep(random.uniform(2, 4))
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)

            title = _clean(await page.title())
            h1 = _clean(await page.locator("h1").first.text_content() or "")
            body_text = _clean(await page.locator("body").inner_text())

            role = h1 or title or "Unknown role"
            company = "Unknown company"
            for selector in [
                '[data-testid*="company"]',
                '[class*="company"]',
                'meta[property="og:site_name"]',
            ]:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    value = await locator.get_attribute("content") if "meta" in selector else await locator.text_content()
                    if value and _clean(value):
                        company = _clean(value)
                        break

            location = "Unknown"
            location_match = re.search(
                r"(location|based in|office|city)[:\s\-]+([A-Za-z0-9,\-\s]{3,80})",
                body_text,
                flags=re.IGNORECASE,
            )
            if location_match:
                location = _clean(location_match.group(2))

            lower = body_text.lower()
            remote_ok = any(word in lower for word in REMOTE_PATTERNS)

            await browser.close()
            return {
                "company": company,
                "role": role,
                "description": body_text[:25000],
                "location": location,
                "remote_ok": remote_ok,
                "url": url,
            }
    except (PlaywrightTimeoutError, Exception):
        return None
