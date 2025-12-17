# app/services/embed_service.py
"""
Embedding service backed by Gemini's hosted embedding endpoint.

Why this approach?
- Keeps the FastAPI service lightweight (no local SentenceTransformer model)
- Still returns normalized float32 vectors so FAISS works exactly the same
- Lets us run on tiny hosts (Render free tier) at the cost of an external API call
"""

from __future__ import annotations

from typing import List

import asyncio
import logging
import numpy as np
import google.generativeai as genai

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when Gemini embedding generation fails."""
    pass


_client_ready = False


async def embed_texts_async(texts: List[str]) -> np.ndarray:
    return await asyncio.to_thread(embed_texts, texts)


def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts via Gemini.

    Args:
        texts: list of strings to embed

    Returns:
        numpy array of shape (n, d) with dtype float32, normalized (unit length)

    Raises:
        ValueError: if texts is empty
        EmbeddingError: if Gemini call fails or returns malformed data
    """
    if not texts:
        raise ValueError("embed_texts requires a non-empty list of texts.")

    _ensure_gemini_client()

    embeddings: list[np.ndarray] = []
    for text in texts:
        payload = (text or "").strip()
        if not payload:
            payload = " "
        try:
            resp = genai.embed_content(
                model=settings.GEMINI_EMBED_MODEL,
                content=payload,
            )
        except Exception as exc:
            raise EmbeddingError(f"Gemini embedding failed: {exc}") from exc

        vector = resp.get("embedding")
        if not vector:
            raise EmbeddingError("Gemini embedding response missing 'embedding'.")

        arr = np.asarray(vector, dtype="float32")
        if arr.ndim != 1:
            raise EmbeddingError("Gemini embedding must be a 1D vector.")
        norm = float(np.linalg.norm(arr))
        if norm > 0:
            arr = arr / norm

        embeddings.append(arr)

    result = np.vstack(embeddings)
    if result.ndim != 2:
        raise EmbeddingError("Unexpected embedding shape from Gemini.")

    return np.ascontiguousarray(result, dtype="float32")


def _ensure_gemini_client() -> None:
    if not settings.GEMINI_API_KEY:
        raise EmbeddingError("GEMINI_API_KEY is not configured; cannot embed text.")

    global _client_ready
    if _client_ready:
        return

    genai.configure(api_key=settings.GEMINI_API_KEY)
    _client_ready = True
    logger.info("Configured Gemini client for embedding model %s", settings.GEMINI_EMBED_MODEL)
