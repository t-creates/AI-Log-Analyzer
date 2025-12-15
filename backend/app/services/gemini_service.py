# app/services/gemini_service.py
"""
Gemini (Google AI Studio) generation service.

Goals:
- Keep the rest of the app decoupled from the Gemini SDK.
- Fail gracefully when no API key is configured.
- Provide a single async function to generate text.
- Add basic reliability controls (timeouts + retries).

Notes:
- The underlying google-generativeai client is synchronous.
  We run it in a threadpool via `asyncio.to_thread()` so it doesn't block the event loop.
- For MVP speed, we return plain text. Later we can add JSON schema / structured output.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings


class GeminiError(RuntimeError):
    """Raised for Gemini-related errors (network, auth, generation)."""
    pass


def gemini_enabled() -> bool:
    """True if Gemini is configured and should be used."""
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())


def _generate_sync(prompt: str) -> str:
    """
    Synchronous Gemini call (runs in a thread when used from async code).
    """
    try:
        import google.generativeai as genai
    except Exception as e:
        raise GeminiError(f"google-generativeai import failed: {e}") from e

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or ""
        return text.strip()
    except Exception as e:
        raise GeminiError(str(e)) from e


@retry(
    retry=retry_if_exception_type(GeminiError),
    stop=stop_after_attempt(2),             # MVP: one retry
    wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0),
)
async def generate_text(prompt: str, *, timeout_s: float = 20.0) -> str:
    """
    Generate text from Gemini for a given prompt.

    Args:
        prompt: prompt text
        timeout_s: max seconds to allow the request before failing

    Returns:
        Generated text (may be empty if Gemini returns empty text)

    Behavior:
    - If Gemini is not enabled, returns empty string.
    - If a Gemini error occurs, raises GeminiError (caller can catch & fallback).
    """
    if not prompt or not prompt.strip():
        return ""

    if not gemini_enabled():
        return ""

    try:
        # Run blocking SDK call in a thread to avoid blocking FastAPI event loop.
        coro = asyncio.to_thread(_generate_sync, prompt)
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError as e:
        raise GeminiError(f"Gemini timed out after {timeout_s}s") from e
