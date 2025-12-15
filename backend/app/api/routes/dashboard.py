# app/api/routes/dashboard.py
"""
GET /dashboard

Dashboard-oriented data for charts and graphs.

Returns:
- severity_breakdown: pie/bar chart
- top_sources: bar chart
- severity_timeseries: stacked area/bar chart
- recent_incidents: cards list

MVP design:
- Uses newest timestamp in DB to define the window ("Last N days")
  so historical sample uploads still show meaningful time windows.
- Purely deterministic; fast and reliable.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LogEntry
from app.db.session import get_session
from app.schemas.dashboard import (
    DashboardResponse,
    RecentIncident,
    SeveritySeries,
    SourceCount,
    TimeBucket,
)

router = APIRouter()

CANONICAL_SEVERITIES = ["CRITICAL", "ERROR", "WARNING", "INFO"]


def _iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _floor_to_bucket(dt: datetime, bucket_minutes: int) -> datetime:
    """Floor dt to the start of its bucket."""
    minute = (dt.minute // bucket_minutes) * bucket_minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


@dataclass(frozen=True)
class _IncidentKey:
    source: str
    severity: str


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    days: int = Query(default=7, ge=1, le=30, description="Window size in days"),
    bucket_minutes: int = Query(default=60, ge=15, le=1440, description="Time bucket size in minutes"),
    top_sources_limit: int = Query(default=10, ge=3, le=50, description="How many sources to return"),
    session: AsyncSession = Depends(get_session),
):
    # Pull a capped set (MVP). Later we can do a proper time-bounded DB query.
    rows = (
        await session.execute(
            select(LogEntry).order_by(LogEntry.timestamp.desc()).limit(20000)
        )
    ).scalars().all()

    now = datetime.utcnow().replace(microsecond=0)

    if not rows:
        return DashboardResponse(
            generated_at=_iso_z(now),
            period=f"Last {days} days",
            total_entries=0,
            severity_breakdown={},
            top_sources=[],
            severity_timeseries=[],
            recent_incidents=[],
        )

    newest_ts = rows[0].timestamp
    cutoff = newest_ts - timedelta(days=days)
    window = [r for r in rows if r.timestamp >= cutoff]
    total = len(window)

    # -----------------------
    # Severity breakdown
    # -----------------------
    sev_counts = Counter((r.severity or "INFO").upper() for r in window)
    # Keep ordering stable for charts
    severity_breakdown = {sev: int(sev_counts.get(sev, 0)) for sev in CANONICAL_SEVERITIES}
    # Include any unknown severities at the end (won't break UI)
    for sev, cnt in sev_counts.items():
        if sev not in severity_breakdown:
            severity_breakdown[sev] = int(cnt)

    # -----------------------
    # Top sources
    # -----------------------
    src_counts = Counter(r.source or "UNKNOWN" for r in window)
    top_sources = [
        SourceCount(source=src, count=int(cnt))
        for src, cnt in src_counts.most_common(top_sources_limit)
    ]

    # -----------------------
    # Severity time series
    # -----------------------
    # buckets[(severity)][bucket_start] = count
    buckets = defaultdict(lambda: defaultdict(int))
    bucket_starts = set()

    for r in window:
        sev = (r.severity or "INFO").upper()
        b = _floor_to_bucket(r.timestamp, bucket_minutes)
        buckets[sev][b] += 1
        bucket_starts.add(b)

    # Ensure continuous time axis for frontend charts
    if bucket_starts:
        start = min(bucket_starts)
        end = max(bucket_starts)
        axis = []
        cur = start
        step = timedelta(minutes=bucket_minutes)
        while cur <= end:
            axis.append(cur)
            cur += step
    else:
        axis = []

    severity_timeseries = []
    all_severities = list(dict.fromkeys(CANONICAL_SEVERITIES + sorted(buckets.keys())))
    for sev in all_severities:
        series = [
            TimeBucket(bucket_start=_iso_z(b), count=int(buckets[sev].get(b, 0)))
            for b in axis
        ]
        # Only include series that has any data (keeps response small)
        if any(tb.count > 0 for tb in series):
            severity_timeseries.append(SeveritySeries(severity=sev, buckets=series))

    # -----------------------
    # Recent incidents (cards)
    # -----------------------
    # MVP incident definition:
    # - group by (source, severity)
    # - show recent clusters, largest first
    clusters = defaultdict(list)
    for r in window:
        key = _IncidentKey(source=(r.source or "UNKNOWN"), severity=(r.severity or "INFO").upper())
        clusters[key].append(r)

    # rank: severity rank then related_entries then recency
    def sev_rank(s: str) -> int:
        return {"CRITICAL": 4, "ERROR": 3, "WARNING": 2, "INFO": 1}.get(s, 0)

    incident_cards = []
    for key, items in clusters.items():
        first_seen = min(i.timestamp for i in items)
        last_seen = max(i.timestamp for i in items)
        incident_cards.append(
            RecentIncident(
                title=f"{key.severity.title()} events on {key.source}",
                severity=key.severity,
                first_seen=_iso_z(first_seen),
                last_seen=_iso_z(last_seen),
                related_entries=len(items),
                sources=[key.source],
            )
        )

    incident_cards.sort(
        key=lambda x: (sev_rank(x.severity), x.related_entries, x.last_seen),
        reverse=True,
    )
    recent_incidents = incident_cards[:8]

    return DashboardResponse(
        generated_at=_iso_z(now),
        period=f"Last {days} days",
        total_entries=total,
        severity_breakdown=severity_breakdown,
        top_sources=top_sources,
        severity_timeseries=severity_timeseries,
        recent_incidents=recent_incidents,
    )
