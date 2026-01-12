# app/api/routes/ingest.py
"""
Log ingestion endpoint.

Responsibilities:
- Accept CSV/TXT uploads
- Validate file type and content
- Parse logs with delimiter + header detection
- Persist logs + file metadata to SQLite
- Return structured ingestion statistics

"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IngestedFile, LogEntry
from app.db.session import get_session
from app.schemas.ingest import DateRange, UploadResponse
from app.services.ingest_service import index_log_entries_for_search
from app.utils.parsers import parse_csv_bytes, parse_txt_bytes

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_LOG_PATH = BACKEND_ROOT / "tmp" / "sample_logs_100.csv"

router = APIRouter()


def _parse_file(filename: str, content: bytes):
    filename = (filename or "").lower()
    if filename.endswith(".csv"):
        return parse_csv_bytes(content)
    if filename.endswith(".txt"):
        return parse_txt_bytes(content)
    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Only .csv and .txt are supported.",
    )


async def _persist_logs(
    *,
    parsed_logs: list,
    original_filename: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> UploadResponse:
    if not parsed_logs:
        raise HTTPException(
            status_code=400,
            detail="No valid log entries were found after parsing.",
        )

    file_id = f"file_{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().replace(microsecond=0)

    ingested_file = IngestedFile(
        file_id=file_id,
        filename=original_filename,
        created_at=now,
        entries_parsed=len(parsed_logs),
    )
    session.add(ingested_file)

    result = await session.execute(select(func.count()).select_from(LogEntry))
    offset = int(result.scalar() or 0)

    log_rows: list[LogEntry] = []
    for i, entry in enumerate(parsed_logs, start=1):
        log_rows.append(
            LogEntry(
                log_id=f"log_{offset + i:06d}",
                file_id=file_id,
                timestamp=entry.timestamp,
                source=entry.source,
                severity=entry.severity,
                message=entry.message,
            )
        )

    session.add_all(log_rows)
    await session.commit()

    try:
        background_tasks.add_task(
            index_log_entries_for_search,
            log_ids=[r.log_id for r in log_rows],
            sources=[r.source for r in log_rows],
            severities=[r.severity for r in log_rows],
            messages=[r.message for r in log_rows],
        )
    except Exception as e:
        logger.exception("Indexing failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Indexing failed; logs were ingested but search index was not updated.",
        )

    timestamps = [r.timestamp for r in log_rows]
    severities = [r.severity for r in log_rows]

    date_range = DateRange(
        earliest=min(timestamps).isoformat() + "Z",
        latest=max(timestamps).isoformat() + "Z",
    )
    severity_breakdown = dict(Counter(severities))

    return UploadResponse(
        status="success",
        file_id=file_id,
        entries_parsed=len(log_rows),
        date_range=date_range,
        severity_breakdown=severity_breakdown,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_logs(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload and ingest a log file (CSV or TXT).
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        parsed_logs = _parse_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _persist_logs(
        parsed_logs=parsed_logs,
        original_filename=file.filename,
        session=session,
        background_tasks=background_tasks,
    )


@router.post("/upload/sample", response_model=UploadResponse)
async def upload_sample_logs(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Ingest the bundled sample log file so users can explore the app immediately.
    """

    if not SAMPLE_LOG_PATH.exists():
        logger.error("Sample log file not found at %s", SAMPLE_LOG_PATH)
        raise HTTPException(
            status_code=500,
            detail="Sample log file is missing on the server.",
        )

    content = SAMPLE_LOG_PATH.read_bytes()
    try:
        parsed_logs = _parse_file(SAMPLE_LOG_PATH.name, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await _persist_logs(
        parsed_logs=parsed_logs,
        original_filename=SAMPLE_LOG_PATH.name,
        session=session,
        background_tasks=background_tasks,
    )
