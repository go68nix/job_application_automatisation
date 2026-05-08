from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx

from .prompts import GEO_CHECK_PROMPT, PROFILE_MATCH_PROMPT, REQUIREMENTS_EXTRACT_PROMPT

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "user_config.json"
MASTER_CV_PATH = DATA_DIR / "master_cv.pdf"


async def call_gemini(prompt: str, pdf_base64: str | None = None) -> str:
    parts = []
    if pdf_base64:
        parts.append({
            "inline_data": {
                "mime_type": "application/pdf",
                "data": pdf_base64
            }
        })
    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1500
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GEMINI_URL,
            params={"key": os.getenv("GEMINI_API_KEY")},
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def load_user_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {
            "base_location": "",
            "max_commute": "",
            "target_roles": [],
            "deal_breakers": [],
        }
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_master_cv_base64() -> str:
    if not MASTER_CV_PATH.exists():
        raise FileNotFoundError("Master CV not uploaded yet")
    return base64.b64encode(MASTER_CV_PATH.read_bytes()).decode("utf-8")


async def stage_1_geo_check(job: dict[str, Any]) -> dict[str, str]:
    config = load_user_config()
    prompt = (
        f"{GEO_CHECK_PROMPT}\n\n"
        f"User config:\n{json.dumps(config)}\n\n"
        f"Job location: {job.get('location', '')}\n"
        f"Job remote_ok: {job.get('remote_ok', False)}"
    )
    try:
        result = _extract_json(await call_gemini(prompt))
        verdict = result.get("verdict", "yellow")
        if verdict not in {"green", "yellow", "red"}:
            verdict = "yellow"
        return {
            "verdict": verdict,
            "reason": str(result.get("reason", "Location compatibility estimated."))
        }
    except Exception:
        return {"verdict": "yellow", "reason": "Could not verify location automatically."}


async def stage_2_profile_match(job_description: str, cv_base64: str) -> dict[str, Any]:
    prompt = (
        f"{PROFILE_MATCH_PROMPT}\n\n"
        "Evaluate this job description:\n"
        f"{job_description}\n"
    )
    try:
        result = _extract_json(await call_gemini(prompt, pdf_base64=cv_base64))
        score = int(result.get("match_score", 0))
        score = max(0, min(100, score))
        if score >= 65:
            verdict = "strong"
        elif score >= 40:
            verdict = "partial"
        else:
            verdict = "mismatch"
        return {
            "match_score": score,
            "verdict": verdict,
            "reason": str(result.get("reason", "Profile match estimated.")),
        }
    except Exception:
        return {"match_score": 0, "verdict": "mismatch", "reason": "Could not score profile automatically."}


async def stage_3_gap_qa(job_description: str, cv_base64: str) -> dict[str, Any]:
    prompt = (
        f"{REQUIREMENTS_EXTRACT_PROMPT}\n\n"
        "Job description:\n"
        f"{job_description}\n"
    )
    try:
        result = _extract_json(await call_gemini(prompt, pdf_base64=cv_base64))
        requirements = result.get("requirements", [])
        if not isinstance(requirements, list):
            requirements = []
        normalized = []
        for item in requirements:
            if not isinstance(item, dict):
                continue
            skill = str(item.get("skill", "")).strip()
            if not skill:
                continue
            in_cv = bool(item.get("in_cv", False))
            gap = bool(item.get("gap", not in_cv))
            normalized.append({"skill": skill, "in_cv": in_cv, "gap": gap})
        return {"requirements": normalized}
    except Exception:
        return {"requirements": []}
