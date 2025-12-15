# app/schemas/ingest.py
"""
Schemas for POST /upload.

Matches the response contract provided in the project specs.
"""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    """Date range covered by the ingested file."""
    earliest: str = Field(..., description="ISO8601 UTC timestamp (earliest log entry)")
    latest: str = Field(..., description="ISO8601 UTC timestamp (latest log entry)")


class UploadResponse(BaseModel):
    """
    Response returned after successful ingestion.

    Example:
    {
      "status": "success",
      "file_id": "file_001",
      "entries_parsed": 150,
      "date_range": {"earliest": "...Z", "latest": "...Z"},
      "severity_breakdown": {"INFO": 95, "WARNING": 35, "ERROR": 15, "CRITICAL": 5}
    }
    """
    status: str = Field(..., description="Status string, typically 'success'")
    file_id: str = Field(..., description="Identifier for the uploaded file (e.g., file_001)")
    entries_parsed: int = Field(..., ge=0, description="Number of log entries parsed and stored")
    date_range: DateRange = Field(..., description="Date range of entries in the file")
    severity_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts of entries by severity",
    )
