from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .fit_check import (
    load_master_cv_base64,
    load_master_cv_text,
    load_user_config,
    stage_1_geo_check,
    stage_2_profile_match,
    stage_3_gap_qa,
)
from .generator import generate_documents
from .pdf_builder import build_pdfs
from .scraper import parse_pasted_page, scrape_job, parse_job_with_ai
from .job_filter import parse_job_with_groq, filter_job_with_groq
from fastapi import Body
from .tracker import delete_application, get_all_applications, init_db, save_application, update_notes, update_status

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
CONFIG_PATH = DATA_DIR / "user_config.json"
MASTER_CV_PATH = DATA_DIR / "master_cv.pdf"

app = FastAPI(title="job-applier")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FitCheckRequest(BaseModel):
    url: str | None = None
    manual_description: str | None = None
    company: str | None = None
    role: str | None = None
    location: str | None = None
    remote_ok: bool | None = None


class GenerateRequest(BaseModel):
    job: dict[str, Any]
    gap_answers: list[dict[str, str]] = Field(default_factory=list)
    match_score: int | None = None


class ConfigModel(BaseModel):
    base_location: str
    max_commute: str
    target_roles: list[str]
    deal_breakers: list[str]


class PatchApplication(BaseModel):
    status: str | None = None
    notes: str | None = None


@app.get("/")
async def serve_frontend() -> FileResponse:
    frontend_index = BASE_DIR / "frontend" / "index.html"
    if not frontend_index.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(path=frontend_index)


@app.on_event("startup")
async def startup_event() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "base_location": "Munich, Germany",
                    "max_commute": "same city or remote",
                    "target_roles": ["software engineer", "backend developer"],
                    "deal_breakers": ["sales", "pure management"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    init_db()


@app.post("/upload-cv")
async def upload_cv(file: UploadFile = File(...)) -> dict[str, bool]:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    MASTER_CV_PATH.write_bytes(content)
    return {"success": True}


@app.get("/master-cv")
async def get_master_cv() -> FileResponse:
    if not MASTER_CV_PATH.exists():
        raise HTTPException(status_code=404, detail="Master CV not uploaded yet")
    return FileResponse(
        path=MASTER_CV_PATH,
        media_type="application/pdf",
        filename=MASTER_CV_PATH.name,
        content_disposition_type="inline",
    )


@app.get('/master-cv-text')
async def get_master_cv_text() -> dict[str, Any]:
    """Return extracted plain text from the uploaded master CV PDF."""
    try:
        text = load_master_cv_text()
        # If the loader returned a base64 PDF (fallback), detect and return a helpful message
        try:
            import base64
            decoded = base64.b64decode(text)
            if isinstance(decoded, (bytes, bytearray)) and decoded[:4] == b"%PDF":
                return {"text": "[Text extraction failed: PDF appears to be binary or image-scanned. Please upload a selectable-text PDF or enable OCR.]", "extracted": False}
        except Exception:
            # not base64 or decode failed — treat as plain text
            pass
        return {"text": text, "extracted": True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to extract CV text: {exc}") from exc


@app.post("/fit-check")
async def fit_check(payload: FitCheckRequest) -> dict[str, Any]:
    job = None
    if payload.url:
        job = await scrape_job(payload.url)

    if not job:
        if not payload.manual_description:
            return {
                "error": "Scraping failed. Please paste the job description manually.",
                "need_manual_description": True,
            }
        job = {
            "company": payload.company or "Unknown company",
            "role": payload.role or "Unknown role",
            "description": payload.manual_description,
            "location": payload.location or "Unknown",
            "remote_ok": bool(payload.remote_ok),
            "url": payload.url or "manual",
        }

    try:
        cv_base64 = load_master_cv_base64()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    geo = await stage_1_geo_check(job)
    profile = await stage_2_profile_match(job.get("description", ""), cv_base64)
    gaps_result = await stage_3_gap_qa(job.get("description", ""), cv_base64)
    gaps = [{"skill": item["skill"]} for item in gaps_result.get("requirements", []) if item.get("gap")]

    return {"job": job, "geo": geo, "profile": profile, "gaps": gaps}


@app.post('/scrape')
async def scrape_endpoint(payload: dict = Body(...)) -> dict[str, Any]:
    """Lightweight scrape endpoint that returns raw scrape result or an indicator
    that manual description is needed."""
    url = payload.get('url')
    page_content = payload.get('page_content')
    if not url and not page_content:
        raise HTTPException(status_code=400, detail='Provide url or page_content in JSON body')

    if page_content:
        job = await parse_pasted_page(page_content, url=url or 'manual')
    else:
        job = await scrape_job(url)
    if not job:
        return {
            'error': 'Scraping failed',
            'need_manual_description': True,
        }
    return {'job': job}


@app.post('/scrape-with-ai')
async def scrape_with_ai_endpoint(payload: dict = Body(...)) -> dict[str, Any]:
    """Parse job content using Gemini AI. Expects page_content and optional url."""
    page_content = payload.get('page_content')
    url = payload.get('url')
    
    if not page_content:
        raise HTTPException(status_code=400, detail='Provide page_content in JSON body')
    
    result = await parse_job_with_ai(page_content, url=url or 'manual')
    # parse_job_with_ai now returns either {"job": {...}} or {"error": "..."}
    if not result:
        return {
            'error': 'AI parsing failed',
            'need_manual_description': True,
        }
    if isinstance(result, dict) and result.get('error'):
        return {'error': result.get('error'), 'need_manual_description': True}
    if isinstance(result, dict) and result.get('job'):
        return {'job': result.get('job')}
    # fallback
    return {'error': 'AI parsing failed', 'need_manual_description': True}


@app.post('/filter-job')
async def filter_job_endpoint(payload: dict = Body(...)) -> dict[str, Any]:
    """Filter job using Groq: geo check, talent fit, extract gaps."""
    job = payload.get('job')
    
    if not job or not isinstance(job, dict):
        raise HTTPException(status_code=400, detail='Provide job object in request body')
    
    try:
        # Prefer extracting real text from the PDF
        cv_text = load_master_cv_text()
    except Exception:
        cv_text = "No CV available - please upload a CV first"
    
    user_config = load_user_config()
    base_location = user_config.get('base_location', 'Munich, Germany')
    
    result = await filter_job_with_groq(job, cv_text, base_location)
    if result.get('error'):
        return {'error': result.get('error')}
    
    return result



@app.post("/generate")
async def generate(payload: GenerateRequest) -> dict[str, Any]:
    try:
        cv_base64 = load_master_cv_base64()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        generated = await generate_documents(payload.job, cv_base64, payload.gap_answers)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Document generation failed: {exc}") from exc
    cv_path, cl_path = build_pdfs(
        payload.job.get("company", "Unknown company"),
        payload.job.get("role", "Unknown role"),
        generated["cv_text"],
        generated["cover_letter_text"],
    )

    application_id = save_application(
        {
            "company": payload.job.get("company"),
            "role": payload.job.get("role"),
            "url": payload.job.get("url"),
            "match_score": payload.match_score,
            "status": "Generated",
            "date_generated": datetime.now(tz=timezone.utc).isoformat(),
            "cv_path": cv_path,
            "cl_path": cl_path,
            "notes": "",
        }
    )

    return {
        "cv_path": cv_path,
        "cl_path": cl_path,
        "application_id": application_id,
        "cv_text": generated["cv_text"],
        "cover_letter_text": generated["cover_letter_text"],
    }


@app.get("/applications")
async def list_applications() -> list[dict[str, Any]]:
    return get_all_applications()


@app.patch("/applications/{application_id}")
async def patch_application(application_id: int, payload: PatchApplication) -> dict[str, bool]:
    if payload.status is None and payload.notes is None:
        raise HTTPException(status_code=400, detail="Provide status or notes")
    if payload.status is not None:
        update_status(application_id, payload.status)
    if payload.notes is not None:
        update_notes(application_id, payload.notes)
    return {"success": True}


@app.delete("/applications/{application_id}")
async def remove_application(application_id: int) -> dict[str, bool]:
    delete_application(application_id)
    return {"success": True}


@app.get("/outputs/{filepath:path}")
async def get_output(filepath: str) -> FileResponse:
    safe_path = (OUTPUT_DIR / filepath).resolve()
    if not str(safe_path).startswith(str(OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid output path")
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=safe_path)


@app.get("/config")
async def get_config() -> dict[str, Any]:
    config = load_user_config()
    config["cv_uploaded"] = MASTER_CV_PATH.exists()
    return config


@app.post("/config")
async def save_config(config: ConfigModel) -> dict[str, bool]:
    CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return {"success": True}
