# app/core/config.py
"""
Central configuration for the AI Log Analyzer backend.

This module defines a single `settings` object (Pydantic BaseSettings) that reads
configuration from environment variables and a local `.env` file.

Guiding principles:
- DRY: config is declared once, imported everywhere.
- KISS: sensible defaults for local dev.
- Security: secrets live in env vars; `.env` is never committed.
"""

from __future__ import annotations

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and optional `.env`.

    `.env` location:
      - With our current repo layout, we run uvicorn from `backend/`,
        so `.env` should live in `backend/.env`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # deployment environments often add extra env vars
        case_sensitive=False,
    )

    # -----------------------
    # Runtime
    # -----------------------
    ENV: str = Field(default="dev", description="Environment: dev|test|prod")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (e.g., INFO, DEBUG)")

    # -----------------------
    # API / CORS
    # -----------------------
    # Default to common local dev ports (Vite/React 5173, CRA 3000).
    CORS_ALLOW_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000", "https://ai-log-analyzer-1-gzfi.onrender.com"],
        description="Allowed CORS origins for the frontend",
    )

    # -----------------------
    # Upload limits
    # -----------------------
    MAX_UPLOAD_MB: int = Field(
        default=25,
        ge=1,
        le=500,
        description="Max upload size in megabytes for log files",
    )

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        """
        Derived upload size limit in bytes.

        Using a property keeps the conversion logic centralized and consistent.
        """
        return int(self.MAX_UPLOAD_MB) * 1024 * 1024

    # -----------------------
    # Database
    # -----------------------
    # Async SQLAlchemy URL for SQLite (aiosqlite driver).
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/app.db",
        description="SQLAlchemy async database URL",
    )

    # -----------------------
    # Embeddings / FAISS
    # -----------------------
    EMBED_MODEL: str = Field(
        default="all-MiniLM-L4-v2",
        description="Sentence-Transformers model name/path",
    )
    FAISS_INDEX_PATH: str = Field(
        default="./data/faiss.index",
        description="Path to persisted FAISS index",
    )
    FAISS_IDMAP_PATH: str = Field(
        default="./data/faiss_idmap.json",
        description="Path to FAISS id mapping JSON (row_id -> log_id)",
    )

    # -----------------------
    # Gemini (Google AI Studio)
    # -----------------------
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description="Gemini API key (unset disables Gemini features)",
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name",
    )
    GEMINI_EMBED_MODEL: str = Field(
        default="models/text-embedding-004",
        description="Gemini model used for embeddings",
    )

    # -----------------------
    # Validators / normalizers
    # -----------------------
    @field_validator("ENV")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return (v or "dev").strip().lower()

    @field_validator("LOG_LEVEL")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        return (v or "INFO").strip().upper()

    @field_validator("CORS_ALLOW_ORIGINS")
    @classmethod
    def _clean_cors_origins(cls, v: List[str]) -> List[str]:
        # Strip whitespace and drop empty entries to avoid weird CORS behavior.
        cleaned = []
        for origin in v or []:
            o = (origin or "").strip()
            if o:
                cleaned.append(o)
        return cleaned

    @field_validator("DATABASE_URL", "FAISS_INDEX_PATH", "FAISS_IDMAP_PATH", "EMBED_MODEL", "GEMINI_MODEL", "GEMINI_EMBED_MODEL")
    @classmethod
    def _strip_strings(cls, v: str) -> str:
        # Defensive: eliminates accidental whitespace in env values.
        return (v or "").strip()


# Singleton instance imported across the codebase.
settings = Settings()
