# routes/realtime_routes.py
"""
Real-time transcription routes for MedJournee

These endpoints provide:
1. /instant-transcribe/ - Fast transcription during recording (2-3 sec)
2. /finalize-session/ - Post-recording diarization and journal generation
"""

from fastapi import APIRouter, UploadFile, File, Form, Request
from typing import Optional, List
import json

router = APIRouter()

@router.post("/instant-transcribe/")
async def instant_transcribe(
    file: UploadFile = File(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form("auto"),
    session_id: Optional[str] = Form(None),
    family_id: Optional[str] = Form(None)
):
    """
    FAST transcription for real-time display during recording.

    - Uses OpenAI Whisper API (2-3 second latency)
    - Returns transcription + translation + speaker detection
    - When session_id provided, attempts to identify speakers during recording

    Use this endpoint every 3-5 seconds during recording.
    """
    from services.realtime_transcription_service import realtime_transcription_service

    # Initialize speaker tracking if session ID and family ID are provided
    if session_id and family_id:
        realtime_transcription_service.initialize_session_speakers(session_id, family_id)

    try:
        result = await realtime_transcription_service.transcribe_and_translate_instant(
            audio_file=file,
            target_language=target_language,
            source_language=source_language if source_language != "auto" else None,
            session_id=session_id
        )

        return result

    except Exception as e:
        print(f"Instant transcribe error: {e}")
        return {
            "success": False,
            "has_speech": False,
            "error": str(e)
        }


@router.post("/finalize-session/")
async def finalize_session(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    family_id: str = Form(...),
    user_id: str = Form(...),
    patient_name: str = Form(...),
    target_language: str = Form("vi"),
    instant_transcripts: str = Form("[]")  # JSON string of instant transcripts
):
    """
    Finalize recording session with speaker diarization and journal generation.
    
    Call this AFTER recording stops with:
    - Full audio blob
    - All instant transcripts collected during recording
    
    This endpoint:
    1. Runs AssemblyAI speaker diarization on full audio
    2. Matches speakers with enrolled voices
    3. Generates AI journal entry
    4. Saves to database
    """
    from services.realtime_transcription_service import realtime_transcription_service
    from services.ai_journal_service import ai_journal_service
    from services.database_service import database_service
    from services.translation_service import translate_text
    
    try:
        # Parse instant transcripts
        try:
            transcripts = json.loads(instant_transcripts)
        except:
            transcripts = []
        
        print(f"Finalizing session {session_id} with {len(transcripts)} instant transcripts")
        
        # Read full audio
        audio_data = await file.read()
        
        # Step 1: Run post-recording diarization
        diarization_result = await realtime_transcription_service.finalize_with_diarization(
            session_id=session_id,
            full_audio_blob=audio_data,
            instant_transcripts=transcripts,
            family_id=family_id
        )
        
        # Get the final segments (diarized or fallback)
        final_segments = diarization_result.get("segments", [])
        
        # Step 2: Ensure all segments have translations
        for segment in final_segments:
            if not segment.get("translation") and segment.get("text"):
                try:
                    trans_result = await translate_text(segment["text"], target_language, None)
                    segment["translation"] = trans_result.get("translated_text", "")
                except:
                    segment["translation"] = ""
        
        print(f"Final segments after diarization: {len(final_segments)}")
        
        # Step 3: Create session in database
        created_session_id = await database_service.create_session(
            user_id=user_id,
            patient_name=patient_name,
            family_id=family_id,
            target_language=target_language,
            session_id=session_id
        )
        
        # Step 4: Generate AI journal entry
        patient_info = {
            "name": patient_name,
            "family_id": family_id,
            "preferred_language": target_language
        }
        
        journal_result = await ai_journal_service.generate_medical_journal_entry(
            final_segments, patient_info
        )
        
        # Step 5: Save journal to database
        if journal_result.get("success"):
            await database_service.create_journal_entry(
                session_id=created_session_id,
                user_id=user_id,
                patient_name=patient_name,
                family_id=family_id,
                journal_entry=journal_result["journal_entry"],
                ai_confidence=journal_result.get("confidence_score", 0.85)
            )
            
            return {
                "success": True,
                "session_id": session_id,
                "journal_created": True,
                "segments_processed": len(final_segments),
                "diarization_method": diarization_result.get("method", "unknown"),
                "message": "Session finalized and journal created"
            }
        else:
            return {
                "success": False,
                "error": journal_result.get("error", "Journal generation failed"),
                "segments": final_segments
            }
        
    except Exception as e:
        print(f"Finalize session error: {e}")
        import traceback
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/")
def realtime_status():
    """Status endpoint"""
    return {
        "service": "Real-time Transcription",
        "endpoints": {
            "/instant-transcribe/": "Fast transcription during recording (2-3 sec)",
            "/finalize-session/": "Post-recording diarization + journal generation"
        },
        "workflow": [
            "1. Start recording on frontend",
            "2. Every 3-5 seconds, send audio chunk to /instant-transcribe/",
            "3. Display instant transcription to user (no speaker labels yet)",
            "4. When recording stops, send full audio to /finalize-session/",
            "5. Receive diarized segments + generated journal"
        ]
    }
