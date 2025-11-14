# routes/live_translation.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from services.whisper_service import transcribe_audio
from services.translation_service import translate_text
from typing import Dict, List
import uuid
from datetime import datetime
from services.ai_journal_service import ai_journal_service
from pydantic import BaseModel
from services.database_service import database_service

router = APIRouter()

# In-memory session storage (replace with Redis/database in production)
active_sessions: Dict[str, Dict] = {}
completed_sessions: Dict[str, Dict] = {}

class LiveSessionManager:
    """Manages live translation sessions with automatic journal generation"""
    
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, user_id: str, patient_name: str, family_id: str, target_language: str) -> str:
        """Create new live session"""
        session_id = str(uuid.uuid4())
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "patient_name": patient_name,
            "family_id": family_id,
            "target_language": target_language,
            "started_at": datetime.now(),
            "status": "active",
            "speaker_segments": [],
            "last_activity": datetime.now(),
            "journal_entry": None
        }
        
        self.sessions[session_id] = session_data
        active_sessions[session_id] = session_data
        
        return session_id
    
    def add_segment(self, session_id: str, segment: Dict):
        """Add new transcribed segment to session"""
        if session_id in self.sessions:
            self.sessions[session_id]["speaker_segments"].append(segment)
            self.sessions[session_id]["last_activity"] = datetime.now()
            
            # Auto-delete transcription after brief period (privacy)
            self._schedule_segment_cleanup(session_id, len(self.sessions[session_id]["speaker_segments"]) - 1)
    
    def _schedule_segment_cleanup(self, session_id: str, segment_index: int):
        """Schedule deletion of raw transcription text for privacy"""
        import asyncio
        async def cleanup():
            await asyncio.sleep(10)  # Keep for 10 seconds then delete
            try:
                if session_id in self.sessions:
                    segments = self.sessions[session_id]["speaker_segments"]
                    if segment_index < len(segments):
                        # Keep only summary info, delete raw text
                        segments[segment_index]["raw_text_deleted"] = True
                        segments[segment_index]["original_text"] = "[DELETED FOR PRIVACY]"
            except:
                pass
        
        asyncio.create_task(cleanup())
    
    async def end_session(self, session_id: str) -> Dict:
        """End session and generate journal entry"""
        if session_id not in self.sessions:
            return {"success": False, "error": "Session not found"}
        
        session = self.sessions[session_id]
        session["status"] = "processing_journal"
        session["ended_at"] = datetime.now()
        
        # Generate AI journal entry from collected segments
        try:
            patient_info = {
                "name": session["patient_name"],
                "family_id": session["family_id"],
                "preferred_language": session["target_language"]
            }
            
            journal_result = await ai_journal_service.generate_medical_journal_entry(
                session["speaker_segments"], 
                patient_info
            )
            
            if journal_result["success"]:
                session["journal_entry"] = journal_result["journal_entry"]

                await database_service.create_journal_entry(
                    session_id=session_id,
                    user_id=session["user_id"],
                    patient_name=session["patient_name"],
                    family_id=session["family_id"],
                    journal_entry=journal_result["journal_entry"],
                    ai_confidence=journal_result.get("confidence_score", 0.85)
                )

                session["confidence_score"] = journal_result["confidence_score"]
                session["status"] = "completed"
                
                # Move to completed sessions
                completed_sessions[session_id] = session
                
                # Clean up speaker segments for privacy (keep only journal)
                session["speaker_segments"] = []  # Delete raw conversation
                
                return {
                    "success": True,
                    "journal_entry_id": session_id,
                    "journal_created": True,
                    "message": "Session ended and journal entry created automatically"
                }
            else:
                session["status"] = "journal_failed"
                return {
                    "success": False,
                    "error": "Failed to generate journal entry",
                    "fallback_available": True
                }
                
        except Exception as e:
            session["status"] = "error"
            return {
                "success": False,
                "error": f"Journal generation error: {str(e)}"
            }
    
    def get_session_journal(self, session_id: str) -> Dict:
        """Get the generated journal entry for a session"""
        if session_id in completed_sessions:
            session = completed_sessions[session_id]
            return {
                "success": True,
                "journal_entry": session.get("journal_entry"),
                "confidence_score": session.get("confidence_score", 0.5),
                "session_info": {
                    "patient_name": session["patient_name"],
                    "date": session["started_at"].strftime("%Y-%m-%d"),
                    "duration": str(session.get("ended_at", datetime.now()) - session["started_at"])
                }
            }
        
        return {"success": False, "error": "Journal entry not found"}

# Global session manager
session_manager = LiveSessionManager()

class SessionStartRequest(BaseModel):
    user_id: str
    patient_name: str
    family_id: str
    target_language: str = "vi"

@router.post("/start-live-session/")
async def start_live_session(
    user_id: str = Form(...),
    patient_name: str = Form(...),
    family_id: str = Form(...),
    target_language: str = Form("vi")
):
    """Start live session - accepts form data"""
    session_id = session_manager.create_session(
        user_id,
        patient_name,
        family_id,
        target_language
    )
    return {
        "success": True,
        "session_id": session_id,
        "message": f"Live session started for {patient_name}",
        "auto_journal": True
    }


@router.post("/add-live-segment/{session_id}")
async def add_live_segment(
    session_id: str,
    segment_data: Dict
):
    """Add a transcribed segment to the live session"""
    
    # Add timestamp if not present
    if "timestamp" not in segment_data:
        segment_data["timestamp"] = datetime.now().isoformat()
    
    session_manager.add_segment(session_id, segment_data)
    
    return {
        "success": True,
        "segment_added": True,
        "privacy_note": "Raw text will be auto-deleted in 10 seconds"
    }

@router.post("/end-live-session/{session_id}")
async def end_live_session(session_id: str, background_tasks: BackgroundTasks):
    """End live session and generate journal entry automatically"""
    
    result = await session_manager.end_session(session_id)
    
    if result["success"]:
        # Clean up session data in background for privacy
        background_tasks.add_task(cleanup_session_data, session_id)
    
    return result

@router.get("/list-journal-entries/{user_id}")
async def list_user_journal_entries(user_id: str):
    """List all journal entries for a user"""
    try:
        # Get entries from DATABASE, not in-memory sessions
        entries = await database_service.list_user_journals(user_id, limit=50)
        
        # Format for frontend
        user_entries = []
        for entry in entries:
            user_entries.append({
                "session_id": entry["session_id"],
                "patient_name": entry["patient_name"],
                "date": entry["visit_date"],
                "visit_type": entry.get("visit_type", "Medical Visit"),
                "provider": entry.get("provider_name", "Healthcare Provider"),
                "summary": entry.get("visit_summary", "")
            })
        
        return {
            "success": True,
            "journal_entries": user_entries,
            "total_entries": len(user_entries)
        }
    except Exception as e:
        print(f"Failed to list journals: {e}")
        return {
            "success": False,
            "error": str(e),
            "journal_entries": []
        }

async def cleanup_session_data(session_id: str):
    """Background task to clean up session data for privacy"""
    try:
        if session_id in active_sessions:
            del active_sessions[session_id]
        
        # Keep completed journal but ensure no raw audio/text remains
        if session_id in completed_sessions:
            session = completed_sessions[session_id]
            session["speaker_segments"] = []  # Delete any remaining segments
            session["raw_data_deleted"] = True
            
        print(f"Session {session_id} data cleaned for privacy compliance")
        
    except Exception as e:
        print(f"Session cleanup error: {e}")

# Integration with existing WebSocket handler
@router.websocket("/ws/live-journal/{session_id}")
async def websocket_live_journal(websocket: WebSocket, session_id: str):
    """WebSocket for live session updates with journal generation"""
    await websocket.accept()
    
    try:
        while True:
            # Receive audio chunk or control message
            message = await websocket.receive_json()
            
            if message.get("type") == "audio_segment":
                # Process audio segment (existing logic)
                # Then add to session
                segment_data = {
                    "speaker": message.get("speaker", "SPEAKER_1"),
                    "text": message.get("text", ""),
                    "translation": message.get("translation", ""),
                    "confidence": message.get("confidence", 0.8)
                }
                
                session_manager.add_segment(session_id, segment_data)
                
                # Send acknowledgment
                await websocket.send_json({
                    "type": "segment_processed",
                    "session_id": session_id,
                    "auto_journal_building": True
                })
                
            elif message.get("type") == "end_session":
                # End session and generate journal
                result = await session_manager.end_session(session_id)
                
                await websocket.send_json({
                    "type": "session_ended",
                    "journal_generated": result["success"],
                    "journal_entry_id": session_id if result["success"] else None,
                    "message": "Your medical visit journal entry has been created automatically!"
                })
                
                break
                
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
        # Auto-end session on disconnect
        await session_manager.end_session(session_id)

# Add this to routes/live_translation.py

@router.get("/debug/entries/{user_id}")
async def debug_entries(user_id: str):
    """Debug endpoint to check what's in the database"""
    try:
        entries = await database_service.list_user_journals(user_id, limit=50)
        
        return {
            "count": len(entries),
            "entries": entries,
            "user_id": user_id
        }
    except Exception as e:
        return {
            "error": str(e),
            "count": 0,
            "entries": []
        }
    
@router.get("/get-journal/{session_id}")
async def get_session_journal(session_id: str):
    """Get journal entry by session ID"""
    try:
        journal_entry = await database_service.get_journal_by_session(session_id)
        
        if journal_entry:
            return {
                "success": True,
                "journal_entry": journal_entry
            }
        else:
            return {
                "success": False,
                "error": "Journal entry not found"
            }
    except Exception as e:
        print(f"Failed to get journal: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    
@router.put("/update-journal/{session_id}")
async def update_journal_entry(session_id: str, request: Request):
    """Update journal entry fields with DATE FORMAT CONVERSION"""
    try:
        data = await request.json()
        import json
        from datetime import datetime
        
        conn = database_service.get_connection()
        
        field_mapping = {
            "visit_date": "visit_date",
            "patient_name": "patient_name",
            "visit_type": "visit_type",
            "provider_name": "provider_name",
            "main_reason": "main_reason",
            "symptoms": "symptoms",
            "diagnoses": "diagnoses",
            "treatments": "treatments",
            "vital_signs": "vital_signs",
            "medications": "medications",
            "follow_up_instructions": "follow_up_instructions",
            "next_appointments": "next_appointments",
            "family_summary": "family_summary"
        }
        
        update_fields = []
        update_values = []
        
        for frontend_field, db_column in field_mapping.items():
            if frontend_field in data and frontend_field != 'session_id':
                value = data[frontend_field]
                
                # DATE CONVERSION FIX
                if frontend_field == "visit_date" and value:
                    try:
                        # Convert "October 1, 2025" to "2025-10-01"
                        date_obj = datetime.strptime(value, "%B %d, %Y")
                        value = date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            # Fallback: try ISO format
                            date_obj = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            value = date_obj.strftime("%Y-%m-%d")
                        except:
                            # If parsing fails, skip this field
                            print(f"Date parsing failed for: {value}")
                            continue
                
                # Convert arrays/lists to JSON
                elif frontend_field in ["symptoms", "diagnoses", "treatments", "medications", 
                                       "follow_up_instructions", "next_appointments"]:
                    if isinstance(value, list):
                        value = json.dumps(value)
                    elif isinstance(value, str) and value.strip() and not value.startswith('['):
                        # Text with bullets - convert to array
                        if '•' in value:
                            items = [item.strip() for item in value.split('•') if item.strip()]
                            value = json.dumps(items)
                
                # Convert vital signs to JSON
                elif frontend_field == "vital_signs":
                    if isinstance(value, dict):
                        value = json.dumps(value)
                    elif isinstance(value, str) and not value.startswith('{'):
                        value = json.dumps({"note": value})
                
                update_fields.append(f"{db_column} = %s")
                update_values.append(value)
        
        if not update_fields:
            return {"success": False, "error": "No valid fields to update"}
        
        update_values.append(session_id)
        
        try:
            with conn.cursor() as cursor:
                sql = f"""
                UPDATE journal_entries 
                SET {', '.join(update_fields)},
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """
                cursor.execute(sql, tuple(update_values))
            conn.commit()
            
            return {
                "success": True,
                "message": "Journal entry updated successfully"
            }
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Update journal error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }

@router.put("/update-journal-notes/{session_id}")
async def update_journal_notes(session_id: str, request: Request):
    """
    Auto-save personal notes for a journal entry.
    Called every 2 seconds when user types in notes field.
    """
    try:
        data = await request.json()
        personal_notes = data.get("personal_notes", "")
        
        conn = database_service.get_connection()
        try:
            with conn.cursor() as cursor:
                # Check if personal_notes column exists, if not we'll need to add it
                sql = """
                UPDATE journal_entries 
                SET personal_notes = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """
                cursor.execute(sql, (personal_notes, session_id))
            conn.commit()
            
            return {
                "success": True,
                "message": "Notes saved"
            }
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Update notes error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# router = APIRouter()

# # Simple in-memory session storage (for development)
# active_sessions = {}

# @router.post("/start-session/")
# async def start_translation_session(
#     user_id: str = Form(...),
#     source_language: str = Form("en"),
#     target_language: str = Form("vi")
# ):
#     """Start a new live translation session"""
#     session_id = str(uuid.uuid4())
    
#     active_sessions[session_id] = {
#         "user_id": user_id,
#         "source_language": source_language,
#         "target_language": target_language,
#         "started_at": datetime.now(),
#         "status": "active"
#     }
    
#     return {
#         "success": True,
#         "session_id": session_id,
#         "message": "Translation session started"
#     }

# @router.post("/process-audio/{session_id}")
# async def process_live_audio(
#     session_id: str,
#     file: UploadFile = File(...)
# ):
#     """Process audio chunk for live translation"""
#     if session_id not in active_sessions:
#         raise HTTPException(status_code=404, detail="Session not found")
    
#     session = active_sessions[session_id]
    
#     try:
#         # Transcribe audio
#         transcription = await transcribe_audio(file, session["source_language"])
        
#         if not transcription["success"] or not transcription["text"].strip():
#             return {
#                 "status": "no_speech_detected",
#                 "transcription": "",
#                 "translation": ""
#             }
        
#         # Translate text
#         translation = await translate_text(
#             transcription["text"], 
#             session["target_language"],
#             session["source_language"]
#         )
        
#         return {
#             "status": "success",
#             "transcription": transcription["text"],
#             "translation": translation["translated_text"],
#             "timestamp": datetime.now().isoformat()
#         }
        
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

# @router.post("/stop-session/{session_id}")
# async def stop_translation_session(session_id: str):
#     """Stop translation session"""
#     if session_id in active_sessions:
#         del active_sessions[session_id]
#         return {"status": "session_stopped"}
#     return {"status": "session_not_found"}

# @router.get("/")
# def test_live_translation():
#     return {"message": "Live translation service ready"}