# app/services/embed_service.py
"""
Embedding service using Sentence-Transformers.

Responsibilities:
- Load the embedding model once (singleton in-process cache)
- Provide a simple function to embed batches of texts
- Ensure embeddings are returned as float32 numpy arrays
- Normalize embeddings (so FAISS inner product behaves like cosine similarity)

Why normalize?
- Cosine similarity is the most common semantic-search metric.
- If vectors are normalized, cosine(a, b) == dot(a, b),
  which lets us use FAISS IndexFlatIP efficiently.
"""

from __future__ import annotations

from typing import List

import asyncio
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings


# Module-level singleton cache (fast + simple for MVP).
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """
    Lazily load and cache the SentenceTransformer model.

    This prevents expensive reloads per request.

    Note:
    - This is safe for typical FastAPI deployments where each worker process
      has its own memory space.
    - If we later add multi-process indexing or background jobs, we may want
      a more explicit lifecycle manager.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBED_MODEL, device="cpu")
    return _model

async def embed_texts_async(texts: List[str]) -> np.ndarray:
    return await asyncio.to_thread(embed_texts, texts)

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts.

    Args:
        texts: list of strings to embed

    Returns:
        numpy array of shape (n, d) with dtype float32, normalized (unit length)

    Raises:
        ValueError: if texts is empty
    """
    if not texts:
        raise ValueError("embed_texts requires a non-empty list of texts.")

    model = get_model()

    # normalize_embeddings=True ensures unit-length vectors for cosine similarity.
    emb = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    # Sentence-Transformers can return list/np array depending on config.
    arr = np.asarray(emb, dtype="float32")

    if arr.ndim != 2:
        raise ValueError("Embedding output must be a 2D array of shape (n, d).")

    return arr
