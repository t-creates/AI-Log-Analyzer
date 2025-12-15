# app/api/routes/summary.py
"""
GET /summary

Generates an incident-style summary and lightweight pattern analysis suitable
for a dashboard.

MVP approach:
- Purely deterministic analysis first (fast + reliable)
- Optional Gemini "polish" later (without making the endpoint fragile)

What we do:
- Define a "last 7 days" window based on the newest timestamp in the DB
  (more useful than wall-clock when historical sample logs are uploaded).
- Compute totals
- Identify "top incidents" using simple clustering heuristics:
  - by (source, severity) AND
  - keyword buckets (pressure/temp/valve/sensor)
- Detect simple patterns:
  - concentration by source
  - night shift ratio (10PM–6AM)
  - repeated issues by keyword
- Recommend actions based on severities + dominant keywords
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LogEntry
from app.db.session import get_session
from app.schemas.summary import SummaryResponse, TopIncident

router = APIRouter()

# Keywords used for MVP incident bucketing/pattern hints.
KEYWORDS = {
    "pressure": ("pressure", "psi", "valve", "drop", "fluctuat"),
    "temperature": ("temp", "temperature", "°c", "celsius", "overheat", "cool"),
    "sensor": ("sensor", "calibration", "calibrate", "reading"),
    "power": ("power", "voltage", "current", "amp", "outage"),
}


@dataclass(frozen=True)
class _Cluster:
    """
    Internal representation of an incident cluster.

    We keep this separate from API schemas to make clustering logic testable.
    """
    title: str
    severity: str
    timestamp: datetime
    related_entries: int
    root_cause_hint: str


def _iso_z(dt: datetime) -> str:
    """Convert naive UTC datetime to ISO with trailing Z."""
    return dt.replace(microsecond=0).isoformat() + "Z"


def _match_keyword_bucket(message: str) -> str | None:
    """
    Return the first keyword bucket that matches the message (case-insensitive),
    else None.
    """
    m = (message or "").lower()
    for bucket, tokens in KEYWORDS.items():
        if any(t in m for t in tokens):
            return bucket
    return None


def _root_cause_hint(bucket: str | None) -> str:
    """Human-friendly root cause hint based on bucket."""
    if bucket == "pressure":
        return "Possible valve malfunction, blockage, regulator instability, or upstream supply variance"
    if bucket == "temperature":
        return "Cooling system performance degradation, increased load, or environmental factors"
    if bucket == "sensor":
        return "Sensor calibration drift, intermittent readings, or instrumentation issues"
    if bucket == "power":
        return "Power supply fluctuation, electrical subsystem fault, or upstream outage"
    return "Requires further investigation; correlate with maintenance and operational context"


def _severity_rank(sev: str) -> int:
    """Higher rank = more severe."""
    s = (sev or "").upper()
    return {"CRITICAL": 4, "ERROR": 3, "WARNING": 2, "INFO": 1, "LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(s, 0)


@router.get("/summar", response_model=SummaryResponse)
async def get_summary(session: AsyncSession = Depends(get_session)):
    """
    Dashboard summary for the "last 7 days" relative to newest ingested log timestamp.
    """
    # Pull a capped set (MVP). If your logs get huge, we'll switch to time-bounded query.
    rows = (
        await session.execute(
            select(LogEntry).order_by(LogEntry.timestamp.desc()).limit(10000)
        )
    ).scalars().all()

    now = datetime.utcnow().replace(microsecond=0)

    if not rows:
        return SummaryResponse(
            summary_generated_at=_iso_z(now),
            period="Last 7 days",
            total_entries=0,
            top_incidents=[],
            patterns_detected=[],
            recommended_actions=[],
        )

    newest_ts = rows[0].timestamp
    cutoff = newest_ts - timedelta(days=7)

    window = [r for r in rows if r.timestamp >= cutoff]
    total = len(window)

    # -----------------------
    # Basic counts
    # -----------------------
    sev_counts = Counter((r.severity or "INFO").upper() for r in window)
    source_counts = Counter(r.source or "UNKNOWN" for r in window)

    # -----------------------
    # Incident clustering (MVP)
    # -----------------------
    # Cluster 1: by (source, severity)
    by_source_sev: Dict[Tuple[str, str], List[LogEntry]] = defaultdict(list)
    for r in window:
        by_source_sev[(r.source or "UNKNOWN", (r.severity or "INFO").upper())].append(r)

    # Cluster 2: by keyword bucket (pressure/temp/sensor/power) optionally per source
    by_bucket_source: Dict[Tuple[str, str], List[LogEntry]] = defaultdict(list)
    for r in window:
        bucket = _match_keyword_bucket(r.message)
        if bucket:
            by_bucket_source[(bucket, r.source or "UNKNOWN")].append(r)

    clusters: List[_Cluster] = []

    # Convert (source,severity) clusters to incidents
    for (source, sev), items in by_source_sev.items():
        if len(items) < 2 and _severity_rank(sev) < 3:
            # Skip tiny low-severity clusters to reduce noise
            continue

        # pick "representative" timestamp: earliest occurrence in the window
        ts0 = min(i.timestamp for i in items)
        # infer bucket from messages
        bucket = None
        for i in items[:10]:
            bucket = _match_keyword_bucket(i.message) or bucket

        title = f"{sev.title()} events on {source}"
        clusters.append(
            _Cluster(
                title=title,
                severity=sev,
                timestamp=ts0,
                related_entries=len(items),
                root_cause_hint=_root_cause_hint(bucket),
            )
        )

    # Convert keyword clusters to incidents (helps produce meaningful labels)
    for (bucket, source), items in by_bucket_source.items():
        if len(items) < 2:
            continue
        sev = max((i.severity or "INFO").upper() for i in items)  # simple: choose max severity label
        ts0 = min(i.timestamp for i in items)
        title = f"{bucket.title()} issues on {source}"
        clusters.append(
            _Cluster(
                title=title,
                severity=sev,
                timestamp=ts0,
                related_entries=len(items),
                root_cause_hint=_root_cause_hint(bucket),
            )
        )

    # Rank clusters by:
    # 1) severity, 2) related entries, 3) recency-ish (more recent first if tie)
    clusters_sorted = sorted(
        clusters,
        key=lambda c: (_severity_rank(c.severity), c.related_entries, c.timestamp),
        reverse=True,
    )

    top3 = clusters_sorted[:3]

    top_incidents: List[TopIncident] = [
        TopIncident(
            incident=c.title,
            timestamp=_iso_z(c.timestamp),
            severity=c.severity,
            related_entries=c.related_entries,
            suspected_root_cause=c.root_cause_hint,
        )
        for c in top3
    ]

    # -----------------------
    # Pattern detection (MVP)
    # -----------------------
    patterns: List[str] = []

    if source_counts:
        top_sources = source_counts.most_common(3)
        patterns.append(
            "Most activity concentrated in: "
            + ", ".join(f"{src} ({cnt})" for src, cnt in top_sources)
        )

    # Night shift: 22:00–06:00
    night = [r for r in window if (r.timestamp.hour >= 22 or r.timestamp.hour < 6)]
    if total > 0:
        night_ratio = len(night) / total
        if night_ratio >= 0.35:
            patterns.append("Temperature/pressure alerts elevated during night shift (10PM–6AM)")

    # Keyword concentration
    bucket_counts = Counter(_match_keyword_bucket(r.message) for r in window)
    bucket_counts.pop(None, None)
    if bucket_counts:
        dominant = bucket_counts.most_common(2)
        patterns.append(
            "Dominant issue types: "
            + ", ".join(f"{b} ({c})" for b, c in dominant)
        )

    # Simple degradation hint: same source shows repeated higher severity in last few days
    # MVP heuristic: any source with >=3 WARNING/ERROR/CRITICAL entries
    noisy_sources = []
    for src, cnt in source_counts.items():
        severe_cnt = sum(
            1 for r in window
            if (r.source or "UNKNOWN") == src and _severity_rank((r.severity or "INFO").upper()) >= 2
        )
        if severe_cnt >= 3:
            noisy_sources.append((src, severe_cnt))

    noisy_sources.sort(key=lambda x: x[1], reverse=True)
    if noisy_sources:
        src, cnt = noisy_sources[0]
        patterns.append(f"{src} shows repeated alert activity ({cnt} WARNING+ entries)")

    # -----------------------
    # Recommended actions (MVP)
    # -----------------------
    actions: List[str] = []

    if sev_counts.get("CRITICAL", 0) > 0:
        actions.append("Priority inspection for sources associated with CRITICAL events")

    if sev_counts.get("ERROR", 0) > 0:
        actions.append("Review ERROR events for repeat causes and correlate with maintenance history")

    # Keyword-based actions
    if bucket_counts.get("pressure", 0) > 0:
        actions.append("Inspect pressure regulation components (valves/regulators) for affected units")
    if bucket_counts.get("temperature", 0) > 0:
        actions.append("Review cooling system performance and maintenance schedule for affected units")
    if bucket_counts.get("sensor", 0) > 0:
        actions.append("Calibrate sensors on units with frequent fluctuation or calibration messages")

    # Keep the list tidy (avoid 10 near-duplicates)
    actions = list(dict.fromkeys(actions))[:5]  # preserve order, dedupe, max 5

    return SummaryResponse(
        summary_generated_at=_iso_z(now),
        period="Last 7 days",
        total_entries=total,
        top_incidents=top_incidents,
        patterns_detected=patterns[:5],
        recommended_actions=actions,
    )
