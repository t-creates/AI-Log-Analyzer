from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse

# Routers (we’ll implement these next)
from app.api.routes.ingest import router as ingest_router
from app.api.routes.query import router as query_router
from app.api.routes.ai_summary import router as summary_router
from app.api.routes.logs import router as logs_router
from app.api.routes.dashboard import router as dashboard_router


# Settings + init (we’ll implement these as lightweight modules next)
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.executors import faiss_executor
import logging
logger = logging.getLogger("app")

# app/main.py (TOP OF FILE — before importing anything heavy)
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"


def _ensure_hf_cache_dir() -> None:
    """
    Make sure Hugging Face caches live in a writable directory.

    Priority:
    1. Respect any of HF_HOME / HF_HUB_CACHE / TRANSFORMERS_CACHE set by env.
    2. Otherwise default to ./.cache/huggingface (repo-relative) and set HF_HOME.
    """
    candidate_vars = ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE")
    for var in candidate_vars:
        path = os.environ.get(var)
        if path:
            os.makedirs(path, exist_ok=True)
            logger.info("Using %s for HuggingFace cache (%s)", path, var)
            return

    default_cache = os.path.abspath(os.path.join(".", ".cache", "huggingface"))
    os.makedirs(default_cache, exist_ok=True)
    os.environ["HF_HOME"] = default_cache
    logger.info(
        "No HuggingFace cache env set; defaulting HF_HOME to %s", default_cache
    )


_ensure_hf_cache_dir()


# -------------------------
# Response helpers (MVP)
# -------------------------
def ok(data: Any = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"success": True, "data": data, "error": None, "meta": meta or {}}


def fail(
    code: str,
    message: str,
    details: Optional[Any] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
        "meta": meta or {},
    }


# -------------------------
# App factory
# -------------------------
app = FastAPI(
    title="AI Log Analyzer API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)


# -------------------------
# Middleware
# -------------------------
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS for future React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request-id + timing + upload-size guard
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.perf_counter()

    # Basic upload limit guard (works well for log file uploads)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.MAX_UPLOAD_BYTES:
                return ORJSONResponse(
                    status_code=413,
                    content=fail(
                        code="PAYLOAD_TOO_LARGE",
                        message=f"Upload too large. Max is {settings.MAX_UPLOAD_MB} MB.",
                        meta={"request_id": request_id},
                    ),
                )
        except ValueError:
            pass

    response = await call_next(request)

    response.headers["x-request-id"] = request_id
    response.headers["x-response-ms"] = f"{(time.perf_counter() - start) * 1000:.2f}"
    return response


# -------------------------
# Routes
# -------------------------
@app.get("/health", response_class=ORJSONResponse)
async def health():
    # Keep it tiny & fast: used by docker/k8s/reverse proxies
    return ok({"status": "ok", "env": settings.ENV})


# API endpoints
app.include_router(ingest_router, prefix="", tags=["ingest"])
app.include_router(query_router, prefix="", tags=["query"])
app.include_router(summary_router, prefix="", tags=["summary"])
app.include_router(logs_router, prefix="", tags=["logs"])
app.include_router(dashboard_router, tags=["dashboard"])

# -------------------------
# Error handling
# -------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

    # Show minimal debug info only in dev
    details = None
    if settings.ENV == "dev":
        details = {"type": exc.__class__.__name__, "message": str(exc)}

    return ORJSONResponse(
        status_code=500,
        content=fail(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            details=details,
        ),
    )



# -------------------------
# Startup / shutdown
# -------------------------
@app.on_event("startup")
async def on_startup():
    configure_logging(settings.LOG_LEVEL)

    # Initialize DB + load/create FAISS index.
    # These imports are inside startup so we don’t create side effects on import.
    from app.db.session import init_db
    from app.services.faiss_service import init_faiss
    from app.services.gemini_service import gemini_enabled

    await init_db()
    await init_faiss()

    if gemini_enabled():
        logger.info("Gemini enabled (model=%s)", settings.GEMINI_MODEL)
    else:
        logger.warning("Gemini disabled; set GEMINI_API_KEY to enable AI answers.")


@app.on_event("shutdown")
async def on_shutdown():
    # Optional hooks (flush index, close clients, etc.)
    from app.services.faiss_service import shutdown_faiss
    faiss_executor.shutdown(wait=False, cancel_futures=True)
    await shutdown_faiss()
