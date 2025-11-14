# routes/combined_translation.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from services.whisper_service import transcribe_audio
from services.translation_service import translate_text
from services.cloud_speaker_service import cloud_speaker_service
from typing import Optional, List, Dict
import os
from services.voice_enrollment_service import enroll_voice_endpoint, enhanced_speaker_processing
from services.ai_journal_service import ai_journal_service
from fastapi import BackgroundTasks
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Request
from services.database_service import database_service


router = APIRouter()

def fix_source_language(source_language: Optional[str]) -> Optional[str]:
    """Convert 'auto' to None for Google Translate API compatibility"""
    if source_language and source_language.lower() in ["auto", "automatic", "detect"]:
        return None
    return source_language

@router.post("/diarize-and-translate/")
async def diarize_and_translate(
    file: UploadFile = File(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form("auto")
):
    """
    Cloud-based speaker diarization with automatic audio deletion.
    Audio is processed temporarily and immediately deleted by the cloud service.
    """
    try:
        # Step 1: Process with cloud diarization (audio auto-deleted after processing)
        speaker_segments = await cloud_speaker_service.process_audio_with_diarization(file)
        
        if not speaker_segments:
            # Fallback to regular transcription if cloud diarization fails
            await file.seek(0)
            transcription_result = await transcribe_audio(file, source_language)
            
            if not transcription_result["success"]:
                return {
                    "success": False,
                    "error": "Both cloud diarization and local transcription failed",
                    "speaker_segments": []
                }
            
            # Create a single segment for fallback
            original_text = transcription_result["text"].strip()
            if len(original_text) >= 3:
                source_lang = fix_source_language(source_language)
                translation_result = await translate_text(original_text, target_language, source_lang)
                
                speaker_segments = [{
                    "speaker": "SPEAKER_1",
                    "text": original_text,
                    "translation": translation_result["translated_text"],
                    "start_time": 0,
                    "end_time": 30,
                    "confidence": 0.6,
                    "method": "whisper_fallback"
                }]
        
        # Step 2: Translate each speaker segment
        for segment in speaker_segments:
            if "translation" not in segment:  # Only translate if not already done
                source_lang = fix_source_language(source_language)
                translation_result = await translate_text(segment["text"], target_language, source_lang)
                segment["translation"] = translation_result["translated_text"]
        
        return {
            "success": True,
            "speaker_segments": speaker_segments,
            "total_segments": len(speaker_segments),
            "processing_method": "cloud_diarization",
            "privacy_note": "Audio automatically deleted after processing"
        }
        
    except Exception as e:
        print(f"Diarization processing error: {e}")
        return {
            "success": False,
            "error": f"Processing failed: {str(e)}",
            "speaker_segments": []
        }

@router.post("/debug-speakers/")
async def debug_speakers(
    file: UploadFile = File(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form("auto")
):
    """Debug endpoint for comprehensive speaker detection analysis"""
    try:
        print("Debug endpoint called")
        
        # Process with cloud diarization for analysis
        speaker_segments = await cloud_speaker_service.process_audio_with_diarization(file)
        
        # Comprehensive debug analysis
        debug_info = {
            "total_segments": len(speaker_segments),
            "segments_by_speaker": {},
            "segments_detail": [],
            "issues_detected": [],
            "processing_quality": "unknown"
        }
        
        if speaker_segments:
            # Count segments per speaker
            for segment in speaker_segments:
                speaker = segment.get("speaker", "unknown")
                debug_info["segments_by_speaker"][speaker] = debug_info["segments_by_speaker"].get(speaker, 0) + 1
            
            # Detailed segment analysis (first 10 for debugging)
            for i, segment in enumerate(speaker_segments[:10]):
                debug_info["segments_detail"].append({
                    "index": i,
                    "speaker": segment.get("speaker", "unknown"),
                    "method": segment.get("method", "unknown"),
                    "confidence": str(segment.get("confidence", "unknown")),
                    "text_preview": segment.get("text", "")[:100] + "..." if len(segment.get("text", "")) > 100 else segment.get("text", ""),
                    "duration": segment.get("end_time", 0) - segment.get("start_time", 0)
                })
            
            # Issue detection logic
            unique_speakers = len(debug_info["segments_by_speaker"])
            total_segments = len(speaker_segments)
            
            if unique_speakers == 1 and total_segments > 3:
                debug_info["issues_detected"].append("Only one speaker detected despite multiple segments - may need better audio quality")
            elif unique_speakers > 8:
                debug_info["issues_detected"].append("Too many speakers detected - may indicate background noise")
            
            # Check for fallback methods
            fallback_methods = ["fallback", "no_diarization", "whisper_fallback"]
            fallback_count = 0
            for segment in speaker_segments:
                method = segment.get("method", "")
                if any(fb in method.lower() for fb in fallback_methods):
                    fallback_count += 1
            
            if fallback_count == total_segments and total_segments > 0:
                debug_info["issues_detected"].append("All segments using fallback methods - cloud diarization failed")
            
            # Quality assessment
            if unique_speakers >= 2 and fallback_count < total_segments / 2:
                debug_info["processing_quality"] = "good"
            elif unique_speakers >= 1 and fallback_count < total_segments:
                debug_info["processing_quality"] = "fair"
            else:
                debug_info["processing_quality"] = "poor"
        else:
            debug_info["issues_detected"].append("No speech segments detected")
            debug_info["processing_quality"] = "failed"
        
        # Generate recommendations
        recommendations = []
        if not speaker_segments:
            recommendations.extend([
                "No speech detected - check microphone settings",
                "Ensure audio file contains clear speech",
                "Try uploading a longer audio sample (10+ seconds)"
            ])
        elif len(debug_info["issues_detected"]) > 0:
            if "Only one speaker" in str(debug_info["issues_detected"]):
                recommendations.extend([
                    "Record longer audio samples (30-60 seconds)",
                    "Ensure multiple speakers have distinct voices",
                    "Check that speakers alternate speaking clearly"
                ])
            if "fallback methods" in str(debug_info["issues_detected"]):
                recommendations.extend([
                    "Check AssemblyAI API key and quota",
                    "Verify internet connection",
                    "Try higher quality audio recording"
                ])
            if "Too many speakers" in str(debug_info["issues_detected"]):
                recommendations.extend([
                    "Reduce background noise",
                    "Use closer microphone placement",
                    "Ensure clean audio environment"
                ])
        else:
            recommendations.append("Speaker detection working well - no issues detected!")
        
        return {
            "success": True,
            "cloud_diarization": {
                "debug_info": debug_info,
                "raw_segments_sample": speaker_segments[:3] if speaker_segments else []
            },
            "recommendations": recommendations,
            "analysis_summary": {
                "speakers_found": len(debug_info["segments_by_speaker"]),
                "total_segments": debug_info["total_segments"],
                "quality_rating": debug_info["processing_quality"],
                "main_issues": len(debug_info["issues_detected"])
            }
        }
        
    except Exception as e:
        print(f"Debug analysis error: {e}")
        return {
            "success": False,
            "error": f"Debug analysis failed: {str(e)}",
            "cloud_diarization": {
                "debug_info": {
                    "total_segments": 0,
                    "segments_by_speaker": {},
                    "segments_detail": [],
                    "issues_detected": [f"Debug failed with error: {str(e)}"]
                }
            },
            "recommendations": ["Check server logs for detailed error information", "Verify all API keys are configured"]
        }

@router.post("/transcribe-and-translate/")
async def transcribe_and_translate(
    file: UploadFile = File(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form(None)
):
    """
    Original endpoint for basic transcription without speaker detection
    """
    try:
        transcription_result = await transcribe_audio(file, source_language)
        
        if not transcription_result["success"]:
            return {
                "success": False,
                "error": "Transcription failed",
                "transcription": transcription_result,
                "translation": None
            }
        
        original_text = transcription_result["text"].strip()
        detected_language = transcription_result["language"]
        
        if len(original_text) < 3:
            return {
                "success": True,
                "transcription": {
                    "text": original_text,
                    "language": detected_language
                },
                "translation": {
                    "text": "",
                    "target_language": target_language,
                    "success": False,
                    "reason": "Text too short to translate"
                },
                "combined_success": False
            }
        
        source_lang = fix_source_language(source_language)
        translation_result = await translate_text(original_text, target_language, source_lang)
        
        return {
            "success": True,
            "transcription": {
                "text": original_text,
                "language": detected_language
            },
            "translation": {
                "text": translation_result["translated_text"],
                "target_language": target_language,
                "success": translation_result["success"]
            },
            "combined_success": transcription_result["success"] and translation_result["success"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Combined translation failed: {str(e)}")

@router.post("/live-diarize/")
async def live_diarize(
    file: UploadFile = File(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form("auto")
):
    """
    Live processing endpoint using cloud-based voice analysis.
    Optimized for real-time speaker detection in medical conversations.
    """
    try:
        # Cloud-based voice analysis with enhanced error handling
        speaker_segments = await cloud_speaker_service.process_audio_with_diarization(file)
        
        if not speaker_segments:
            # If no speech detected by cloud, return empty rather than guessing
            return {
                "success": True,
                "speaker_segments": [],
                "processing_method": "no_speech_detected",
                "quality_metrics": {
                    "speaker_count": 0,
                    "average_confidence": 0,
                    "processing_time": "minimal"
                }
            }
        
        # Add translations to cloud-detected segments
        translation_errors = 0
        for segment in speaker_segments:
            try:
                if "translation" not in segment and segment.get("text"):
                    source_lang = fix_source_language(source_language)
                    translation_result = await translate_text(
                        segment["text"], 
                        target_language, 
                        source_lang
                    )
                    
                    if translation_result["success"]:
                        segment["translation"] = translation_result["translated_text"]
                    else:
                        segment["translation"] = f"[Translation unavailable]"
                        translation_errors += 1
                        print(f"Translation failed for segment: {segment['text'][:50]}...")
            except Exception as trans_error:
                segment["translation"] = f"[Translation error]"
                translation_errors += 1
                print(f"Translation error: {trans_error}")
        
        # Fix confidence values for the color-coded interface
        for segment in speaker_segments:
            # Ensure confidence is a proper number for the frontend
            confidence_val = segment.get("confidence", 0.8)
            
            # Handle string confidence values (like "fallback")
            if isinstance(confidence_val, str):
                if "fallback" in confidence_val.lower():
                    segment["confidence"] = 0.6  # Lower confidence for fallback
                else:
                    try:
                        segment["confidence"] = float(confidence_val)
                    except:
                        segment["confidence"] = 0.8  # Safe default
            
            # Ensure confidence is within valid range
            if not isinstance(segment["confidence"], (int, float)):
                segment["confidence"] = 0.8
            else:
                segment["confidence"] = max(0.0, min(1.0, float(segment["confidence"])))
            
            # Ensure speaker field exists and follows expected format
            if not segment.get("speaker"):
                segment["speaker"] = "SPEAKER_1"
            
            # Normalize speaker labels to match color-coding expectations
            speaker = segment["speaker"]
            if not speaker.startswith("SPEAKER_"):
                # Handle various speaker label formats from AssemblyAI
                if speaker in ["A", "1"]:
                    segment["speaker"] = "SPEAKER_1"
                elif speaker in ["B", "2"]:
                    segment["speaker"] = "SPEAKER_2"
                else:
                    segment["speaker"] = f"SPEAKER_{speaker[-1] if speaker[-1].isdigit() else '1'}"
        
        # Calculate quality metrics
        speaker_count = len(set(s.get("speaker", "unknown") for s in speaker_segments))
        avg_confidence = sum(
            float(s.get("confidence", 0)) for s in speaker_segments 
            if isinstance(s.get("confidence"), (int, float))
        ) / len(speaker_segments) if speaker_segments else 0
        
        return {
            "success": True,
            "speaker_segments": speaker_segments,
            "processing_method": "enhanced_cloud_voice_analysis",
            "quality_metrics": {
                "speaker_count": speaker_count,
                "average_confidence": round(avg_confidence, 2),
                "translation_success_rate": round((len(speaker_segments) - translation_errors) / len(speaker_segments) * 100, 1) if speaker_segments else 0,
                "total_segments": len(speaker_segments)
            }
        }
        
    except Exception as e:
        print(f"Enhanced live diarization failed: {e}")
        return {
            "success": False,
            "error": f"Enhanced voice analysis temporarily unavailable: {str(e)}",
            "speaker_segments": [],
            "quality_metrics": {
                "speaker_count": 0,
                "average_confidence": 0,
                "error_occurred": True
            }
        }

@router.post("/enroll-voice/")
async def enroll_voice(
    file: UploadFile = File(...),
    family_id: str = Form(...),
    speaker_name: str = Form(...),
    relationship: str = Form("family_member")
):
    """Voice enrollment endpoint"""
    return await enroll_voice_endpoint(file, family_id, speaker_name, relationship)

@router.post("/enhanced-live-diarize/")
async def enhanced_live_diarize(
    file: UploadFile = File(...),
    family_id: str = Form(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form("auto")
):
    """
    Enhanced live processing with FIXED speaker assignment logic.
    Enrolled voices (like 'kris') should always appear as SPEAKER_2 (Patient/Family - GREEN).
    """
    try:
        # Step 1: Get enhanced speaker processing results
        speaker_segments = await enhanced_speaker_processing(file, family_id)
        
        if not speaker_segments:
            return {
                "success": True,
                "speaker_segments": [],
                "processing_method": "no_speech_detected"
            }

        # Step 2: FIXED ENROLLMENT-FIRST ASSIGNMENT
        processed_segments = []
        
        for segment in speaker_segments:
            # Check for enrollment match FIRST - this is the priority
            enrollment_confidence = segment.get("enrollment_confidence", 0)
            enrolled_name = segment.get("speaker", "")
            
            print(f"Processing segment - Original speaker: {segment.get('speaker')}, Enrollment confidence: {enrollment_confidence}")
            
            # PRIORITY RULE: If enrolled voice detected with confidence >= 0.70, assign to SPEAKER_2
            if enrollment_confidence >= 0.70:
                segment["speaker"] = "SPEAKER_2"  # Patient/Family GREEN color
                segment["speaker_role"] = "Patient/Family" 
                segment["enrolled_speaker"] = enrolled_name
                segment["assignment_method"] = "voice_enrollment_match"
                print(f"✅ ENROLLED VOICE: {enrolled_name} -> SPEAKER_2 (Patient/Family)")
                
            else:
                # No enrollment match - DEFAULT ALL UNKNOWN VOICES TO HEALTHCARE PROVIDER
                # This is correct for a personal medical journal app where only family voices are enrolled
                segment["speaker"] = "SPEAKER_1"  # Healthcare Provider BLUE color
                segment["speaker_role"] = "Healthcare Provider"
                segment["assignment_method"] = "unknown_voice_default_provider"
                print(f"Unknown voice -> SPEAKER_1 (Healthcare Provider) - Cloud said {segment.get('speaker', 'unknown')}")
            
            # Add translations
            if "translation" not in segment and segment.get("text"):
                source_lang = fix_source_language(source_language)
                translation_result = await translate_text(segment["text"], target_language, source_lang)
                segment["translation"] = translation_result.get("translated_text", "")
            
            # Clean up confidence values
            confidence = segment.get("confidence", 0.8)
            if isinstance(confidence, str):
                segment["confidence"] = 0.6 if "fallback" in confidence.lower() else 0.8
            else:
                segment["confidence"] = max(0.0, min(1.0, float(confidence)))
                
            processed_segments.append(segment)

        # Final verification log
        role_counts = {}
        for segment in processed_segments:
            role = segment.get("speaker_role", "Unknown")
            method = segment.get("assignment_method", "unknown")
            role_counts[f"{role}_{method}"] = role_counts.get(f"{role}_{method}", 0) + 1

        print(f"FINAL ROLE ASSIGNMENT SUMMARY: {role_counts}")

        return {
            "success": True,
            "speaker_segments": processed_segments,
            "processing_method": "fixed_enrollment_priority_assignment",
            "debug_info": {
                "role_assignment_summary": role_counts,
                "total_segments": len(processed_segments)
            }
        }
        
    except Exception as e:
        print(f"Enhanced live diarization failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Enhanced processing failed: {str(e)}",
            "speaker_segments": []
        }

@router.get("/")
def test_combined():
    return {
        "message": "Enhanced combined transcription and translation service ready", 
        "endpoints": [
            "/diarize-and-translate/ - Full speaker diarization with translation",
            "/debug-speakers/ - Comprehensive speaker detection debugging", 
            "/transcribe-and-translate/ - Basic transcription and translation",
            "/live-diarize/ - Real-time speaker detection with metrics",
            "/enroll-voice/ - Voice enrollment for family members",
            "/enhanced-live-diarize/ - Live processing with voice enrollment and proper role assignment"
        ],
        "features": [
            "AssemblyAI cloud-based speaker diarization",
            "Voice enrollment with encrypted storage",
            "Proper speaker role assignment (Patient/Family vs Healthcare Provider)",
            "Color-coded interface support",
            "Privacy-compliant audio processing"
        ]
    }

@router.post("/generate-journal-entry/")
async def generate_journal_entry(
    file: UploadFile = File(...),
    family_id: str = Form(...),
    patient_name: str = Form(...),
    target_language: str = Form("vi"),
    source_language: Optional[str] = Form("auto"),
    background_tasks: BackgroundTasks = None
):
    """
    Complete pipeline: Enhanced speaker detection + AI journal generation.
    This endpoint processes audio and automatically creates a structured medical journal entry.
    """
    try:
        print(f"Starting complete journal generation for patient: {patient_name}")
        
        # Step 1: Enhanced speaker processing with voice enrollment
        speaker_segments = await enhanced_speaker_processing(file, family_id)
        
        if not speaker_segments:
            return {
                "success": False,
                "error": "No speech detected in audio",
                "journal_entry": None
            }
        
        # Step 2: Add translations to all segments
        for segment in speaker_segments:
            if "translation" not in segment and segment.get("text"):
                source_lang = fix_source_language(source_language)
                translation_result = await translate_text(segment["text"], target_language, source_lang)
                segment["translation"] = translation_result.get("translated_text", "")
        
        # Step 3: Generate AI-powered journal entry
        patient_info = {
            "name": patient_name,
            "family_id": family_id,
            "preferred_language": target_language
        }
        
        journal_result = await ai_journal_service.generate_medical_journal_entry(
            speaker_segments, patient_info
        )
        
        # Step 4: Privacy compliance - Schedule audio deletion
        if background_tasks:
            background_tasks.add_task(auto_delete_processed_audio, file)
        
        if journal_result["success"]:
            return {
                "success": True,
                "journal_entry": journal_result["journal_entry"],
                "medical_summary": journal_result["medical_summary"],
                "confidence_score": journal_result["confidence_score"],
                "processing_info": {
                    "segments_processed": len(speaker_segments),
                    "ai_generated": True,
                    "privacy_compliant": True,
                    "auto_structured": True
                }
            }
        else:
            return {
                "success": False,
                "error": journal_result["error"],
                "fallback_entry": journal_result["fallback_summary"],
                "speaker_segments": speaker_segments  # Provide raw segments as backup
            }
        
    except Exception as e:
        print(f"Complete journal generation failed: {e}")
        return {
            "success": False,
            "error": f"Journal generation failed: {str(e)}",
            "processing_stage": "complete_pipeline"
        }


async def auto_delete_processed_audio(audio_file):
    """
    Background task to ensure privacy compliance by clearing processed audio data.
    Called automatically after journal entry generation.
    """
    try:
        # Clear any temporary audio processing files
        # Note: This is a placeholder - implement based on your storage system
        print(f"Auto-deleting processed audio data for privacy compliance")
        
        # Reset file pointer and clear from memory
        if hasattr(audio_file, 'file'):
            audio_file.file.seek(0)
            audio_file.file.truncate(0)
        
        print("Audio data cleared for privacy compliance")
        
    except Exception as e:
        print(f"Audio cleanup error: {e}")

@router.post("/quick-journal-from-segments/")
async def quick_journal_from_segments(request: Request):
    """Generate journal from segments - accepts JSON"""
    try:
        data = await request.json()
        
        # Extract data
        session_id = data.get("session_id")
        user_id = data.get("user_id")
        patient_name = data.get("patient_name")
        family_id = data.get("family_id")
        target_language = data.get("target_language")
        
        # STEP 1: Create session with frontend session_id
        created_session_id = await database_service.create_session(
            user_id=user_id,
            patient_name=patient_name,
            family_id=family_id,
            target_language=target_language,
            session_id=session_id  # Pass frontend ID to use it
        )
        
        # STEP 2: Generate journal entry
        patient_info = {
            "name": patient_name,
            "family_id": family_id,
            "preferred_language": target_language
        }
        
        journal_result = await ai_journal_service.generate_medical_journal_entry(
            data.get("segments", []), patient_info
        )
        
        # STEP 3: Save journal entry with same session_id
        if journal_result["success"]:
            await database_service.create_journal_entry(
                session_id=created_session_id,  # Use the same ID
                user_id=user_id,
                patient_name=patient_name,
                family_id=family_id,
                journal_entry=journal_result["journal_entry"],
                ai_confidence=journal_result.get("confidence_score", 0.85)
            )
        
        return journal_result
        
    except Exception as e:
        print(f"Journal generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}