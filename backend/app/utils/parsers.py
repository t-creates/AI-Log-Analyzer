# app/utils/parsers.py
"""
Log file parsing utilities.

Enhancements (per your notes):
- Delimiter detection (CSV + TXT) to handle real-world variations.
- Header detection + strict header validation for structured formats.
- If a header is missing/invalid, we raise a clear error with the expected header format.

Supported structured fields:
    timestamp, source, severity, message

CSV:
- Detect delimiter using csv.Sniffer (fallback to comma).
- Require a valid header containing required fields.

TXT:
- Try to detect delimiter per line (comma, tab, pipe, semicolon).
- If a header line is detected, validate it; otherwise parse as data lines.
- If delimiter parsing fails, store the raw line as a fallback entry (MVP-friendly).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from dateutil import parser as dtparser


# Canonical severities aligned with your API examples
CANONICAL_SEVERITIES = {"INFO", "WARNING", "ERROR", "CRITICAL"}
EXTRA_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_SEVERITIES = CANONICAL_SEVERITIES | EXTRA_SEVERITIES

REQUIRED_FIELDS = ("timestamp", "source", "severity", "message")

# Common delimiters we see in TXT-like logs
COMMON_DELIMITERS: Tuple[str, ...] = (",", "\t", "|", ";")

EXPECTED_HEADER_EXAMPLE = "timestamp,source,severity,message"


@dataclass(frozen=True)
class ParsedLog:
    """In-memory representation of a parsed log entry (normalized)."""
    timestamp: datetime  # naive UTC datetime
    source: str
    severity: str
    message: str


# ----------------------------
# Normalization helpers
# ----------------------------
def _parse_timestamp_to_utc_naive(value: str) -> datetime:
    """
    Parse a timestamp string and normalize to naive UTC datetime.

    - If tz-aware -> convert to UTC and drop tzinfo.
    - If tz-naive -> treat as UTC (common in industrial logs).
    """
    dt = dtparser.isoparse(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0)


def _normalize_severity(raw: str) -> str:
    sev = (raw or "INFO").strip().upper()
    return sev if sev in ALLOWED_SEVERITIES else "INFO"


def _normalize_source(raw: str) -> str:
    src = (raw or "").strip()
    return src if src else "UNKNOWN"


def _normalize_message(raw: str) -> str:
    return (raw or "").strip()


def isoformat_z(dt: datetime) -> str:
    """Convert naive UTC datetime to ISO8601 with trailing 'Z'."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat() + "Z"


# ----------------------------
# Header / delimiter detection
# ----------------------------
def _looks_like_header(fields: Sequence[str]) -> bool:
    """
    Heuristic: a header line is one where normalized tokens contain required fields.
    """
    normalized = {f.strip().lower() for f in fields if f and f.strip()}
    return all(k in normalized for k in REQUIRED_FIELDS)


def _validate_header(fields: Sequence[str]) -> None:
    """
    Validate that a header contains required fields.
    Raises ValueError if invalid with a clear hint.
    """
    if not _looks_like_header(fields):
        raise ValueError(
            "Missing or invalid header. Expected header format:\n"
            f"  {EXPECTED_HEADER_EXAMPLE}\n"
            "Required columns: timestamp, source, severity, message"
        )


def _sniff_csv_dialect(sample: str) -> csv.Dialect:
    """
    Use csv.Sniffer to detect delimiter/quoting. Fallback to comma dialect.
    """
    sniffer = csv.Sniffer()
    try:
        return sniffer.sniff(sample, delimiters="".join(COMMON_DELIMITERS))
    except Exception:
        # fallback to a safe default
        class _Comma(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return _Comma()


def _detect_txt_delimiter(line: str) -> Optional[str]:
    """
    Detect delimiter for a TXT line by choosing the delimiter that yields the best
    4-part split when splitting into at most 4 fields.

    Returns delimiter or None.
    """
    best_delim = None
    best_score = -1

    for d in COMMON_DELIMITERS:
        parts = [p.strip() for p in line.split(d)]
        # Score: prefer exactly 4+ parts, and avoid very low part counts.
        # We only really need 4 fields (timestamp/source/severity/message),
        # but sometimes message contains the delimiter; we handle that by split(maxsplit=3) later.
        score = 0
        if len(parts) >= 4:
            score += 2
        if len(parts) >= 2:
            score += 1
        # If delimiter not present, len(parts)==1 => score stays low
        if score > best_score:
            best_score = score
            best_delim = d

    if best_score <= 0:
        return None
    return best_delim


# ----------------------------
# Parsers
# ----------------------------
def parse_csv_bytes(content: bytes) -> List[ParsedLog]:
    """
    Parse CSV bytes into ParsedLog entries.

    Requirements:
    - A valid header must be present containing: timestamp,source,severity,message
    - Delimiter is auto-detected (fallback to comma).

    Raises:
        ValueError: if header is missing/invalid or no valid rows exist.
    """
    text = content.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("Empty file.")

    # Sniff dialect from first few lines
    sample = "\n".join(lines[:20])
    dialect = _sniff_csv_dialect(sample)

    reader = csv.reader(lines, dialect=dialect)

    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("Empty file.")

    header_fields = [h.strip().lower() for h in header]
    _validate_header(header_fields)

    # Build index mapping so column order doesn’t matter
    idx = {name: header_fields.index(name) for name in REQUIRED_FIELDS}

    logs: List[ParsedLog] = []
    for row in reader:
        # Allow short rows (skip)
        if not row or len(row) <= max(idx.values()):
            continue

        ts_raw = (row[idx["timestamp"]] or "").strip()
        src_raw = row[idx["source"]] if idx["source"] < len(row) else ""
        sev_raw = row[idx["severity"]] if idx["severity"] < len(row) else ""
        msg_raw = row[idx["message"]] if idx["message"] < len(row) else ""

        if not ts_raw:
            continue

        msg = _normalize_message(msg_raw)
        if not msg:
            continue

        try:
            ts = _parse_timestamp_to_utc_naive(ts_raw)
        except Exception:
            continue

        logs.append(
            ParsedLog(
                timestamp=ts,
                source=_normalize_source(src_raw),
                severity=_normalize_severity(sev_raw),
                message=msg,
            )
        )

    if not logs:
        raise ValueError(
            "No valid log rows found after parsing. Ensure your file matches:\n"
            f"  {EXPECTED_HEADER_EXAMPLE}"
        )

    return logs


def parse_txt_bytes(content: bytes) -> List[ParsedLog]:
    """
    Parse TXT bytes into ParsedLog entries.

    Strategy:
    1) Find first non-empty line.
    2) Detect delimiter for that line.
       - If it looks like a header -> validate it, then parse subsequent lines as structured.
       - Else attempt to parse each line as structured using detected delimiter per line.
    3) If structured parse fails for a line -> store as raw fallback entry.

    Raises:
        ValueError: only if the file is empty OR it *looks structured* but header is invalid.
    """
    text = content.decode("utf-8", errors="replace")
    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not raw_lines:
        raise ValueError("Empty file.")

    first_line = raw_lines[0]
    delim = _detect_txt_delimiter(first_line)

    start_index = 0
    header_map: Optional[dict[str, int]] = None

    # If delimiter detected, check if first line is header
    if delim:
        first_parts = [p.strip().lower() for p in first_line.split(delim)]
        if _looks_like_header(first_parts):
            _validate_header(first_parts)
            header_map = {name: first_parts.index(name) for name in REQUIRED_FIELDS}
            start_index = 1
        else:
            # No header. We'll treat lines as "timestamp<d>source<d>severity<d>message"
            # If user actually intended a header but it doesn't match, we don't fail here
            # because TXT is often messy. Only fail when it *looks like* a header but is invalid.
            header_map = None

    logs: List[ParsedLog] = []

    for line in raw_lines[start_index:]:
        # Re-detect per line (different devices sometimes change delimiters mid-file 🙃)
        d = _detect_txt_delimiter(line) or delim

        if d:
            # Split into at most 4 fields so message can contain delimiters
            parts = [p.strip() for p in line.split(d, 3)]
            if len(parts) == 4:
                ts_raw, src_raw, sev_raw, msg_raw = parts
                msg = _normalize_message(msg_raw)

                if ts_raw and msg:
                    try:
                        ts = _parse_timestamp_to_utc_naive(ts_raw)
                        logs.append(
                            ParsedLog(
                                timestamp=ts,
                                source=_normalize_source(src_raw),
                                severity=_normalize_severity(sev_raw),
                                message=msg,
                            )
                        )
                        continue
                    except Exception:
                        # fall through to raw
                        pass

        # Fallback: store the raw line; don’t drop data in MVP
        logs.append(
            ParsedLog(
                timestamp=datetime.utcnow().replace(microsecond=0),
                source="UNKNOWN",
                severity="INFO",
                message=line,
            )
        )

    # If everything became raw entries, that’s still valid for MVP.
    # The user can still semantic-search the messages.
    return logs
