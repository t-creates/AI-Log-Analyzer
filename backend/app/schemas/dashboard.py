# app/schemas/dashboard.py
"""
Dashboard response schemas.

These models define the stable contract for chart and graph data consumed by the frontend.
Keep changes here intentional and versioned, because the UI will strongly depend on them.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field


class TimeBucket(BaseModel):
    """
    A single time bucket for time-series charts.

    Example:
      {"bucket_start": "2024-01-12T14:00:00Z", "count": 7}
    """
    bucket_start: str = Field(..., description="ISO8601 UTC timestamp representing the start of the bucket")
    count: int = Field(..., ge=0, description="Number of log entries in this bucket")


class SeveritySeries(BaseModel):
    """
    A series of time buckets for a specific severity level.

    Example:
      {"severity": "WARNING", "buckets": [ ... ]}
    """
    severity: str = Field(..., description="Severity name (e.g., INFO, WARNING, ERROR, CRITICAL)")
    buckets: List[TimeBucket] = Field(default_factory=list, description="Ordered time buckets for this severity")


class SourceCount(BaseModel):
    """
    Count of log entries by source (for bar charts / ranking lists).

    Example:
      {"source": "UNIT-007", "count": 42}
    """
    source: str = Field(..., description="Log source identifier (e.g., UNIT-007)")
    count: int = Field(..., ge=0, description="Number of log entries for this source")


class RecentIncident(BaseModel):
    """
    A small "incident card" summary (for dashboard cards).

    MVP incident definition is flexible. For now we typically group by (source, severity)
    and show counts + window.
    """
    title: str = Field(..., description="Human-readable incident title for a dashboard card")
    severity: str = Field(..., description="Incident severity label")
    first_seen: str = Field(..., description="ISO8601 UTC timestamp when the incident first appeared in the window")
    last_seen: str = Field(..., description="ISO8601 UTC timestamp when the incident last appeared in the window")
    related_entries: int = Field(..., ge=0, description="Number of related log entries")
    sources: List[str] = Field(default_factory=list, description="Sources involved in the incident")


class DashboardResponse(BaseModel):
    """
    Primary dashboard endpoint response.

    Includes:
    - severity breakdown for pie/bar charts
    - top sources for bar charts
    - severity time series for stacked charts
    - incident cards for quick summary widgets
    """
    generated_at: str = Field(..., description="ISO8601 UTC timestamp when this dashboard payload was generated")
    period: str = Field(..., description="Human-readable period label (e.g., 'Last 7 days')")
    total_entries: int = Field(..., ge=0, description="Total number of log entries in the selected window")

    severity_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by severity (keys are severity labels, values are counts)",
    )
    top_sources: List[SourceCount] = Field(
        default_factory=list,
        description="Top sources by volume for the selected window",
    )
    severity_timeseries: List[SeveritySeries] = Field(
        default_factory=list,
        description="Time-series buckets per severity for charting",
    )
    recent_incidents: List[RecentIncident] = Field(
        default_factory=list,
        description="Incident-style dashboard cards for the selected window",
    )
