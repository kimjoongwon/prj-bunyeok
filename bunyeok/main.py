from __future__ import annotations

import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bunyeok.job_store import job_store
from bunyeok.translator import run_translation_job

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Bunyeok", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def translation_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) or os.getenv("MOCK_TRANSLATION", "false").lower() == "true"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    server_api_key_available = bool(os.getenv("OPENAI_API_KEY"))
    mock_translation = os.getenv("MOCK_TRANSLATION", "false").lower() == "true"

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "translation_enabled": translation_enabled(),
            "default_target_language": "Korean",
            "server_api_key_available": server_api_key_available,
            "mock_translation": mock_translation,
        },
    )


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_language: str = Form("Korean"),
    openai_api_key: str = Form(""),
) -> JSONResponse:
    filename = file.filename or "document.pdf"
    looks_like_pdf = filename.lower().endswith(".pdf") or file.content_type == "application/pdf"

    if not looks_like_pdf:
        raise HTTPException(status_code=400, detail="PDF 형식만 업로드할 수 있습니다.")

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="비어 있는 파일은 처리할 수 없습니다.")

    job = job_store.create(filename=filename, target_language=target_language.strip() or "Korean")

    background_tasks.add_task(
        run_translation_job,
        job.id,
        filename,
        file_bytes,
        target_language.strip() or "Korean",
        openai_api_key.strip() or None,
    )

    return JSONResponse(
        {
            "job_id": job.id,
            "job": job_store.serialize(job),
        },
        status_code=202,
    )


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    job = job_store.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="작업 정보를 찾을 수 없습니다.")

    return JSONResponse(job_store.serialize(job), headers={"Cache-Control": "no-store"})


@app.get("/api/jobs/{job_id}/download")
async def download_markdown(job_id: str) -> Response:
    job = job_store.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="작업 정보를 찾을 수 없습니다.")

    if job.status != "completed" or not job.translated_markdown:
        raise HTTPException(status_code=409, detail="아직 내려받을 결과가 없습니다.")

    headers = {
        "Content-Disposition": f'attachment; filename="{job.download_filename or "translated-document.md"}"',
        "Cache-Control": "no-store",
    }

    return PlainTextResponse(job.translated_markdown, headers=headers, media_type="text/markdown")
