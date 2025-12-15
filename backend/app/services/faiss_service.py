# app/services/faiss_service.py
"""
FAISS vector index management.

Responsibilities:
- Load an existing index + id map on startup (if present)
- Create an index lazily when first embeddings arrive (dimension is known then)
- Add embeddings with stable row IDs
- Search nearest neighbors for a query vector
- Persist index and row_id -> log_id mapping to disk

Similarity:
- We use cosine similarity by normalizing vectors and using inner product (IP).
  That is: cosine(a, b) == dot(a_norm, b_norm)
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

import faiss
#faiss.omp_set_num_threads(1)
import numpy as np
import threading

from app.core.config import settings

_INDEX_LOCK = threading.RLock()

# In-memory singleton state (simple + fast for MVP).
_index: faiss.Index | None = None

# Maps FAISS internal integer ids -> our stable LogEntry.log_id strings.
_idmap: Dict[int, str] = {}

# Next integer id to assign to a new vector (monotonic).
_next_row_id: int = 0


async def init_faiss() -> None:
    """
    Initialize FAISS state.

    If persisted index + id map exist, load them.
    Otherwise, start empty and build index lazily on first add.
    """
    global _index, _idmap, _next_row_id

    idx_path = settings.FAISS_INDEX_PATH
    map_path = settings.FAISS_IDMAP_PATH

    if os.path.exists(idx_path) and os.path.exists(map_path):
        _index = faiss.read_index(idx_path)
        with open(map_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # JSON keys are strings; normalize to int
        _idmap = {int(k): str(v) for k, v in raw.items()}
        _next_row_id = (max(_idmap.keys()) + 1) if _idmap else 0
        return

    # No existing files -> start fresh. Index will be created on first add.
    _index = None
    _idmap = {}
    _next_row_id = 0


def _ensure_index(dimension: int) -> None:
    """
    Create a FAISS index if one doesn't exist.

    We use:
    - IndexFlatIP for inner product similarity (works with normalized vectors)
    - IndexIDMap2 wrapper so we can supply our own integer IDs
    """
    global _index
    with _INDEX_LOCK:
        if _index is not None:
            return
        base = faiss.IndexFlatIP(dimension)
        _index = faiss.IndexIDMap2(base)


def add_embeddings(log_ids: List[str], embeddings: np.ndarray) -> None:
    """
    Add a batch of embeddings to the FAISS index.

    Args:
        log_ids: our stable log identifiers (LogEntry.log_id)
        embeddings: shape (n, d) float32 numpy array

    Notes:
    - Embeddings must already be normalized if we want true cosine similarity.
      Our embed_service currently normalizes embeddings.
    """
    global _next_row_id, _idmap
    with _INDEX_LOCK:
        if embeddings is None or embeddings.size == 0:
            return

        if embeddings.dtype != np.float32:
            embeddings = embeddings.astype("float32")

        if embeddings.ndim != 2:
            raise ValueError("Embeddings must be a 2D array of shape (n, d).")

        n, d = embeddings.shape
        if n != len(log_ids):
            raise ValueError("log_ids length must match embeddings rows.")

        embeddings = np.ascontiguousarray(embeddings, dtype="float32")

    with _INDEX_LOCK:
        _ensure_index(d)

        # Dim mismatch guard (prevents native weirdness)
        if hasattr(_index, "d") and _index.d != d:
            raise ValueError(f"FAISS dim mismatch: index d={_index.d}, embeddings d={d}")

        ids = np.arange(_next_row_id, _next_row_id + n, dtype="int64")
        _index.add_with_ids(embeddings, ids)

        for row_id, log_id in zip(ids.tolist(), log_ids):
            _idmap[int(row_id)] = str(log_id)

        _next_row_id += n
    print(f"[FAISS] add_embeddings: added={n} ntotal={_index.ntotal} next_row_id={_next_row_id}")


def search(query_embedding: np.ndarray, k: int = 20) -> List[Tuple[str, float]]:
    """
    Search FAISS for the top-k most similar vectors.

    Args:
        query_embedding: shape (1, d) float32 array
        k: number of results

    Returns:
        List of (log_id, relevance_score) where relevance_score is inner product
        (cosine similarity if vectors are normalized).

    If the index is empty, returns [].
    """
    if query_embedding.dtype != np.float32:
        query_embedding = query_embedding.astype("float32")

    if query_embedding.ndim != 2 or query_embedding.shape[0] != 1:
        raise ValueError("query_embedding must have shape (1, d).")

    query_embedding = np.ascontiguousarray(query_embedding, dtype="float32")

    with _INDEX_LOCK:
        if _index is None or _index.ntotal == 0:
            return []

        if hasattr(_index, "d") and _index.d != query_embedding.shape[1]:
            raise ValueError(f"FAISS dim mismatch: index d={_index.d}, query d={query_embedding.shape[1]}")

        scores, ids = _index.search(query_embedding, k)
        print(f"[FAISS] search: ntotal={_index.ntotal} d={getattr(_index,'d',None)} qd={query_embedding.shape[1]}")
        
        results: List[Tuple[str, float]] = []
        for row_id, score in zip(ids[0].tolist(), scores[0].tolist()):
            if row_id == -1:
                continue
            log_id = _idmap.get(int(row_id))
            if log_id:
                results.append((log_id, float(score)))

        return results


def persist() -> None:
    with _INDEX_LOCK:
        if _index is None:
            return

        os.makedirs(os.path.dirname(settings.FAISS_INDEX_PATH) or ".", exist_ok=True)

        tmp_idx = settings.FAISS_INDEX_PATH + ".tmp"
        tmp_map = settings.FAISS_IDMAP_PATH + ".tmp"

        faiss.write_index(_index, tmp_idx)

        with open(tmp_map, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in _idmap.items()}, f)

        os.replace(tmp_idx, settings.FAISS_INDEX_PATH)
        os.replace(tmp_map, settings.FAISS_IDMAP_PATH)



async def shutdown_faiss() -> None:
    """
    Flush FAISS state to disk on application shutdown.
    """
    persist()
