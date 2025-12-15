# app/schemas/logs.py
"""
Schemas for GET /logs.

Matches the response contract provided in the project specs.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class LogItem(BaseModel):
    """A single log record for browsing."""
    log_id: str = Field(..., description="Log identifier (e.g., log_047)")
    timestamp: str = Field(..., description="ISO8601 UTC timestamp")
    source: str = Field(..., description="Log source (e.g., UNIT-007)")
    severity: str = Field(..., description="Severity label")
    message: str = Field(..., description="Raw log message")


class LogsResponse(BaseModel):
    """
    Response for browsing logs with filters.

    Example:
    {
      "logs": [...],
      "total": 5,
      "filters_applied": {"severity": "CRITICAL", "source": "UNIT-007"}
    }
    """
    logs: List[LogItem] = Field(default_factory=list, description="Log entries")
    total: int = Field(..., ge=0, description="Total matching entries before pagination")
    filters_applied: Dict[str, str] = Field(
        default_factory=dict,
        description="Echo of applied filters (for UI clarity)",
    )
