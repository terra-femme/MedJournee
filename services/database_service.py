# services/database_service.py
"""
Database service for storing journal entries and managing live sessions.
Uses Supabase (PostgreSQL) database.
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv
import uuid
from supabase import create_client, Client

load_dotenv()

class DatabaseService:
    """Handles all database operations for journal entries and sessions"""

    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        # Use service role key for server-side operations to bypass RLS
        # Falls back to SUPABASE_KEY if service key not available
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        self.supabase: Client = create_client(supabase_url, supabase_key)

    # ==================== SESSION MANAGEMENT ====================

    async def create_session(
        self,
        user_id: str,
        patient_name: str,
        family_id: str,
        target_language: str = "vi",
        session_id: Optional[str] = None
    ) -> str:
        """Create a new live session"""
        if not session_id:
            session_id = f"session-{uuid.uuid4()}"

        self.supabase.table("live_sessions").insert({
            "session_id": session_id,
            "user_id": user_id,
            "patient_name": patient_name,
            "family_id": family_id,
            "target_language": target_language,
            "session_status": "active"
        }).execute()

        print(f"Created session: {session_id}")
        return session_id

    async def update_session_status(
        self,
        session_id: str,
        status: str,
        total_segments: int = 0,
        duration_seconds: int = 0
    ) -> bool:
        """Update session status and metrics"""
        self.supabase.table("live_sessions").update({
            "session_status": status,
            "total_segments": total_segments,
            "duration_seconds": duration_seconds,
            "ended_at": datetime.utcnow().isoformat()
        }).eq("session_id", session_id).execute()
        return True

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session details"""
        result = self.supabase.table("live_sessions") \
            .select("*") \
            .eq("session_id", session_id) \
            .execute()
        return result.data[0] if result.data else None

    # ==================== SEGMENT MANAGEMENT ====================

    async def add_segment(
        self,
        session_id: str,
        segment: Dict[str, Any]
    ) -> bool:
        """Add a conversation segment to the session"""
        segment_id = f"seg-{uuid.uuid4()}"

        try:
            self.supabase.table("session_segments").insert({
                "segment_id": segment_id,
                "session_id": session_id,
                "speaker": segment.get("speaker", "SPEAKER_1"),
                "speaker_role": segment.get("speaker_role", "Unknown"),
                "original_text": segment.get("text", ""),
                "translated_text": segment.get("translation", ""),
                "timestamp_start": segment.get("timestamp_start", 0),
                "timestamp_end": segment.get("timestamp_end", 0),
                "confidence": segment.get("confidence", 0.8),
                "enrollment_match": segment.get("enrollment_match", False),
                "enrollment_confidence": segment.get("enrollment_confidence", 0.0),
                "method": segment.get("method", "cloud_diarization")
            }).execute()
            return True
        except Exception as e:
            print(f"Error adding segment: {e}")
            return False

    async def get_session_segments(self, session_id: str) -> List[Dict]:
        """Get all segments for a session"""
        result = self.supabase.table("session_segments") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("timestamp_start") \
            .execute()
        return result.data

    async def delete_session_segments(self, session_id: str) -> bool:
        """Delete all segments for privacy compliance"""
        self.supabase.table("session_segments") \
            .delete() \
            .eq("session_id", session_id) \
            .execute()
        print(f"Deleted segments for session {session_id} (privacy compliance)")
        return True

    # ==================== JOURNAL ENTRY MANAGEMENT ====================

    async def create_journal_entry(
        self,
        session_id: str,
        user_id: str,
        patient_name: str,
        family_id: str,
        journal_entry: Dict[str, Any],
        ai_confidence: float = 0.85,
        raw_transcript: Optional[str] = None
    ) -> str:
        """Save AI-generated journal entry to database"""

        entry_id = f"entry-{uuid.uuid4()}"

        # Extract data from journal entry structure
        visit_info = journal_entry.get("visit_information", {})
        medical = journal_entry.get("medical_details", {})
        medications = journal_entry.get("medications", [])
        follow_up = journal_entry.get("follow_up_care", {})
        family = journal_entry.get("family_section", {})
        terms = journal_entry.get("medical_terms_explained", {})

        entry_data = {
            "entry_id": entry_id,
            "session_id": session_id,
            "user_id": user_id,
            "patient_name": patient_name,
            "family_id": family_id,
            # Visit information
            "visit_date": visit_info.get("date", datetime.now().strftime("%Y-%m-%d")),
            "provider_name": visit_info.get("provider", "Healthcare Provider"),
            "visit_type": visit_info.get("visit_type", "Medical Visit"),
            "main_reason": visit_info.get("main_reason", ""),
            # Medical details (as JSON)
            "symptoms": json.dumps(medical.get("symptoms", [])),
            "diagnoses": json.dumps(medical.get("diagnoses", [])),
            "treatments": json.dumps(medical.get("treatments", [])),
            "vital_signs": json.dumps(medical.get("vital_signs", {})),
            "test_results": json.dumps(medical.get("test_results", [])),
            # Medications
            "medications": json.dumps(medications),
            # Follow-up
            "follow_up_instructions": json.dumps(follow_up.get("instructions", [])),
            "next_appointments": json.dumps(follow_up.get("appointments", [])),
            "action_items": json.dumps(follow_up.get("action_items", [])),
            # Family section
            "patient_questions": json.dumps(family.get("patient_questions", [])),
            "family_concerns": json.dumps(family.get("family_concerns", [])),
            "family_summary": family.get("notes_for_family", ""),
            # Medical terms
            "medical_terms_explained": json.dumps(terms),
            # Summary
            "visit_summary": journal_entry.get("summary", "Medical visit completed"),
            # Raw transcript (if provided)
            "raw_transcript": raw_transcript,
            # AI metadata
            "ai_confidence": ai_confidence,
            "ai_model": "gpt-4",
            "processing_method": "ai_medical_summarization",
            # Privacy flags
            "consent_given": True,
            "audio_deleted": True,
            "transcripts_deleted": False if raw_transcript else True
        }

        self.supabase.table("journal_entries").insert(entry_data).execute()

        print(f"Created journal entry: {entry_id}")
        return entry_id

    async def create_raw_transcript_entry(
        self,
        session_id: str,
        user_id: str,
        patient_name: str,
        family_id: str,
        segments: List[Dict[str, Any]],
        visit_date: Optional[str] = None
    ) -> str:
        """
        Save raw transcript without AI summarization.

        Use this when user chooses to skip AI processing.
        """
        entry_id = f"entry-{uuid.uuid4()}"

        # Build raw transcript from segments
        transcript_lines = []
        for seg in segments:
            # Enrolled name takes priority; otherwise format "SPEAKER_1" → "Speaker 1".
            # Never fall back to speaker_role — it would expose "Healthcare Provider" as a label.
            raw_label = seg.get("speaker", "SPEAKER_1")
            speaker = (seg.get("enrolled_name")
                       or raw_label.replace("SPEAKER_", "Speaker ").replace("_", " ").title())
            text = seg.get("text", "")
            translation = seg.get("translation", "")

            line = f"{speaker}: {text}"
            if translation and translation != text:
                line += f"\n  → {translation}"
            transcript_lines.append(line)

        raw_transcript = "\n\n".join(transcript_lines)

        entry_data = {
            "entry_id": entry_id,
            "session_id": session_id,
            "user_id": user_id,
            "patient_name": patient_name,
            "family_id": family_id,
            "visit_date": visit_date or datetime.now().strftime("%Y-%m-%d"),
            "provider_name": "Healthcare Provider",
            "visit_type": "Medical Visit",
            "main_reason": "",
            # Empty medical fields
            "symptoms": json.dumps([]),
            "diagnoses": json.dumps([]),
            "treatments": json.dumps([]),
            "vital_signs": json.dumps({}),
            "test_results": json.dumps([]),
            "medications": json.dumps([]),
            "follow_up_instructions": json.dumps([]),
            "next_appointments": json.dumps([]),
            "action_items": json.dumps([]),
            "patient_questions": json.dumps([]),
            "family_concerns": json.dumps([]),
            "family_summary": "Raw transcript saved without AI summarization.",
            "medical_terms_explained": json.dumps({}),
            "visit_summary": "Raw conversation transcript (no AI processing)",
            # Raw transcript
            "raw_transcript": raw_transcript,
            # No AI processing
            "ai_confidence": 0.0,
            "ai_model": None,
            "processing_method": "raw_transcript_only",
            # Privacy flags
            "consent_given": True,
            "audio_deleted": True,
            "transcripts_deleted": False
        }

        try:
            result = self.supabase.table("journal_entries").insert(entry_data).execute()
            print(f"Created raw transcript entry: {entry_id} for session: {session_id}")
            print(f"Database response: {result.data}")
            return entry_id
        except Exception as e:
            print(f"ERROR: Failed to create raw transcript entry: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def get_journal_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a journal entry by ID"""
        result = self.supabase.table("journal_entries") \
            .select("*") \
            .eq("entry_id", entry_id) \
            .execute()

        if result.data:
            return self._parse_journal_entry(result.data[0])
        return None

    async def get_journal_by_session(self, session_id: str) -> Optional[Dict]:
        """Get journal entry by session ID"""
        print(f"Looking up journal for session_id: {session_id}")
        try:
            result = self.supabase.table("journal_entries") \
                .select("*") \
                .eq("session_id", session_id) \
                .execute()

            print(f"Query result: found {len(result.data)} entries")

            if result.data:
                entry = self._parse_journal_entry(result.data[0])
                print(f"Returning entry: {entry.get('entry_id')}, method: {entry.get('processing_method')}")
                return entry
            else:
                print(f"No journal entry found for session: {session_id}")
            return None
        except Exception as e:
            print(f"ERROR in get_journal_by_session: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def delete_journal_entry(self, session_id: str) -> bool:
        """Delete a journal entry and its associated live session"""
        self.supabase.table("journal_entries").delete().eq("session_id", session_id).execute()
        self.supabase.table("live_sessions").delete().eq("session_id", session_id).execute()
        return True

    async def list_user_journals(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get all journal entries for a user"""
        result = self.supabase.table("journal_entries") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("visit_date", desc=True) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        return [self._parse_journal_entry(entry) for entry in result.data]

    def _parse_journal_entry(self, entry: Dict) -> Dict:
        """Parse JSON fields in journal entry"""
        json_fields = [
            'symptoms', 'diagnoses', 'treatments', 'vital_signs', 'test_results',
            'medications', 'follow_up_instructions', 'next_appointments', 'action_items',
            'patient_questions', 'family_concerns', 'medical_terms_explained'
        ]

        for field in json_fields:
            if field in entry and entry[field]:
                try:
                    if isinstance(entry[field], str):
                        entry[field] = json.loads(entry[field])
                except:
                    entry[field] = [] if field != 'vital_signs' and field != 'medical_terms_explained' else {}

        return entry

# Global instance
database_service = DatabaseService()
