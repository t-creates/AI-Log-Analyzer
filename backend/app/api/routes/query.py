# app/api/routes/query.py
"""
POST /query

Implements:
- Natural language question -> embedding
- Semantic search via FAISS
- Fetch matching log rows from SQLite
- Generate an answer (Gemini if configured; otherwise a strong heuristic)
- Return response exactly matching the provided spec

Security / reliability notes:
- We never execute user input as code.
- We do not interpolate user input into SQL (SQLAlchemy parameterization).
- Gemini usage is optional; the endpoint works without it.
"""

from __future__ import annotations

from typing import Dict, List, Tuple
import re
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from app.db.models import LogEntry
from app.db.session import get_session
from app.schemas.query import QueryRequest, QueryResponse, RelevantLog
from app.services.embed_service import embed_texts_async
from app.services.faiss_service import search as faiss_search
from app.services.gemini_service import GeminiError, generate_text, gemini_enabled
from app.core.executors import faiss_executor

router = APIRouter()

from sqlalchemy import or_

async def _keyword_fallback_hits(
    session: AsyncSession,
    question: str,
    k: int = 20,
) -> List[Tuple[str, float]]:
    """
    Fallback retrieval when vector search is unavailable.

    Returns FAISS-shaped hits: [(log_id, score), ...]
    Score is a simple heuristic; higher = better.
    """
    q = (question or "").strip().lower()
    if not q:
        return []

    # Very simple tokenization; good enough for MVP.
    tokens = [t for t in q.replace("?", " ").replace(",", " ").split() if len(t) >= 3]
    if not tokens:
        tokens = [q]

    # OR across tokens in message/source/severity.
    conditions = []
    for t in tokens[:8]:  # cap to avoid huge SQL
        like = f"%{t}%"
        conditions.append(LogEntry.message.ilike(like))
        conditions.append(LogEntry.source.ilike(like))
        conditions.append(LogEntry.severity.ilike(like))

    stmt = (
        select(LogEntry)
        .where(or_(*conditions))
        .order_by(LogEntry.timestamp.desc())
        .limit(k)
    )

    rows = (await session.execute(stmt)).scalars().all()

    # Heuristic score: count token matches in message (0..1)
    hits: List[Tuple[str, float]] = []
    for r in rows:
        text = f"{r.source} {r.severity} {r.message}".lower()
        match_count = sum(1 for t in tokens if t in text)
        score = match_count / max(len(tokens), 1)
        hits.append((r.log_id, float(score)))

    # Sort by score desc, then newest first (already roughly newest from SQL)
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


def _format_log_for_prompt(log: RelevantLog) -> str:
    """Compact single-line formatting for LLM context."""
    return f"{log.timestamp} | {log.source} | {log.severity} | {log.message} | score={log.relevance_score:.3f}"


def _heuristic_answer(question: str, relevant: List[RelevantLog]) -> Tuple[str, str]:
    """
    Fallback answer generator when Gemini is not configured.

    This is intentionally simple but useful:
    - Summarizes top results
    - Mentions the most relevant event
    - Produces a reasonable follow-up action
    """
    if not relevant:
        return (
            "I couldn’t find relevant log entries yet. Upload logs first or broaden your question.",
            "Upload a recent log file and try again. If logs exist, try using different keywords.",
        )

    top = relevant[0]
    # A light “count” statement without overclaiming. We only show top-N.
    answer = (
        f"Yes — I found {len(relevant)} highly relevant log entries related to your question. "
        f"The most significant match is {top.severity} on {top.timestamp} from {top.source}: {top.message}"
    )

    followup = (
        f"Review the related entries for {top.source} around {top.timestamp}. "
        "Check maintenance notes and correlate with any sensor calibration or upstream conditions."
    )

    return answer, followup


@router.post("/query", response_model=QueryResponse)
async def query_logs(req: QueryRequest, session: AsyncSession = Depends(get_session)):
    """
    Natural language query over ingested logs.

    Request:
      { "question": "..." }

    Response:
      {
        "answer": "...",
        "relevant_logs": [...],
        "suggested_followup": "..."
      }
    """
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    # ---- Embed (guarded) ----
    t0 = time.perf_counter()
    try:
        q_emb = await asyncio.wait_for(embed_texts_async([question]), timeout=10.0)
    except asyncio.TimeoutError:
        logger.exception("Embedding timed out")
        raise HTTPException(status_code=504, detail="Embedding timed out")
    finally:
        logger.info("embed_ms=%.2f", (time.perf_counter() - t0) * 1000)

# ---- FAISS search (guarded: run in thread + timeout) ----
    t1 = time.perf_counter()
    hits: List[Tuple[str, float]] = []
    used_fallback = False

    try:
        # Keep this short so the endpoint is responsive.
        loop = asyncio.get_running_loop()
        hits = await asyncio.wait_for(
            loop.run_in_executor(faiss_executor, faiss_search, q_emb, 20),
            timeout=5.0
        )

    except asyncio.TimeoutError:
        logger.warning("Vector search timed out; falling back to keyword search")
        used_fallback = True
        hits = await _keyword_fallback_hits(session, question, k=20)
    except Exception:
        logger.exception("Vector search errored; falling back to keyword search")
        used_fallback = True
        hits = await _keyword_fallback_hits(session, question, k=20)
    finally:
        logger.info(
            "retrieval_ms=%.2f hits=%d fallback=%s",
            (time.perf_counter() - t1) * 1000,
            len(hits),
            used_fallback,
        )
    
    if not hits:
        # Fallback: simple keyword search against message/source/severity
        q = f"%{question.lower()}%"
        rows = (await session.execute(
            select(LogEntry).where(LogEntry.message.ilike(q)).limit(10)
        )).scalars().all()

        relevant_top3 = [
            RelevantLog(
                log_id=r.log_id,
                timestamp=r.timestamp.isoformat() + "Z",
                source=r.source,
                severity=r.severity,
                message=r.message,
                relevance_score=0.0,
            )
            for r in rows[:3]
        ]

        answer, followup = _heuristic_answer(question, relevant_top3)
        return QueryResponse(answer=answer, relevant_logs=relevant_top3, suggested_followup=followup)

    top_hits = hits[:10]
    top_ids = [log_id for log_id, _ in top_hits]

# ---- DB fetch (timed) ----
    t2 = time.perf_counter()
    rows = (await session.execute(
        select(LogEntry).where(LogEntry.log_id.in_(top_ids))
    )).scalars().all()
    logger.info("db_ms=%.2f rows=%d", (time.perf_counter() - t2) * 1000, len(rows))
    
    by_id: Dict[str, LogEntry] = {r.log_id: r for r in rows}

    # Build RelevantLog objects in hit order (FAISS order)
    relevant: List[RelevantLog] = []
    for log_id, score in top_hits:
        row = by_id.get(log_id)
        if not row:
            continue
        relevant.append(
            RelevantLog(
                log_id=row.log_id,
                timestamp=row.timestamp.isoformat() + "Z",
                source=row.source,
                severity=row.severity,
                message=row.message,
                relevance_score=round(float(score), 4),
            )
        )

    # Response returns top 3 (like your spec). We still pass a bigger set to Gemini.
    relevant_top3 = relevant[:3]

    severity_counts = Counter(r.severity for r in relevant)
    source_counts = Counter(r.source for r in relevant)
    if relevant:
        timestamps_sorted = sorted(r.timestamp for r in relevant)
        time_window = f"{timestamps_sorted[0]} to {timestamps_sorted[-1]}"
    else:
        time_window = "n/a"

    # Generate answer: Gemini if available, otherwise heuristic.
    if gemini_enabled() and relevant:
        prompt_context = "\n".join(_format_log_for_prompt(r) for r in relevant[:8])
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        stats_lines = [
            f"Total relevant hits considered: {len(relevant)} (returning top 3).",
            (
                "Severity counts: "
                + ", ".join(f"{k}={v}" for k, v in sorted(severity_counts.items()))
            )
            if severity_counts
            else "Severity counts: n/a",
            (
                "Sources touched: "
                + ", ".join(f"{k}({v})" for k, v in sorted(source_counts.items()))
            )
            if source_counts
            else "Sources touched: n/a",
            f"Time window: {time_window}",
        ]
        stats_block = "\n".join(stats_lines)

        prompt = (
            f"Current date and time: {now_utc}\n"
            "You are an incident analyst reviewing industrial equipment logs.\n"
            "Use ONLY the provided log excerpts to answer the question.\n"
            "Be specific: show counts, trends, timestamps, log IDs, sources, and likely causes.\n"
            "If information is missing, say so.\n\n"
            f"Context summary:\n{stats_block}\n\n"
            f"Question:\n{question}\n\n"
            f"Log excerpts:\n{prompt_context}\n\n"
            "Return the response in this exact format:\n"
            "Summary:\n"
            "<4-6 sentences giving a thorough narrative referencing multiple log IDs/timestamps and answering the question.>\n"
            "Followupaction: <two sentence actionable next step tied to the findings>\n"
        )
        try:
            llm_text = (await generate_text(prompt)) or ""
            llm_text = llm_text.strip()

            summary_lines: List[str] = []
            follow_line = ""
            capture_summary = False

            for raw_line in llm_text.splitlines():
                s = raw_line.strip()
                if not s:
                    continue
                normalized = re.sub(r"[^a-z]", "", s.lower())
                if normalized.startswith("summary"):
                    capture_summary = True
                    summary_lines.append(s.split(":", 1)[1].strip() if ":" in s else s)
                    continue
                if normalized.startswith("followup") or normalized.startswith("followupaction") or normalized.startswith("followaction"):
                    follow_line = s.split(":", 1)[1].strip() if ":" in s else s
                    capture_summary = False
                    continue
                if capture_summary:
                    summary_lines.append(s)

            answer_line = " ".join(l for l in summary_lines if l).strip()

            # If model didn't follow the exact format, DON'T throw away the whole response.
            if not answer_line and llm_text:
                answer_line = llm_text  # use full text as the answer

            if not follow_line:
                follow_line = "Review the matching incidents and correlate with maintenance and sensor data."

            # Final safety fallback
            if not answer_line:
                answer_line, follow_line = _heuristic_answer(question, relevant_top3)
            return QueryResponse(
                answer=answer_line,
                relevant_logs=relevant_top3,
                suggested_followup=follow_line,
            )

        except GeminiError as exc:
            logger.warning("Gemini generation failed: %s", exc)
        except Exception:
            logger.exception("Unexpected Gemini failure")

        # Gemini failed, fall back to heuristic response.
        answer, followup = _heuristic_answer(question, relevant_top3)
        return QueryResponse(answer=answer, relevant_logs=relevant_top3, suggested_followup=followup)

    if not gemini_enabled():
        logger.warning("Gemini disabled or API key invalid; returning heuristic answer.")
    elif not relevant:
        logger.info("No relevant logs available for Gemini; returning heuristic answer.")

    answer, followup = _heuristic_answer(question, relevant_top3)
    return QueryResponse(answer=answer, relevant_logs=relevant_top3, suggested_followup=followup)
