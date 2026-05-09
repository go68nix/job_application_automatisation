"""Job filtering using Groq: geo check, talent fit, gap extraction."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.groq_client import call_groq


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
            parsed = json.loads(json_match.group(0))
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
        prompt = f"""Analyze this job posting against the user's profile. Return ONLY a valid JSON object:
{{
  "geo_verdict": "green" (job in Munich central), "yellow" (near Munich/remote), or "red" (far/not suitable),
  "geo_reason": "Brief explanation of location decision",
  "talent_fit_score": 0-100,
  "talent_fit_reason": "Brief explanation of talent match",
  "gaps": [
    {{
      "skill": "Skill/requirement name",
      "in_cv": false (if user doesn't have it)
    }}
  ],
  "overall_recommendation": "brief summary - worth applying?"
}}

Job Details:
- Company: {company}
- Role: {role}
- Location: {location}
- Description: {job_desc[:2000]}

User CV (first 2000 chars):
{cv_text[:2000]}

User Preferred Location: {base_location}

Return ONLY valid JSON, no other text."""
        
        response_text = await call_groq(prompt)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            return {"error": "Groq filter response did not contain valid JSON"}
        
        parsed = json.loads(json_match.group(0))
        return {
            "geo_verdict": parsed.get("geo_verdict", "unknown"),
            "geo_reason": parsed.get("geo_reason", ""),
            "talent_fit_score": parsed.get("talent_fit_score", 0),
            "talent_fit_reason": parsed.get("talent_fit_reason", ""),
            "gaps": parsed.get("gaps", []),
            "overall_recommendation": parsed.get("overall_recommendation", ""),
        }
    except Exception as e:
        return {"error": f"Filter failed: {str(e)}"}
