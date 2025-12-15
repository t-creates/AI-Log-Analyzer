## AI Agent Guidance — AI Log Analyzer 🔧

Short, actionable guidance for AI coding agents working in this repository.

### Big picture (what this repo does)
- Backend FastAPI service that ingests CSV/TXT log files, stores them in SQLite, creates embeddings, and performs semantic search using FAISS. See `backend/app/main.py` and `technical-setup.txt` for the high-level plan.
- Optional LLM integration (Gemini) is used to produce natural-language answers for `/query`. LLM usage is guarded by environment variables and safe fallbacks (see `app/services/gemini_service.py`).

### Key components & flows
- API: `backend/app/main.py` (FastAPI app) and route modules in `backend/app/api/routes/*.py` (`/upload`, `/query`, `/summary`, `/logs`).
- DB: `backend/app/db/` — SQLAlchemy + aiosqlite; `init_db()` applies SQLite pragmas and creates tables (`app/db/session.py`, `app/db/models.py`). DB file defaults to `backend/data/app.db`.
- Embeddings: `backend/app/services/embed_service.py` uses Sentence-Transformers and returns normalized float32 arrays (cosine = inner product).
- Vector store: `backend/app/services/faiss_service.py` manages an in-process FAISS index and id map persisted at `backend/data/faiss.index` and `backend/data/faiss_idmap.json`. The index is created lazily on first add and the embedding dimension is inferred from that first add.
- Ingestion flow: `app/api/routes/ingest.py` -> `app/services/ingest_service.index_log_entries_for_search()` (embeddings → FAISS). Ingest purposely does NOT fail uploads when indexing fails (MVP decision).
- Generation: `app/services/gemini_service.py` wraps google-generativeai and runs blocking calls in a thread with timeouts & retries.

### Project-specific conventions & patterns
- Module-level singletons (simple, per-process lifecycle): embedding model (`_model`) and FAISS state (`_index`, `_idmap`) are stored at module scope.
- Embedding canonicalization: `_to_embedding_text()` in `ingest_service.py` builds the stable text `[{severity}] {source}: {message}` — keep this stable when changing indexing.
- API responses use small helpers in `app/main.py`: `ok()` and `fail()` to keep the surface consistent.
- Environment-first config: `app/core/config.py` uses `pydantic-settings` and reads `.env` located at `backend/.env` (note: uvicorn is expected to be run from `backend/`).

### Useful commands & dev workflow (macOS / fish shell)
1. Create & activate venv (fish):
   - python -m venv .venv
   - source .venv/bin/activate.fish
2. Install deps:
   - pip install -r backend/requirements.txt
3. Run locally (from `backend/`):
   - cd backend
   - uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
4. Quick curl examples (adjust host/port):
   - Upload sample logs: curl -v -F "file=@tmp/sample_logs.csv" http://localhost:8000/upload
   - Query: curl -v -H "Content-Type: application/json" -d '{"question":"Were there any pressure drops last week?"}' http://localhost:8000/query
5. Validate Gemini credentials (manual check): `python backend/test_gemini.py` (prints heartbeats and raw response).

### Environment variables to know
- `GEMINI_API_KEY` (unset disables Gemini features)
- `GEMINI_MODEL` (default: `gemini-3-pro-preview`)
- `EMBED_MODEL` (default SentenceTransformer model in `config.py`)
- `DATABASE_URL` (defaults to `sqlite+aiosqlite:///./data/app.db`)
- `FAISS_INDEX_PATH`, `FAISS_IDMAP_PATH` (defaults in config)
- `ENV`, `LOG_LEVEL`, `CORS_ALLOW_ORIGINS`, `MAX_UPLOAD_MB`

### Testing & debugging tips
- The app runs DB + FAISS initialization on startup (`app.main:on_startup()` calls `init_db()` and `init_faiss()`), so start the server to reproduce startup behavior.
- FAISS index is persisted by `faiss_service.persist()` which is called during shutdown and after indexing. If you change embedding format, reindex or remove `backend/data/faiss.index`.
- Timeouts & retries: Gemini requests use `tenacity` with a short retry strategy; LLM calls are run via `asyncio.to_thread()` and guarded by `asyncio.wait_for()`.
- To debug SQL, temporarily set `engine` echo=True in `app/db/session.py` or add logging in the route.

### Files to inspect when working on a feature
- API behavior: `backend/app/api/routes/query.py`, `ingest.py`, `summary.py`
- Embeddings & indexing: `backend/app/services/embed_service.py`, `ingest_service.py`, `faiss_service.py`
- Gemini/LLM: `backend/app/services/gemini_service.py` and `backend/test_gemini.py`
- Config: `backend/app/core/config.py`
- DB: `backend/app/db/session.py`, `backend/app/db/models.py`

---
If anything here is ambiguous or you'd like the instructions tailored (e.g., adding more sample prompts, CI steps, or PR/testing conventions), tell me what to add and I'll iterate. ✅
