from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

# Load .env file at module import time
load_dotenv()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


async def call_groq(prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    """Call Groq API for fast, cost-effective inference."""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1500,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if not response.is_success:
            error_text = response.text
            print(f"Groq API error: {response.status_code} - {error_text}")
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
