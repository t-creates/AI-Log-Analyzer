# app/api/routes/summary.py
"""
GET /summary

Dashboard summary + pattern analysis.

This endpoint is designed to be:
- Deterministic and reliable by default (always returns something useful)
- Optionally enhanced by Gemini when configured (better wording + root-cause hints)

Gemini integration strategy (MVP-safe):
- We generate a deterministic draft (incidents, patterns, actions).
- If Gemini is enabled, we ask it to *refine* the draft and return strict JSON.
- If JSON parsing fails (LLM being an LLM), we fall back to the deterministic draft.
"""

from __future__ import annotations

import json
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
from app.services.gemini_service import generate_text, gemini_enabled

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
    """Internal representation of an incident cluster."""
    title: str
    severity: str
    timestamp: datetime
    related_entries: int
    root_cause_hint: str


def _iso_z(dt: datetime) -> str:
    """Convert naive UTC datetime to ISO with trailing Z."""
    return dt.replace(microsecond=0).isoformat() + "Z"


def _match_keyword_bucket(message: str) -> str | None:
    """Return the first keyword bucket that matches the message (case-insensitive)."""
    m = (message or "").lower()
    for bucket, tokens in KEYWORDS.items():
        if any(t in m for t in tokens):
            return bucket
    return None


def _root_cause_hint(bucket: str | None) -> str:
    """Root cause hint based on bucket (deterministic baseline)."""
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


def _build_deterministic_summary(window: List[LogEntry]) -> tuple[list[TopIncident], list[str], list[str]]:
    """Build deterministic incidents/patterns/actions."""
    total = len(window)
    sev_counts = Counter((r.severity or "INFO").upper() for r in window)
    source_counts = Counter(r.source or "UNKNOWN" for r in window)

    # Clusters by (source, severity)
    by_source_sev: Dict[Tuple[str, str], List[LogEntry]] = defaultdict(list)
    for r in window:
        by_source_sev[(r.source or "UNKNOWN", (r.severity or "INFO").upper())].append(r)

    # Clusters by (bucket, source)
    by_bucket_source: Dict[Tuple[str, str], List[LogEntry]] = defaultdict(list)
    for r in window:
        bucket = _match_keyword_bucket(r.message)
        if bucket:
            by_bucket_source[(bucket, r.source or "UNKNOWN")].append(r)

    clusters: List[_Cluster] = []

    for (source, sev), items in by_source_sev.items():
        if len(items) < 2 and _severity_rank(sev) < 3:
            continue
        ts0 = min(i.timestamp for i in items)
        bucket = None
        for i in items[:10]:
            bucket = _match_keyword_bucket(i.message) or bucket

        clusters.append(
            _Cluster(
                title=f"{sev.title()} events on {source}",
                severity=sev,
                timestamp=ts0,
                related_entries=len(items),
                root_cause_hint=_root_cause_hint(bucket),
            )
        )

    for (bucket, source), items in by_bucket_source.items():
        if len(items) < 2:
            continue
        sev = max(((i.severity or "INFO").upper() for i in items), key=_severity_rank)
        ts0 = min(i.timestamp for i in items)
        clusters.append(
            _Cluster(
                title=f"{bucket.title()} issues on {source}",
                severity=sev,
                timestamp=ts0,
                related_entries=len(items),
                root_cause_hint=_root_cause_hint(bucket),
            )
        )

    clusters_sorted = sorted(
        clusters,
        key=lambda c: (_severity_rank(c.severity), c.related_entries, c.timestamp),
        reverse=True,
    )[:3]

    top_incidents: List[TopIncident] = [
        TopIncident(
            incident=c.title,
            timestamp=_iso_z(c.timestamp),
            severity=c.severity,
            related_entries=c.related_entries,
            suspected_root_cause=c.root_cause_hint,
        )
        for c in clusters_sorted
    ]

    # Patterns
    patterns: List[str] = []
    if source_counts:
        top_sources = source_counts.most_common(3)
        patterns.append("Most activity concentrated in: " + ", ".join(f"{s} ({c})" for s, c in top_sources))

    night = [r for r in window if (r.timestamp.hour >= 22 or r.timestamp.hour < 6)]
    if total > 0 and (len(night) / total) >= 0.35:
        patterns.append("Alerts elevated during night shift (10PM–6AM)")

    bucket_counts = Counter(_match_keyword_bucket(r.message) for r in window)
    bucket_counts.pop(None, None)
    if bucket_counts:
        dominant = bucket_counts.most_common(2)
        patterns.append("Dominant issue types: " + ", ".join(f"{b} ({c})" for b, c in dominant))

    noisy_sources = []
    for src, _cnt in source_counts.items():
        severe_cnt = sum(
            1
            for r in window
            if (r.source or "UNKNOWN") == src and _severity_rank((r.severity or "INFO").upper()) >= 2
        )
        if severe_cnt >= 3:
            noisy_sources.append((src, severe_cnt))
    noisy_sources.sort(key=lambda x: x[1], reverse=True)
    if noisy_sources:
        src, cnt = noisy_sources[0]
        patterns.append(f"{src} shows repeated alert activity ({cnt} WARNING+ entries)")

    # Actions
    actions: List[str] = []
    if sev_counts.get("CRITICAL", 0) > 0:
        actions.append("Priority inspection for sources associated with CRITICAL events")
    if sev_counts.get("ERROR", 0) > 0:
        actions.append("Review ERROR events for repeat causes and correlate with maintenance history")

    if bucket_counts.get("pressure", 0) > 0:
        actions.append("Inspect pressure regulation components (valves/regulators) for affected units")
    if bucket_counts.get("temperature", 0) > 0:
        actions.append("Review cooling system performance and maintenance schedule for affected units")
    if bucket_counts.get("sensor", 0) > 0:
        actions.append("Calibrate sensors on units with frequent fluctuation or calibration messages")

    # Deduplicate while preserving order
    actions = list(dict.fromkeys(actions))[:5]

    return top_incidents, patterns[:5], actions


async def _maybe_refine_with_gemini(
    *,
    question_period: str,
    total_entries: int,
    top_incidents: list[TopIncident],
    patterns: list[str],
    actions: list[str],
    sample_logs: list[LogEntry],
) -> tuple[list[TopIncident], list[str], list[str]]:
    """
    Ask Gemini to refine wording/insights and return strict JSON.
    Falls back to the provided deterministic content if anything goes wrong.
    """
    if not gemini_enabled():
        return top_incidents, patterns, actions

    # Provide a small sample of logs so Gemini has real evidence to phrase around.
    # Keep short to control cost and latency.
    sample = "\n".join(
        f"- {r.timestamp.isoformat()}Z {r.source} {r.severity}: {r.message}"
        for r in sample_logs[:40]
    )

    draft = {
        "top_incidents": [ti.model_dump() for ti in top_incidents],
        "patterns_detected": patterns,
        "recommended_actions": actions,
    }

    prompt = (
        "You are generating a dashboard summary of industrial equipment logs.\n"
        "Refine the provided draft to be more specific and operational.\n"
        "Rules:\n"
        "- Use only the evidence in the log sample.\n"
        "- Do not invent units, counts, or timestamps.\n"
        "- Keep it concise.\n"
        "- Return STRICT JSON only (no markdown, no extra text).\n\n"
        f"Period: {question_period}\n"
        f"Total entries: {total_entries}\n\n"
        f"Log sample:\n{sample}\n\n"
        f"Draft JSON to refine:\n{json.dumps(draft)}\n\n"
        "Return JSON with exactly these keys:\n"
        "{\n"
        '  "top_incidents": [\n'
        '    {"incident": str, "timestamp": str, "severity": str, "related_entries": int, "suspected_root_cause": str}\n'
        "  ],\n"
        '  "patterns_detected": [str],\n'
        '  "recommended_actions": [str]\n'
        "}\n"
    )

    try:
        text = await generate_text(prompt, timeout_s=25.0)
        if not text:
            return top_incidents, patterns, actions

        refined = json.loads(text)

        # Minimal validation (avoid hard failures from minor LLM hiccups)
        ti_raw = refined.get("top_incidents", [])
        pd_raw = refined.get("patterns_detected", [])
        ra_raw = refined.get("recommended_actions", [])

        refined_top = []
        for item in ti_raw[:3]:
            # Ensure required keys exist; skip malformed entries
            if not all(k in item for k in ("incident", "timestamp", "severity", "related_entries", "suspected_root_cause")):
                continue
            refined_top.append(TopIncident(**item))

        refined_patterns = [str(x) for x in pd_raw[:5] if str(x).strip()]
        refined_actions = [str(x) for x in ra_raw[:5] if str(x).strip()]

        # If Gemini returns unusable output, keep deterministic baseline
        if not refined_top:
            refined_top = top_incidents
        if not refined_patterns:
            refined_patterns = patterns
        if not refined_actions:
            refined_actions = actions

        return refined_top, refined_patterns, refined_actions

    except Exception:
        return top_incidents, patterns, actions


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(session: AsyncSession = Depends(get_session)):
    """
    Generate summary for the last 7 days relative to newest timestamp in DB.
    """
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

    top_incidents, patterns, actions = _build_deterministic_summary(window)

    # Gemini refinement (optional, safe fallback)
    top_incidents, patterns, actions = await _maybe_refine_with_gemini(
        question_period="Last 7 days",
        total_entries=total,
        top_incidents=top_incidents,
        patterns=patterns,
        actions=actions,
        sample_logs=window[:200],  # sample source; function trims to 40
    )

    return SummaryResponse(
        summary_generated_at=_iso_z(now),
        period="Last 7 days",
        total_entries=total,
        top_incidents=top_incidents,
        patterns_detected=patterns,
        recommended_actions=actions,
    )
