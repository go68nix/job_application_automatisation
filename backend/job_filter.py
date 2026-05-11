"""Job filtering using Groq: geo check, talent fit, gap extraction."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.groq_client import call_groq


def _loads_ai_json(text: str) -> dict[str, Any]:
    """Parse AI-generated JSON more defensively.

    Some model outputs contain unescaped control characters (for example raw
    newlines inside string values). Python's JSON parser can accept those when
    strict=False.
    """
    return json.loads(text, strict=False)


def _normalize_gaps(raw_gaps: Any) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not isinstance(raw_gaps, list):
        return gaps

    for item in raw_gaps:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill", "")).strip()
        if not skill:
            continue

        in_cv = bool(item.get("in_cv", False))
        gap = bool(item.get("gap", not in_cv))
        gaps.append({"skill": skill, "in_cv": in_cv, "gap": gap})

    return gaps


def _build_gap_questions(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for gap in gaps:
        if not bool(gap.get("gap", False)) and bool(gap.get("in_cv", False)):
            continue
        skill = str(gap.get("skill", "")).strip()
        if not skill:
            continue
        questions.append({
            "skill": skill,
            "question": f"Do you have hands-on experience with {skill}?",
            "follow_up": f"How strong is your experience with {skill}, and where have you used it?",
            "options": ["yes", "somewhat", "no"],
        })
    return questions





async def parse_job_with_groq(page_content: str, url: str = "manual") -> dict[str, Any]:
    """Parse job content using Groq AI (fast + cheap)."""
    try:
        content_to_parse = page_content
        
        prompt = f"""Extract job posting details from the following content. Return ONLY a valid JSON object with these exact fields:
{{
  "company": "Company name or 'Unknown company'",
  "role": "Job title/role or 'Unknown role'",
  "location": "Location or 'Unknown'",
  "contact_information": "Contact email/phone/linkedin or 'Unknown'",
  "remote_ok": true or false (are there mentions of remote/hybrid/work from home?),
    "description": "Take the job description text from the scraped content and include it in full as the description field. Do not summarize it. Keep the relevant description section and important job details as-is."
}}

Content:
{content_to_parse}

Return ONLY valid JSON, no other text."""
        
        response_text = await call_groq(prompt)

        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            return {"error": "Groq response did not contain valid JSON"}

        try:
            parsed = _loads_ai_json(json_match.group(0))
        except Exception as e:
            return {"error": f"Failed to parse Groq JSON response: {e}"}

        job = {
            "company": parsed.get("company", "Unknown company"),
            "role": parsed.get("role", "Unknown role"),
            "description": parsed.get("description", content_to_parse[:500]),
            "location": parsed.get("location", "Unknown"),
            "contact_information": parsed.get("contact_information", "Unknown"),
            "remote_ok": bool(parsed.get("remote_ok", False)),
            "url": url,
        }

        return {"job": job}
    except Exception as e:
        return {"error": str(e)}


async def filter_job_with_groq(job: dict[str, Any], cv_text: str, base_location: str = "Munich, Germany") -> dict[str, Any]:
    """Filter job against user CV: geo check, talent fit, extract gaps."""
    job_desc = job.get("description", "")
    company = job.get("company", "Unknown")
    role = job.get("role", "Unknown")
    location = job.get("location", "Unknown")
    
    try:
        prompt = f"""Analyze this job posting and extract the TECHNICAL SKILLS and TOOLS it requires.

Return ONLY a valid JSON object with this shape:
{{
    "geo_verdict": "green" | "yellow" | "red",
    "geo_reason": "short explanation",
    "talent_fit_score": 0-100,
    "talent_fit_reason": "short explanation",
    "requirements": [
        {{ "skill": "technology/tool/framework name", "in_cv": true|false }}
    ],
    "overall_recommendation": "brief summary - worth applying?"
}}

Instructions:
- Extract ALL technical skills, tools, frameworks, libraries, languages, databases, platforms mentioned in the job description.
- Include both explicitly stated and reasonably implied requirements.
- Do NOT include soft skills, generic duties, numbers, dates, or noise.
- For each skill: set `in_cv=true` ONLY if it is explicitly mentioned in the user's CV text below. Otherwise `in_cv=false`.
- Return ONLY skills that appear in the job description but NOT in the user's CV (these are the gaps).
- No truncation: return the complete, exhaustive list.
- Return valid JSON only, no other text.

Job Details:
- Company: {company}
- Role: {role}
- Location: {location}
- Description: {job_desc}

User's CV:
{cv_text}

User Preferred Location: {base_location}

Return ONLY valid JSON, no other text."""
        
        response_text = await call_groq(prompt)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            return {"error": "Groq filter response did not contain valid JSON"}
        
        parsed = _loads_ai_json(json_match.group(0))

        # Use the AI-provided requirements (or fallback to 'gaps'). Keep only missing skills.
        raw_reqs = parsed.get("requirements", parsed.get("gaps", []))
        gaps: list[dict[str, Any]] = []
        for item in raw_reqs:
            if not isinstance(item, dict):
                continue
            skill = str(item.get("skill", "")).strip()
            if not skill:
                continue
            # filter out obvious noise: pure numbers or date-like tokens
            if re.fullmatch(r"\d+(?:\.\d+)?", skill):
                continue
            if re.search(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b", skill):
                continue
            in_cv = bool(item.get("in_cv", False))
            gap = bool(item.get("gap", not in_cv))
            # keep only missing skills (those not found in CV)
            if gap:
                gaps.append({"skill": skill, "in_cv": in_cv, "gap": gap})
        talent_fit_score = int(parsed.get("talent_fit_score", 0) or 0)
        geo_verdict = str(parsed.get("geo_verdict", "unknown")).strip().lower()
        if geo_verdict not in {"green", "yellow", "red"}:
            geo_verdict = "yellow"

        needs_warning = geo_verdict == "red" or talent_fit_score < 40
        warning_message = "This job may not be a good fit. Continue anyway?" if needs_warning else ""

        return {
            "geo_verdict": geo_verdict,
            "geo_reason": parsed.get("geo_reason", ""),
            "talent_fit_score": talent_fit_score,
            "talent_fit_reason": parsed.get("talent_fit_reason", ""),
            "gaps": gaps,
            "gap_questions": _build_gap_questions(gaps),
            "needs_warning": needs_warning,
            "warning_message": warning_message,
            "overall_recommendation": parsed.get("overall_recommendation", ""),
        }
    except Exception as e:
        return {"error": f"Filter failed: {str(e)}"}
