# app/api/routes/logs.py
"""
GET /logs

Browse and filter ingested log entries.

Supported filters:
- severity
- source
- pagination (limit + offset)

This endpoint is intentionally simple and fast:
- No semantic search
- No AI calls
- Safe for dashboards and tables
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LogEntry
from app.db.session import get_session
from app.schemas.logs import LogItem, LogsResponse

router = APIRouter()


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    limit: int = Query(default=20, ge=1, le=200, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
):
    """
    Retrieve log entries with optional filters.

    Example:
      /logs?severity=CRITICAL&source=UNIT-007&limit=20
    """

    stmt = select(LogEntry)
    count_stmt = select(func.count()).select_from(LogEntry)

    filters_applied: Dict[str, str] = {}

    if severity:
        stmt = stmt.where(LogEntry.severity == severity)
        count_stmt = count_stmt.where(LogEntry.severity == severity)
        filters_applied["severity"] = severity

    if source:
        stmt = stmt.where(LogEntry.source == source)
        count_stmt = count_stmt.where(LogEntry.source == source)
        filters_applied["source"] = source

    # Total count before pagination
    total = int((await session.execute(count_stmt)).scalar() or 0)

    # Apply pagination and ordering (newest first)
    rows = (
        await session.execute(
            stmt.order_by(LogEntry.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    logs: List[LogItem] = [
        LogItem(
            log_id=row.log_id,
            timestamp=row.timestamp.isoformat() + "Z",
            source=row.source,
            severity=row.severity,
            message=row.message,
        )
        for row in rows
    ]

    return LogsResponse(
        logs=logs,
        total=total,
        filters_applied=filters_applied,
    )
