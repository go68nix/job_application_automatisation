from __future__ import annotations

from typing import Any

from .gemini_client import call_gemini
from .prompts import COVER_LETTER_PROMPT, CV_GENERATION_PROMPT


def _gap_context(gap_answers: list[dict[str, str]]) -> str:
    lines = []
    for item in gap_answers:
        skill = item.get("skill", "").strip()
        answer = item.get("answer", "").strip().lower()
        detail = item.get("detail", "").strip()
        if not skill:
            continue
        lines.append(f"- skill: {skill}; answer: {answer}; detail: {detail}")
    return "\n".join(lines) if lines else "- no gaps provided"


async def generate_documents(
    job: dict[str, Any],
    cv_base64: str,
    gap_answers: list[dict[str, str]],
    gap_summary_text: str | None = None,
) -> dict[str, str]:
    job_context = (
        f"Company: {job.get('company', '')}\n"
        f"Role: {job.get('role', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Description:\n{job.get('description', '')}"
    )
    gap_context = _gap_context(gap_answers)
    gap_summary = (gap_summary_text or "").strip()
    gap_summary_block = gap_summary if gap_summary else "- no manual gap summary provided"

    cv_prompt = (
        f"{CV_GENERATION_PROMPT}\n\n"
        f"Job context:\n{job_context}\n\n"
        f"Gap answers:\n{gap_context}\n\n"
        f"Gap summary to append after the CV:\n{gap_summary_block}"
    )
    cl_prompt = (
        f"{COVER_LETTER_PROMPT}\n\n"
        f"Job context:\n{job_context}\n\n"
        f"Gap answers:\n{gap_context}\n\n"
        f"Gap summary to append after the CV:\n{gap_summary_block}"
    )

    cv_text = await call_gemini(cv_prompt, pdf_base64=cv_base64)
    cover_letter_text = await call_gemini(cl_prompt, pdf_base64=cv_base64)
    return {"cv_text": cv_text.strip(), "cover_letter_text": cover_letter_text.strip()}
