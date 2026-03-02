# routes/enrollment.py
"""
Voice Enrollment API Routes

Provides endpoints for:
- Enrolling family member voices
- Listing enrolled speakers
- Deleting enrollments
- Testing voice recognition
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import os
from dotenv import load_dotenv
from supabase import create_client

from services.voice_enrollment_service import voice_enrollment_service

load_dotenv()

router = APIRouter()

# Supabase client for listing enrollments
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)


@router.post("/enroll")
async def enroll_voice(
    audio: UploadFile = File(..., description="Audio file with 15-20 seconds of clear speech"),
    family_id: str = Form(..., description="Family identifier"),
    speaker_name: str = Form(..., description="Name of the person being enrolled"),
    relationship: str = Form(default="family_member", description="Relationship: provider, patient, family_member")
):
    """
    Enroll a family member's voice for speaker identification.

    Requirements:
    - 15-20 seconds of clear speech
    - One person speaking
    - Minimal background noise

    Supported relationships:
    - provider: Healthcare provider/doctor
    - patient: The patient being cared for
    - family_member: Family member (caregiver, translator, etc.)
    """
    if not audio.filename:
        raise HTTPException(status_code=400, detail="No audio file provided")

    if not family_id or not speaker_name:
        raise HTTPException(status_code=400, detail="family_id and speaker_name are required")

    # Validate relationship
    valid_relationships = ["provider", "patient", "family_member"]
    if relationship not in valid_relationships:
        relationship = "family_member"

    print(f"Enrollment request: {speaker_name} ({relationship}) for family {family_id}")

    result = await voice_enrollment_service.enroll_family_voice(
        audio_file=audio,
        family_id=family_id,
        speaker_name=speaker_name,
        relationship=relationship
    )

    if result["success"]:
        return JSONResponse(content=result, status_code=201)
    else:
        return JSONResponse(content=result, status_code=400)


@router.get("/list/{family_id}")
async def list_enrollments(family_id: str):
    """
    List all enrolled speakers for a family.

    Returns enrollment metadata (not voice profiles).
    """
    try:
        result = supabase.table("voice_enrollments") \
            .select("id, speaker_name, relationship, quality_score, sample_count, enrollment_date, active") \
            .eq("family_id", family_id) \
            .eq("active", True) \
            .order("enrollment_date", desc=True) \
            .execute()

        return {
            "family_id": family_id,
            "enrollments": result.data,
            "count": len(result.data)
        }
    except Exception as e:
        print(f"Error listing enrollments: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list enrollments: {str(e)}")


@router.delete("/delete/{enrollment_id}")
async def delete_enrollment(enrollment_id: str, family_id: str):
    """
    Delete a voice enrollment.

    Soft deletes by setting active=False (preserves audit trail).
    """
    try:
        # Verify the enrollment belongs to the family
        check = supabase.table("voice_enrollments") \
            .select("id, family_id") \
            .eq("id", enrollment_id) \
            .eq("family_id", family_id) \
            .execute()

        if not check.data:
            raise HTTPException(status_code=404, detail="Enrollment not found")

        # Soft delete
        supabase.table("voice_enrollments") \
            .update({"active": False}) \
            .eq("id", enrollment_id) \
            .execute()

        return {"success": True, "message": "Enrollment deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting enrollment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete enrollment: {str(e)}")


@router.post("/test-recognition")
async def test_voice_recognition(
    audio: UploadFile = File(..., description="Audio sample to test"),
    family_id: str = Form(..., description="Family identifier")
):
    """
    Test voice recognition against enrolled speakers.

    Returns the matched speaker name and confidence score.
    Useful for verifying enrollments work correctly.
    """
    if not audio.filename:
        raise HTTPException(status_code=400, detail="No audio file provided")

    matched_name, confidence = await voice_enrollment_service.identify_enrolled_speaker(
        audio_input=audio,
        family_id=family_id
    )

    return {
        "matched_speaker": matched_name,
        "confidence": round(confidence, 3),
        "is_match": matched_name is not None and confidence >= 0.70,
        "threshold": 0.70
    }


@router.get("/health")
async def enrollment_health():
    """Health check for enrollment service"""
    return {
        "status": "healthy",
        "service": "voice_enrollment",
        "features": {
            "audio_formats": ["webm", "wav", "mp4", "m4a", "aac"],
            "min_duration_seconds": 15,
            "recommended_duration_seconds": 20,
            "match_threshold": 0.70
        }
    }
