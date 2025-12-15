# app/services/ingest_service.py
"""
Ingestion-side orchestration (DB -> embeddings -> FAISS).

Why a service?
- Keeps the /upload route thin (KISS)
- Makes indexing reusable (rebuild index, batch jobs, etc.)
- Easier to test independently

Flow:
1) Build canonical text for each log entry
2) Generate embeddings (sentence-transformers)
3) Add embeddings to FAISS and persist index + id map
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

from app.services.embed_service import embed_texts
from app.services.faiss_service import add_embeddings, persist


def _to_embedding_text(source: str, severity: str, message: str) -> str:
    """
    Canonical representation used for embeddings.

    Keep it stable over time so:
    - search results remain consistent
    - future re-indexing produces comparable vectors
    """
    return f"[{severity}] {source}: {message}"


def index_log_entries_for_search(
    *,
    log_ids: Sequence[str],
    sources: Sequence[str],
    severities: Sequence[str],
    messages: Sequence[str],
) -> None:
    """
    Embed and index a batch of log entries.

    Args:
        log_ids: list of LogEntry.log_id values (stable public ids)
        sources/severities/messages: aligned lists in the same order
    """
    if not log_ids:
        return

    texts = [
        _to_embedding_text(src, sev, msg)
        for src, sev, msg in zip(sources, severities, messages)
    ]

    embeddings = embed_texts(texts)
    add_embeddings(list(log_ids), embeddings)
    persist()
