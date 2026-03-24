# routes/gladia_routes.py
"""
Gladia real-time transcription routes.

POST /gladia/session  — create a Gladia live session (returns session_id)
WS   /gladia/ws/{session_id} — proxy: frontend PCM audio → Gladia → frontend transcript

The proxy enriches Gladia's final transcripts with a translation before
forwarding to the frontend, so the recording screen gets both text and
translation in one message — same contract as the old instant-transcribe path.
"""

import asyncio
import json
import logging

import websockets
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from middleware.auth import require_auth, verify_ws_token
from services.gladia_service import create_live_session, get_session_url, remove_session

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SessionRequest(BaseModel):
    provider_spoken: str = "en"
    family_spoken: str = "vi"
    provider_spoken_2: str = ""
    family_spoken_2: str = ""


@router.post("/session")
async def create_session(req: SessionRequest, _user: dict = Depends(require_auth)):
    """
    Create a Gladia live session.
    Call this when the user taps Record, before opening the WebSocket.
    """
    all_langs = [req.provider_spoken, req.family_spoken,
                 req.provider_spoken_2, req.family_spoken_2]
    languages = list({l for l in all_langs if l and l not in ("auto", "")})

    try:
        session = await create_live_session(languages=languages)
    except Exception as e:
        logger.error(f"[Gladia] Session creation failed: {e}")
        return JSONResponse(status_code=502, content={"error": "Failed to create Gladia session"})
    return {"session_id": session["session_id"]}


@router.websocket("/ws/{session_id}")
async def websocket_proxy(
    websocket: WebSocket,
    session_id: str,
    token: str = "",
    family_spoken: str = "vi",
    provider_translate_to: str = "vi",
    family_translate_to: str = "en",
):
    """
    WebSocket proxy: browser → backend → Gladia → backend → browser.

    Browser sends:  raw PCM binary frames (16-bit signed, 16 kHz, mono)
    Browser receives: JSON messages enriched with translation + speaker_role

    Authentication: pass JWT as ?token=<jwt> query parameter.
    Browsers cannot send custom headers during the WebSocket handshake,
    so query-param token is the standard approach.
    """
    try:
        verify_ws_token(token)
    except Exception:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()

    # Sanitize session_id before any logging to prevent log injection
    safe_sid = session_id.replace('\n', '').replace('\r', '')[:36]

    gladia_url = get_session_url(session_id)
    if not gladia_url:
        await websocket.close(code=4004, reason="Session not found")
        return

    try:
        async with websockets.connect(gladia_url) as gladia_ws:

            async def audio_to_gladia():
                """Forward PCM audio from browser to Gladia."""
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await gladia_ws.send(data)
                except WebSocketDisconnect:
                    # Browser stopped recording — close Gladia side cleanly
                    await gladia_ws.close()
                except Exception as e:
                    logger.warning(f"[Gladia] audio_to_gladia error: {e}")

            async def gladia_to_browser():
                """Receive Gladia transcripts, enrich with translation, forward to browser."""
                try:
                    async for raw in gladia_ws:
                        logger.debug(f"[Gladia] raw message: {raw!r:.200}")
                        if not isinstance(raw, str):
                            continue

                        msg = json.loads(raw)

                        # Only forward final transcripts
                        if msg.get("type") != "transcript":
                            continue
                        data = msg.get("data", {})
                        if not data.get("is_final"):
                            continue

                        # v2 live API returns "utterance" (singular object),
                        # not "utterances" (plural array used by pre-recorded)
                        raw_utt = data.get("utterance") or data.get("utterances")
                        if not raw_utt:
                            continue
                        utterances = [raw_utt] if isinstance(raw_utt, dict) else raw_utt

                        # Words Whisper/Gladia commonly hallucinate on silence or ambient noise
                        _HALLUCINATIONS = {
                            "thank you", "thanks", "you", "uh", "um", "hmm", "hm",
                            "slurp", "conversation", "bye", "bye bye", "goodbye",
                            "see you", "see you later", "thanks.", "thank you.",
                            "you.", "okay", "ok", "hey", "hi", "hello",
                        }

                        for utterance in utterances:
                            text = (utterance.get("text") or "").strip()
                            if len(text) < 3:
                                continue

                            # Drop known hallucination strings
                            if text.lower().rstrip(".!?,") in _HALLUCINATIONS:
                                logger.debug(f"[Gladia] Hallucination filtered: {text!r}")
                                continue

                            speaker_index = utterance.get("speaker", 0)
                            detected_lang = (utterance.get("language") or "en").lower()
                            start_time = utterance.get("start", 0.0)
                            end_time = utterance.get("end", 0.0)

                            # Speaker 0 = first voice heard (typically provider, blue)
                            # Speaker 1 = second voice (typically family, green)
                            # These are reassigned correctly in finalize-session via
                            # AssemblyAI + enrollment matching.
                            is_family = speaker_index == 1
                            speaker_role = "patient_family" if is_family else "provider"

                            # Translation
                            translation = ""
                            try:
                                from services.translation_service import translate_text
                                if detected_lang.startswith(family_spoken[:2]):
                                    target = family_translate_to
                                else:
                                    target = provider_translate_to
                                t_result = await translate_text(text, target, detected_lang)
                                translation = t_result.get("translated_text", "")
                            except Exception as e:
                                logger.debug(f"[Gladia] Translation skipped: {e}")

                            await websocket.send_json({
                                "type": "transcript",
                                "text": text,
                                "translation": translation,
                                "speaker_role": speaker_role,
                                "speaker_index": speaker_index,
                                "detected_language": detected_lang,
                                "start": start_time,
                                "end": end_time,
                                "is_final": True,
                            })

                except Exception as e:
                    logger.warning(f"[Gladia] gladia_to_browser error: {e}")
                logger.info("[Gladia] gladia_to_browser exited for session %s", safe_sid)

            await asyncio.gather(
                audio_to_gladia(),
                gladia_to_browser(),
                return_exceptions=True,
            )

    except WebSocketDisconnect:
        pass  # Browser disconnected cleanly during proxy setup — no action needed
    except Exception as e:
        logger.error("[Gladia] Proxy error for session %s: %s", safe_sid, e)
    finally:
        remove_session(session_id)
