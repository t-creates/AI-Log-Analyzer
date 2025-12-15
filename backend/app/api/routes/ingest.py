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
logger = logging.getLogger(__name__)

import uuid
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.db.models import IngestedFile, LogEntry
from app.db.session import get_session
from app.schemas.ingest import DateRange, UploadResponse
from app.services.ingest_service import index_log_entries_for_search
from app.utils.parsers import parse_csv_bytes, parse_txt_bytes

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_logs(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload and ingest a log file (CSV or TXT).

    Returns:
    - file_id
    - number of parsed entries
    - date range
    - severity breakdown
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    filename = file.filename.lower()
    if not (filename.endswith(".csv") or filename.endswith(".txt")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only .csv and .txt are supported.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # -----------------------
    # Parse file
    # -----------------------
    try:
        if filename.endswith(".csv"):
            parsed_logs = parse_csv_bytes(content)
        else:
            parsed_logs = parse_txt_bytes(content)
    except ValueError as e:
        # Parser-level validation errors (header missing, empty, etc.)
        raise HTTPException(status_code=400, detail=str(e))

    if not parsed_logs:
        raise HTTPException(
            status_code=400,
            detail="No valid log entries were found after parsing.",
        )

    # -----------------------
    # Persist metadata
    # -----------------------
    file_id = f"file_{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().replace(microsecond=0)

    ingested_file = IngestedFile(
        file_id=file_id,
        filename=file.filename,
        created_at=now,
        entries_parsed=len(parsed_logs),
    )
    session.add(ingested_file)

    # Determine log_id offset so IDs stay sequential & readable
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

    # -----------------------
    # Semantic indexing (embeddings + FAISS)
    # -----------------------
    try:
    # 🔥 Move indexing to background
        background_tasks.add_task(
            index_log_entries_for_search,
            log_ids=[r.log_id for r in log_rows],
            sources=[r.source for r in log_rows],
            severities=[r.severity for r in log_rows],
            messages=[r.message for r in log_rows],
        )
    except Exception as e:
        logger.exception("Indexing failed: %s", e)
        raise HTTPException(status_code=500, detail="Indexing failed; logs were ingested but search index was not updated.")


    # -----------------------
    # Build response stats
    # -----------------------
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
