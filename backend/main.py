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
    load_user_config,
    stage_1_geo_check,
    stage_2_profile_match,
    stage_3_gap_qa,
)
from .generator import generate_documents
from .pdf_builder import build_pdfs
from .scraper import scrape_job
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
            "date_generated": datetime.now(timezone.utc).isoformat(),
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
