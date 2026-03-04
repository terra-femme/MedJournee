# routes/realtime_routes.py
"""
Real-time transcription routes for MedJournee

Production-grade API endpoints implementing:
- Quality gates at each pipeline stage
- Retry logic with exponential backoff
- Self-correction capabilities
- Full state management

Endpoints:
1. /instant-transcribe/ - Fast bidirectional transcription during recording (2-3 sec)
2. /finalize-session/ - Post-recording diarization and journal generation
3. /health/ - Health check endpoint

Uses the production multi-agent pipeline.
"""

from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional
import json

from models.schemas import (
    InstantTranscribeResponse,
    FinalizeSessionResponse,
)

router = APIRouter()


@router.post("/instant-transcribe/")
async def instant_transcribe(
    file: UploadFile = File(...),
    provider_spoken: str = Form("en"),
    provider_translate_to: str = Form("vi"),
    family_spoken: str = Form("vi"),
    family_translate_to: str = Form("en"),
    family_id: str = Form(default=""),
    session_id: str = Form(default=""),
    user_id: str = Form(default="")
):
    """
    FAST bidirectional transcription for real-time display during recording.

    - Uses OpenAI Whisper API (2-3 second latency)
    - Auto-detects spoken language, translates to configured target
    - Returns transcription + translation + speaker_role
    - If family_id provided, attempts to identify enrolled speaker

    Use this endpoint every 3-5 seconds during recording.
    """
    from pipeline.orchestrator import instant_transcribe as pipeline_instant

    try:
        result = await pipeline_instant(
            audio_file=file,
            provider_spoken=provider_spoken,
            provider_translate_to=provider_translate_to,
            family_spoken=family_spoken,
            family_translate_to=family_translate_to,
            family_id=family_id,
            session_id=session_id,
            user_id=user_id
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
    provider_spoken: str = Form("en"),
    provider_translate_to: str = Form("vi"),
    family_spoken: str = Form("vi"),
    family_translate_to: str = Form("en"),
    instant_transcripts: str = Form("[]"),
    skip_ai_summary: str = Form("false")
):
    """
    Finalize recording session with speaker diarization and optional journal generation.

    Call this AFTER recording stops with:
    - Full audio blob
    - All instant transcripts collected during recording

    Parameters:
    - skip_ai_summary: "true" to save raw transcript only (no AI processing)

    This endpoint:
    1. Runs AssemblyAI speaker diarization on full audio
    2. Performs bidirectional translation based on detected language
    3. If skip_ai_summary=false: Detects terminology + generates AI journal
    4. If skip_ai_summary=true: Saves raw transcript only
    5. Saves to database
    """
    from pipeline.orchestrator import get_pipeline, MedJourneePipeline
    from services.database_service import database_service

    try:
        # Parse parameters
        skip_ai = skip_ai_summary.lower() == "true"

        try:
            transcripts = json.loads(instant_transcripts)
        except:
            transcripts = []

        print(f"Finalizing session {session_id} with {len(transcripts)} instant transcripts")
        print(f"Skip AI summary: {skip_ai}")

        # Reset file position
        await file.seek(0)

        # If skipping AI, we still need diarization but can skip summarization
        if skip_ai:
            # Run partial pipeline: diarization + translation only
            from agents.diarization_agent import DiarizationAgent
            from agents.translation_agent import TranslationAgent

            diarization_agent = DiarizationAgent()
            translation_agent = TranslationAgent()

            # Step 1: Diarize
            diarization_result = await diarization_agent.diarize(file, family_id)

            if not diarization_result.success or not diarization_result.segments:
                return {
                    "success": False,
                    "error": diarization_result.error or "Diarization failed",
                    "failed_stage": "diarization"
                }

            # Step 2: Translate segments
            translated_segments = await translation_agent.translate_segments(
                diarization_result.segments,
                provider_spoken,
                provider_translate_to,
                family_spoken,
                family_translate_to
            )

            final_segments = translated_segments or []
            journal_entry = None
            state = None

            print(f"Raw transcript mode: {len(final_segments)} segments")

        else:
            # Full pipeline with AI summarization
            pipeline = get_pipeline()
            state = await pipeline.process(
                audio_file=file,
                family_id=family_id,
                user_id=user_id,
                provider_spoken=provider_spoken,
                provider_translate_to=provider_translate_to,
                family_spoken=family_spoken,
                family_translate_to=family_translate_to,
                patient_name=patient_name,
                session_id=session_id
            )

            if not state.is_successful():
                return {
                    "success": False,
                    "error": "; ".join(state.errors) if state.errors else "Pipeline failed",
                    "failed_stage": state.current_stage
                }

            final_segments = state.translated_segments
            journal_entry = state.summarization.journal_entry if state.summarization else None

        print(f"Final segments after processing: {len(final_segments)}")

        # Save to database
        created_session_id = await database_service.create_session(
            user_id=user_id,
            patient_name=patient_name,
            family_id=family_id,
            target_language=family_spoken,
            session_id=session_id
        )

        if skip_ai:
            # Save raw transcript only (no AI processing)
            segments_for_db = [
                {
                    "speaker": seg.speaker,
                    "speaker_role": seg.speaker_role.value if hasattr(seg.speaker_role, 'value') else str(seg.speaker_role),
                    "enrolled_name": seg.enrolled_name,
                    "text": seg.text,
                    "translation": seg.translation if hasattr(seg, 'translation') else "",
                    "start_time": seg.start_time,
                    "end_time": seg.end_time
                }
                for seg in final_segments
            ]

            print(f"Saving raw transcript entry for session: {created_session_id}")
            print(f"Number of segments to save: {len(segments_for_db)}")

            entry_id = await database_service.create_raw_transcript_entry(
                session_id=created_session_id,
                user_id=user_id,
                patient_name=patient_name,
                family_id=family_id,
                segments=segments_for_db
            )

            print(f"Raw transcript saved successfully. Entry ID: {entry_id}")

            return {
                "success": True,
                "session_id": created_session_id,  # Use the confirmed session_id from DB
                "entry_id": entry_id,
                "mode": "raw_transcript",
                "segments_processed": len(final_segments),
                "message": "Raw transcript saved without AI summarization"
            }

        elif journal_entry:
            # Build raw transcript to store alongside AI summary
            raw_transcript_lines = []
            for seg in final_segments:
                # Enrolled name takes priority; otherwise format "SPEAKER_1" → "Speaker 1"
                if seg.enrolled_name:
                    speaker = seg.enrolled_name
                else:
                    raw_label = seg.speaker or "SPEAKER_1"
                    speaker = raw_label.replace("SPEAKER_", "Speaker ").replace("_", " ").title()
                text = seg.text
                translation = seg.translation if hasattr(seg, 'translation') else ""

                line = f"{speaker}: {text}"
                if translation and translation != text:
                    line += f"\n  → {translation}"
                raw_transcript_lines.append(line)

            raw_transcript = "\n\n".join(raw_transcript_lines)

            # Convert journal entry to dict format for database
            journal_dict = {
                "entry_type": "medical_visit",
                "visit_information": {
                    "date": journal_entry.visit_date,
                    "provider": journal_entry.provider_name or "Healthcare Provider",
                    "visit_type": journal_entry.visit_type,
                    "main_reason": journal_entry.chief_complaint
                },
                "medical_details": {
                    "symptoms": journal_entry.symptoms,
                    "diagnoses": journal_entry.diagnoses,
                    "treatments": journal_entry.treatments,
                    "vital_signs": journal_entry.vital_signs
                },
                "medications": [
                    {"name": m.name, "dosage": m.dosage, "frequency": m.frequency, "duration": m.duration}
                    for m in journal_entry.medications
                ],
                "follow_up_care": {
                    "instructions": journal_entry.follow_up_instructions,
                    "appointments": [{"type": a.type, "date": a.date} for a in journal_entry.next_appointments],
                    "action_items": journal_entry.action_items
                },
                "family_section": {
                    "patient_questions": journal_entry.patient_questions,
                    "family_concerns": journal_entry.family_concerns,
                    "notes_for_family": journal_entry.family_summary
                },
                "medical_terms_explained": {
                    t.term: {"simple": t.simple, "explanation": t.explanation}
                    for t in journal_entry.medical_terms
                },
                "summary": journal_entry.family_summary
            }

            await database_service.create_journal_entry(
                session_id=created_session_id,
                user_id=user_id,
                patient_name=patient_name,
                family_id=family_id,
                journal_entry=journal_dict,
                ai_confidence=state.summarization.confidence_score if state.summarization else 0.5,
                raw_transcript=raw_transcript
            )

            # Return comprehensive response with quality metrics
            return FinalizeSessionResponse(
                success=True,
                session_id=session_id,
                journal_entry=journal_entry,
                segments_processed=len(final_segments),
                terms_detected=state.terminology.terms_count if state.terminology else 0,
                confidence_score=state.summarization.confidence_score if state.summarization else 0.5,
                quality_scores=state.get_quality_summary(),
                corrections_made=len(state.corrections),
                warnings=state.warnings,
                errors=state.errors,
                processing_time_ms=state.total_duration_ms or 0.0
            )
        else:
            return FinalizeSessionResponse(
                success=False,
                session_id=session_id,
                errors=["Journal generation failed"],
                segments_processed=len(final_segments)
            )

    except Exception as e:
        print(f"Finalize session error: {e}")
        import traceback
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/health/")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "MedJournee Real-time API",
        "architecture": "multi-agent-pipeline",
        "features": {
            "quality_gates": True,
            "retry_logic": True,
            "self_correction": True,
            "state_management": True
        }
    }


@router.get("/")
def realtime_status():
    """Status endpoint"""
    return {
        "service": "MedJournee Real-time API (Production Pipeline)",
        "version": "2.0.0",
        "architecture": "multi-agent-pipeline",
        "endpoints": {
            "/instant-transcribe/": "Fast bidirectional transcription during recording (2-3 sec)",
            "/finalize-session/": "Post-recording diarization + journal generation",
            "/health/": "Health check"
        },
        "agents": [
            "TranscriptionAgent - Audio to text with hallucination filtering",
            "DiarizationAgent - Speaker identification (AssemblyAI)",
            "TranslationAgent - Bidirectional translation (FREE)",
            "TerminologyAgent - Medical term detection",
            "SummarizationAgent - Journal generation with self-correction"
        ],
        "features": {
            "quality_gates": "Validate output at each pipeline stage",
            "retry_logic": "Automatic retry with exponential backoff",
            "self_correction": "Agents critique and fix their own output",
            "state_management": "Full pipeline state tracking"
        },
        "language_params": {
            "provider_spoken": "Language the provider speaks (e.g., 'en')",
            "provider_translate_to": "Language to translate provider speech into (e.g., 'vi')",
            "family_spoken": "Language the family speaks (e.g., 'vi')",
            "family_translate_to": "Language to translate family speech into (e.g., 'en')"
        },
        "workflow": [
            "1. Start recording on frontend",
            "2. Every 3-5 seconds, send audio chunk to /instant-transcribe/",
            "3. Display instant transcription with speaker_role coloring",
            "4. When recording stops, send full audio to /finalize-session/",
            "5. Receive diarized segments + quality scores + generated journal"
        ]
    }
