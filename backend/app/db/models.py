# app/db/models.py
"""
SQLAlchemy ORM models for the AI Log Analyzer backend.

Design goals (MVP-first):
- Keep schema minimal but scalable.
- Store raw logs in SQLite for browsing/filtering.
- Keep ingestion metadata for files (helps summary dashboards & dedupe later).
- Use simple, explicit column types for SQLite compatibility.

Notes:
- Timestamps are stored as naive UTC datetimes (timezone-less) for SQLite simplicity.
  We convert to/from ISO 8601 with a trailing "Z" at the API boundary.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


class IngestedFile(Base):
    """
    Tracks each uploaded/ingested file.

    Why we store this:
    - Enables UI to show upload history and stats
    - Supports future dedupe (hashing) and re-index management
    """

    __tablename__ = "ingested_files"

    # Example: file_1a2b3c4d
    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True, nullable=False)

    # How many entries were parsed and written to DB for this file
    entries_parsed: Mapped[int] = mapped_column(Integer, nullable=False)


class LogEntry(Base):
    """
    A single log entry parsed from an uploaded file.

    Stored fields match the input structure:
        timestamp, source, severity, message

    We also store:
    - log_id: stable public identifier used in API responses (log_000123)
    - file_id: association back to the ingestion file
    """

    __tablename__ = "log_entries"

    # Example: log_000123
    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Which uploaded file this log came from (used for browsing & summaries)
    file_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Naive UTC datetime (timezone-less). Convert to/from ISO8601 "Z" in API.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True, nullable=False)

    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    # Log message content (may include long text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
