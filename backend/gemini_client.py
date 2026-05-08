from __future__ import annotations

import os

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def call_gemini(prompt: str, pdf_base64: str | None = None) -> str:
    parts = []
    if pdf_base64:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": pdf_base64,
                }
            }
        )
    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1500,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GEMINI_URL,
            params={"key": os.getenv("GEMINI_API_KEY")},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
