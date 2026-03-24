# services/gladia_service.py
"""
Gladia real-time transcription service.

Handles session creation for Gladia's live WebSocket API.
Each recording session gets one Gladia session — a persistent
WebSocket that receives PCM audio and returns transcript + speaker labels.

Speaker diarization is voice-based (not language-based), so colors
are correct even when both speakers use the same language.
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GLADIA_API_KEY = os.getenv("GLADIA_API_KEY")
GLADIA_BASE_URL = "https://api.gladia.io"

# In-memory map: session_id → Gladia WebSocket URL
# Populated on session creation, cleared when the WebSocket proxy closes.
_sessions: dict[str, str] = {}


async def create_live_session(languages: list[str]) -> dict:
    """
    Create a Gladia live transcription session.

    Args:
        languages: List of expected language codes (e.g. ["en", "vi"]).
                   1 language → forced. 2+ → code-switching enabled.
        diarization: Enable speaker diarization (default True).

    Returns:
        {"session_id": str, "url": str}
    """
    if not GLADIA_API_KEY:
        raise ValueError("GLADIA_API_KEY not set in environment")

    clean_langs = [l for l in languages if l and l not in ("auto", "")]
    if not clean_langs:
        clean_langs = ["en"]

    config = {
        "encoding": "wav/pcm",
        "bit_depth": 16,
        "sample_rate": 16000,
        "channels": 1,
        "language_config": {
            "languages": clean_langs,
            "code_switching": len(clean_langs) > 1,
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{GLADIA_BASE_URL}/v2/live",
            headers={
                "X-Gladia-Key": GLADIA_API_KEY,
                "Content-Type": "application/json",
            },
            json=config,
        )
        if response.status_code >= 400:
            raise ValueError(
                f"Gladia API error {response.status_code}: {response.text}"
            )
        data = response.json()

    session_id = data["id"]
    gladia_url = data["url"]

    # Store for the WebSocket proxy to look up
    _sessions[session_id] = gladia_url

    return {"session_id": session_id, "url": gladia_url}


def get_session_url(session_id: str) -> str | None:
    return _sessions.get(session_id)


def remove_session(session_id: str):
    _sessions.pop(session_id, None)
