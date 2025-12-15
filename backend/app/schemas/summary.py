# app/schemas/summary.py
"""
Schemas for GET /summary.

Matches the response contract provided in the project specs.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TopIncident(BaseModel):
    """An incident card returned in the summary response."""
    incident: str = Field(..., description="Incident title")
    timestamp: str = Field(..., description="ISO8601 UTC timestamp of representative incident event")
    severity: str = Field(..., description="Severity label")
    related_entries: int = Field(..., ge=0, description="Number of related log entries")
    suspected_root_cause: str = Field(..., description="Hypothesis of root cause (non-authoritative)")


class SummaryResponse(BaseModel):
    """
    Summary of incidents/patterns over the last 7 days.

    Example keys match the provided spec exactly.
    """
    summary_generated_at: str = Field(..., description="ISO8601 UTC timestamp when summary was generated")
    period: str = Field(..., description="Human-readable time window label (e.g., Last 7 days)")
    total_entries: int = Field(..., ge=0, description="Total log entries considered in the period")
    top_incidents: List[TopIncident] = Field(default_factory=list, description="Top incident list")
    patterns_detected: List[str] = Field(default_factory=list, description="Detected operational patterns")
    recommended_actions: List[str] = Field(default_factory=list, description="Recommended next actions")
