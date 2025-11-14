# services/database_service.py
"""
Database service for storing journal entries and managing live sessions.
Uses your existing Google Cloud SQL database (mjournee).
"""

import pymysql
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv
import uuid

load_dotenv()

class DatabaseService:
    """Handles all database operations for journal entries and sessions"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv("GOOGLE_SQL_HOST"),
            'user': os.getenv("GOOGLE_SQL_USER"),
            'password': os.getenv("GOOGLE_SQL_PASSWORD"),
            'database': os.getenv("GOOGLE_SQL_DATABASE"),
            'charset': 'utf8mb4'
        }
    
    def get_connection(self):
        """Create database connection"""
        return pymysql.connect(**self.db_config)
    
    # ==================== SESSION MANAGEMENT ====================
    
    async def create_session(
        self,
        user_id: str,
        patient_name: str,
        family_id: str,
        target_language: str = "vi",
        session_id: Optional[str] = None  # Add this parameter
    ) -> str:
        """Create a new live session"""
        if not session_id:  # Only generate if not provided
            session_id = f"session-{uuid.uuid4()}"
        
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO live_sessions 
                (session_id, user_id, patient_name, family_id, target_language, session_status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                """
                cursor.execute(sql, (session_id, user_id, patient_name, family_id, target_language))
            conn.commit()
            print(f"✅ Created session: {session_id}")
            return session_id
        finally:
            conn.close()
    
    async def update_session_status(
        self,
        session_id: str,
        status: str,
        total_segments: int = 0,
        duration_seconds: int = 0
    ) -> bool:
        """Update session status and metrics"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                UPDATE live_sessions 
                SET session_status = %s, 
                    total_segments = %s,
                    duration_seconds = %s,
                    ended_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """
                cursor.execute(sql, (status, total_segments, duration_seconds, session_id))
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session details"""
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT * FROM live_sessions WHERE session_id = %s"
                cursor.execute(sql, (session_id,))
                return cursor.fetchone()
        finally:
            conn.close()
    
    # ==================== SEGMENT MANAGEMENT ====================
    
    async def add_segment(
        self,
        session_id: str,
        segment: Dict[str, Any]
    ) -> bool:
        """Add a conversation segment to the session"""
        segment_id = f"seg-{uuid.uuid4()}"
        
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO session_segments 
                (segment_id, session_id, speaker, speaker_role, original_text, 
                 translated_text, timestamp_start, timestamp_end, confidence,
                 enrollment_match, enrollment_confidence, method)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(sql, (
                    segment_id,
                    session_id,
                    segment.get("speaker", "SPEAKER_1"),
                    segment.get("speaker_role", "Unknown"),
                    segment.get("text", ""),
                    segment.get("translation", ""),
                    segment.get("timestamp_start", 0),
                    segment.get("timestamp_end", 0),
                    segment.get("confidence", 0.8),
                    segment.get("enrollment_match", False),
                    segment.get("enrollment_confidence", 0.0),
                    segment.get("method", "cloud_diarization")
                ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding segment: {e}")
            return False
        finally:
            conn.close()
    
    async def get_session_segments(self, session_id: str) -> List[Dict]:
        """Get all segments for a session"""
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = """
                SELECT * FROM session_segments 
                WHERE session_id = %s 
                ORDER BY timestamp_start ASC
                """
                cursor.execute(sql, (session_id,))
                return cursor.fetchall()
        finally:
            conn.close()
    
    async def delete_session_segments(self, session_id: str) -> bool:
        """Delete all segments for privacy compliance"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "DELETE FROM session_segments WHERE session_id = %s"
                cursor.execute(sql, (session_id,))
            conn.commit()
            print(f"🔒 Deleted segments for session {session_id} (privacy compliance)")
            return True
        finally:
            conn.close()
    
    # ==================== JOURNAL ENTRY MANAGEMENT ====================
    
    async def create_journal_entry(
        self,
        session_id: str,
        user_id: str,
        patient_name: str,
        family_id: str,
        journal_entry: Dict[str, Any],
        ai_confidence: float = 0.85
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
        
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO journal_entries (
                    entry_id, session_id, user_id, patient_name, family_id,
                    visit_date, provider_name, visit_type, main_reason,
                    symptoms, diagnoses, treatments, vital_signs, test_results,
                    medications, follow_up_instructions, next_appointments, action_items,
                    patient_questions, family_concerns, family_summary,
                    medical_terms_explained, visit_summary,
                    ai_confidence, ai_model, processing_method,
                    consent_given, audio_deleted, transcripts_deleted
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                """
                
                cursor.execute(sql, (
                    entry_id,
                    session_id,
                    user_id,
                    patient_name,
                    family_id,
                    # Visit information
                    visit_info.get("date", datetime.now().strftime("%Y-%m-%d")),
                    visit_info.get("provider", "Healthcare Provider"),
                    visit_info.get("visit_type", "Medical Visit"),
                    visit_info.get("main_reason", ""),
                    # Medical details (as JSON)
                    json.dumps(medical.get("symptoms", [])),
                    json.dumps(medical.get("diagnoses", [])),
                    json.dumps(medical.get("treatments", [])),
                    json.dumps(medical.get("vital_signs", {})),
                    json.dumps(medical.get("test_results", [])),
                    # Medications
                    json.dumps(medications),
                    # Follow-up
                    json.dumps(follow_up.get("instructions", [])),
                    json.dumps(follow_up.get("appointments", [])),
                    json.dumps(follow_up.get("action_items", [])),
                    # Family section
                    json.dumps(family.get("patient_questions", [])),
                    json.dumps(family.get("family_concerns", [])),
                    family.get("notes_for_family", ""),
                    # Medical terms
                    json.dumps(terms),
                    # Summary
                    journal_entry.get("summary", "Medical visit completed"),
                    # AI metadata
                    ai_confidence,
                    "gpt-4",
                    "ai_medical_summarization",
                    # Privacy flags
                    True,  # consent_given
                    True,  # audio_deleted
                    True   # transcripts_deleted
                ))
            conn.commit()
            print(f"✅ Created journal entry: {entry_id}")
            return entry_id
        finally:
            conn.close()
    
    async def get_journal_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a journal entry by ID"""
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT * FROM journal_entries WHERE entry_id = %s"
                cursor.execute(sql, (entry_id,))
                entry = cursor.fetchone()
                
                if entry:
                    # Parse JSON fields back to Python objects
                    entry = self._parse_journal_entry(entry)
                
                return entry
        finally:
            conn.close()
    
    async def get_journal_by_session(self, session_id: str) -> Optional[Dict]:
        """Get journal entry by session ID"""
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT * FROM journal_entries WHERE session_id = %s"
                cursor.execute(sql, (session_id,))
                entry = cursor.fetchone()
                
                if entry:
                    entry = self._parse_journal_entry(entry)
                
                return entry
        finally:
            conn.close()
    
    async def list_user_journals(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get all journal entries for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = """
                SELECT * FROM journal_entries 
                WHERE user_id = %s 
                ORDER BY visit_date DESC, created_at DESC 
                LIMIT %s
                """
                cursor.execute(sql, (user_id, limit))
                entries = cursor.fetchall()
                
                # Parse JSON fields for each entry
                return [self._parse_journal_entry(entry) for entry in entries]
        finally:
            conn.close()
    
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
                    entry[field] = json.loads(entry[field])
                except:
                    entry[field] = [] if field != 'vital_signs' and field != 'medical_terms_explained' else {}
        
        # Convert dates to strings
        if 'visit_date' in entry and entry['visit_date']:
            entry['visit_date'] = entry['visit_date'].strftime("%Y-%m-%d")
        
        return entry

# Global instance
database_service = DatabaseService()