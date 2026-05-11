from __future__ import annotations

import httpx


async def call_make_webhook(webhook_url: str, payload: dict) -> dict:
    """Send payload to a Make webhook and return JSON response."""
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"data": data}

    raw_text = response.text.strip()
    if not raw_text:
        return {}

    try:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"data": data}
    except Exception:
        return {"raw_response": raw_text}
