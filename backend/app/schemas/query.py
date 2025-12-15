# app/schemas/query.py
"""
Schemas for POST /query.

Matches the request/response contract provided in the project specs.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Natural language question for semantic search / RAG."""
    question: str = Field(..., min_length=1, description="User question in natural language")


class RelevantLog(BaseModel):
    """A single relevant log result returned by semantic search."""
    log_id: str = Field(..., description="Log identifier (e.g., log_047)")
    timestamp: str = Field(..., description="ISO8601 UTC timestamp for this log entry")
    source: str = Field(..., description="Log source (e.g., UNIT-007)")
    severity: str = Field(..., description="Severity label (e.g., CRITICAL)")
    message: str = Field(..., description="Raw log message")
    relevance_score: float = Field(..., ge=-1.0, le=1.0, description="Similarity score (cosine/IP)")


class QueryResponse(BaseModel):
    """
    Response for a natural language query.

    Example:
    {
      "answer": "...",
      "relevant_logs": [...],
      "suggested_followup": "..."
    }
    """
    answer: str = Field(..., description="Direct answer grounded in retrieved log entries")
    relevant_logs: List[RelevantLog] = Field(default_factory=list, description="Top relevant log entries")
    suggested_followup: str = Field(..., description="Operational next step suggestion")
