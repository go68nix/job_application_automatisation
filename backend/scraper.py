from __future__ import annotations

import asyncio
import html
import json
import random
import re
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from backend.groq_client import call_groq

REMOTE_PATTERNS = ("remote", "hybrid", "work from home", "home office")
MIN_SCRAPE_DELAY_SECONDS = 2
MAX_SCRAPE_DELAY_SECONDS = 4


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _clean_keep_lines(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_to_text(content: str) -> str:
    content = html.unescape(content or "")
    content = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", content)
    content = re.sub(r"(?is)<br\s*/?>", "\n", content)
    content = re.sub(r"(?is)</(p|div|li|h[1-6]|article|section|tr|table)>", "\n", content)
    content = re.sub(r"(?s)<[^>]+>", " ", content)
    return _clean_keep_lines(content)


def _extract_tag_content(content: str, tag: str) -> str:
    match = re.search(rf"(?is)<{tag}[^>]*>(.*?)</{tag}>", content or "")
    if not match:
        return ""
    value = re.sub(r"(?s)<[^>]+>", " ", html.unescape(match.group(1)))
    return _clean(value)


def _extract_company(body_text: str) -> str:
    company_match = re.search(
        r"(?:company|employer|hiring company)[:\s\-]+(.{2,80}?)(?=\s*(?:location|role|title|position|description|remote)\b|$)",
        body_text,
        flags=re.IGNORECASE,
    )
    if company_match:
        return _clean(company_match.group(1))
    return "Unknown company"


def _extract_location(body_text: str) -> str:
    location_match = re.search(
        r"(?:location|based in|based at|office in|work location)[:\s\-]+(.{2,100}?)(?=\s*(?:contact|email|phone|mobile|role|title|position|description|remote|hybrid|work from home)\b|\.|\||;|$)",
        body_text,
        flags=re.IGNORECASE,
    )
    if location_match:
        return _clean(location_match.group(1))
    return "Unknown"


def _extract_contact_information(body_text: str) -> str:
    email_matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", body_text or "")
    phone_matches = re.findall(
        r"(?:\+\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}",
        body_text or "",
    )
    linkedin_matches = re.findall(r"https?://(?:www\.)?linkedin\.com/[^\s)]+", body_text or "", flags=re.IGNORECASE)

    contacts: list[str] = []
    for item in email_matches[:3]:
        cleaned = _clean(item)
        if cleaned and cleaned not in contacts:
            contacts.append(cleaned)

    for item in phone_matches[:3]:
        cleaned = _clean(item)
        digit_count = len(re.sub(r"\D", "", cleaned))
        if cleaned and digit_count >= 7 and cleaned not in contacts:
            contacts.append(cleaned)

    for item in linkedin_matches[:2]:
        cleaned = _clean(item)
        if cleaned and cleaned not in contacts:
            contacts.append(cleaned)

    if not contacts:
        return "Unknown"
    return " | ".join(contacts[:5])


def _parse_job_text(body_text: str, *, url: str, title: str | None = None, company: str | None = None, location: str | None = None) -> dict[str, Any]:
    raw_text = body_text or ""
    body_text = _clean(raw_text)
    role = _clean(title or "") or "Unknown role"
    if role == "Unknown role":
        role_match = re.search(
            r"(?:title|role|position)[:\s\-]+(.{2,100}?)(?:\.|\n|\||$)",
            body_text,
            flags=re.IGNORECASE,
        )
        if role_match:
            role = _clean(role_match.group(1))

    resolved_company = _clean(company or "") or _extract_company(raw_text)
    resolved_location = _clean(location or "") or _extract_location(raw_text)
    resolved_contact_information = _extract_contact_information(raw_text)
    lower = body_text.lower()
    remote_ok = any(word in lower for word in REMOTE_PATTERNS)

    return {
        "company": resolved_company,
        "role": role,
        "description": body_text[:25000],
        "location": resolved_location,
        "contact_information": resolved_contact_information,
        "remote_ok": bool(remote_ok),
        "url": url,
    }


async def parse_pasted_page(page_content: str, url: str = "manual") -> dict[str, Any] | None:
    try:
        is_html = "<" in page_content and ">" in page_content
        body_text = _html_to_text(page_content) if is_html else _clean(page_content)
        if not body_text:
            return None
        title = _extract_tag_content(page_content, "h1") if is_html else ""
        if not title and is_html:
            title = _extract_tag_content(page_content, "title")
        return _parse_job_text(body_text, url=url, title=title)
    except Exception:
        return None


async def scrape_job(url: str) -> dict[str, Any] | None:
    # Add a small randomized delay to mimic human behavior
    await asyncio.sleep(random.uniform(MIN_SCRAPE_DELAY_SECONDS, MAX_SCRAPE_DELAY_SECONDS))
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # give page some time to render dynamic content
            await page.wait_for_timeout(1500)

            title = _clean(await page.title())
            # prefer H1 for role/title if present
            h1 = _clean((await page.locator("h1").first.text_content()) or "")

            # try some common selectors for the job description
            desc_selectors = [
                '[data-testid*="job-description"]',
                '[class*="job-description"]',
                '[class*="job-desc"]',
                'article',
                'div[itemprop="description"]',
                'div[class*="description"]',
                'section[class*="description"]',
            ]
            body_text = ""
            for sel in desc_selectors:
                loc = page.locator(sel).first
                try:
                    if await loc.count() > 0:
                        txt = await loc.inner_text()
                        if txt and _clean(txt):
                            body_text = _clean(txt)
                            break
                except Exception:
                    continue

            # fallback to the full body text
            if not body_text:
                try:
                    body_text = _clean(await page.locator('body').inner_text())
                except Exception:
                    body_text = ""

            role = h1 or title or "Unknown role"

            # company extraction heuristics
            company = "Unknown company"
            company_selectors = [
                '[data-testid*="company"]',
                '[class*="company"]',
                '[class*="employer"]',
                'meta[property="og:site_name"]',
                'meta[name="og:site_name"]',
            ]
            for selector in company_selectors:
                try:
                    if selector.startswith('meta'):
                        loc = page.locator(selector)
                        if await loc.count() > 0:
                            value = await loc.first.get_attribute('content')
                            if value and _clean(value):
                                company = _clean(value)
                                break
                    else:
                        loc = page.locator(selector).first
                        if await loc.count() > 0:
                            value = await loc.text_content()
                            if value and _clean(value):
                                company = _clean(value)
                                break
                except Exception:
                    continue

            # location heuristics
            location = "Unknown"
            location_match = re.search(r"(location|based in|based at|office in)[:\s\-]+([A-Za-z0-9,\-\s]{2,80})", body_text, flags=re.IGNORECASE)
            if location_match:
                location = _clean(location_match.group(2))
            else:
                # try common location selectors
                for sel in ['[class*="location"]', '[data-testid*="location"]', 'span[aria-label*="location"]']:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0:
                            txt = await loc.text_content()
                            if txt and _clean(txt):
                                location = _clean(txt); break
                    except Exception:
                        continue

            return _parse_job_text(body_text, url=url, title=role, company=company, location=location)
    except (PlaywrightTimeoutError, Exception):
        return None
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass


async def parse_job_with_ai(page_content: str, url: str = "manual") -> dict[str, Any] | None:
    """Parse job content using Groq AI (fast, cheap fallback)."""
    try:
        content_to_parse = page_content
        prompt = f"""Extract job posting details from the following content. Return a JSON object with these exact fields:
{{
    "company": "Company name or 'Unknown company'",
    "role": "Job title/role or 'Unknown role'",
    "location": "Location or 'Unknown'",
    "contact_information": "Contact email/phone/linkedin or 'Unknown'",
    "remote_ok": true/false (are there any mentions of remote/hybrid/work from home?),
    "description": "Take the job description text from the scraped content and include it in full as the description field. Do not summarize it. Keep the relevant description section and important job details as-is."
}}

Content to parse:
{content_to_parse}

Return ONLY valid JSON, no other text."""

        response_text = await call_groq(prompt)

        # Extract JSON from response (in case there's extra text)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            # return an error dict so caller can surface the reason
            return {"error": "AI response did not contain valid JSON"}

        try:
            parsed = json.loads(json_match.group(0))
        except Exception as e:
            return {"error": f"Failed to parse AI JSON response: {e}"}

        job = {
            "company": parsed.get("company", "Unknown company"),
            "role": parsed.get("role", "Unknown role"),
            "description": parsed.get("description", content_to_parse),
            "location": parsed.get("location", "Unknown"),
            "contact_information": parsed.get("contact_information", "Unknown"),
            "remote_ok": bool(parsed.get("remote_ok", False)),
            "url": url,
        }

        return {"job": job}
    except Exception as e:
        # include exception text for visibility
        return {"error": str(e)}
