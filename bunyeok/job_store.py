from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TranslationJob:
    id: str
    filename: str
    target_language: str
    status: str
    progress: int
    message: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    error: str | None = None
    translated_markdown: str | None = None
    source_page_count: int | None = None
    chunk_count: int | None = None
    download_filename: str | None = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, TranslationJob] = {}
        self._lock = Lock()

    def create(self, filename: str, target_language: str) -> TranslationJob:
        now = utcnow_iso()
        job = TranslationJob(
            id=str(uuid4()),
            filename=filename,
            target_language=target_language,
            status="queued",
            progress=0,
            message="번역 작업을 준비하고 있습니다.",
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._jobs[job.id] = job

        return job

    def get(self, job_id: str) -> TranslationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: Any) -> TranslationJob | None:
        with self._lock:
            job = self._jobs.get(job_id)

            if job is None:
                return None

            for key, value in changes.items():
                setattr(job, key, value)

            job.updated_at = utcnow_iso()

            return job

    def fail(self, job_id: str, error: Exception | str) -> TranslationJob | None:
        message = str(error)
        return self.update(
            job_id,
            status="failed",
            progress=100,
            message="번역 작업이 실패했습니다.",
            error=message,
        )

    @staticmethod
    def serialize(job: TranslationJob) -> dict[str, Any]:
        payload = asdict(job)
        markdown = payload.pop("translated_markdown")
        payload["has_download"] = markdown is not None
        payload["preview"] = markdown[:1200] if markdown else ""
        return payload


job_store = JobStore()
