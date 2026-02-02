# services/realtime_transcription_service.py
"""
Hybrid Real-Time Transcription Service for MedJournee

Strategy:
1. DURING RECORDING: Use OpenAI Whisper API for instant transcription (2-3 sec latency)
   - No speaker labels, just fast text + translation
   - Gives immediate visual feedback to users

2. AFTER RECORDING: Send full audio to AssemblyAI for speaker diarization
   - Accurate speaker detection
   - Merges with existing transcripts

This approach provides the best of both worlds:
- Real-time feedback during conversation
- Accurate speaker attribution for journal generation
"""

import openai
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
from dotenv import load_dotenv
import numpy as np
import librosa

load_dotenv()

class RealtimeTranscriptionService:
    """
    Provides instant transcription during recording,
    then enhances with speaker diarization after recording stops.
    """

    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Session storage for pending diarization
        self.pending_sessions = {}

        # Track speaker assignments by session
        self.session_speakers = {}

        # Speaker assignment thresholds
        self.speaker_similarity_threshold = 0.75
        self.confidence_threshold = 0.80
    
    async def transcribe_chunk_instant(
        self, 
        audio_file,
        source_language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        FAST transcription using OpenAI Whisper API.
        Returns text within 2-3 seconds. No speaker detection.
        
        Use this DURING recording for instant feedback.
        """
        import tempfile
        import subprocess
        
        temp_input = None
        temp_output = None
        
        try:
            # Read the uploaded file content
            audio_content = await audio_file.read()
            await audio_file.seek(0)
            
            # Skip if audio is too small (likely silence)
            if len(audio_content) < 5000:  # Less than 5KB
                return {
                    "success": True,
                    "text": "",
                    "is_empty": True,
                    "reason": "Audio too short/quiet"
                }
            
            # CRITICAL FIX: MediaRecorder chunks after the first are NOT self-contained
            # They need FFmpeg conversion to become valid audio files
            content_type = audio_file.content_type or "audio/webm"
            base_content_type = content_type.split(";")[0].strip()
            
            # Determine input extension
            extension_map = {
                "audio/webm": "webm",
                "audio/mp4": "mp4",
                "audio/mpeg": "mp3",
                "audio/wav": "wav",
                "audio/ogg": "ogg",
            }
            input_ext = extension_map.get(base_content_type, "webm")
            
            # Write chunk to temp file
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{input_ext}')
            temp_input.write(audio_content)
            temp_input.close()
            
            # Convert to WAV using FFmpeg (ensures valid audio regardless of chunk state)
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            temp_output.close()
            
            try:
                result = subprocess.run([
                    'ffmpeg', '-i', temp_input.name,
                    '-ar', '16000',
                    '-ac', '1',
                    '-c:a', 'pcm_s16le',
                    '-y',
                    temp_output.name
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0 and os.path.exists(temp_output.name) and os.path.getsize(temp_output.name) > 1000:
                    # Use converted WAV
                    with open(temp_output.name, 'rb') as f:
                        audio_content = f.read()
                    filename = "audio.wav"
                    base_content_type = "audio/wav"
                    print(f"[Instant] FFmpeg converted to WAV: {len(audio_content)} bytes")
                else:
                    # Conversion failed, try original (might work for first chunk)
                    filename = f"audio.{input_ext}"
                    print(f"[Instant] FFmpeg failed, using original: {len(audio_content)} bytes")
                    
            except subprocess.TimeoutExpired:
                filename = f"audio.{input_ext}"
                print(f"[Instant] FFmpeg timeout, using original")
            except FileNotFoundError:
                # FFmpeg not installed - try original
                filename = f"audio.{input_ext}"
                print(f"[Instant] FFmpeg not found, using original")
            
            file_tuple = (filename, audio_content, base_content_type)
            
            print(f"[Instant] Sending to OpenAI: {filename}, {len(audio_content)} bytes, {base_content_type}")
            
            # Prepare API call parameters
            api_params = {
                "model": "whisper-1",
                "file": file_tuple,
                "response_format": "json"
            }
            
            # Add language hint if provided
            if source_language and source_language not in ["auto", "automatic", ""]:
                api_params["language"] = source_language
            
            # Make the API call - this is fast! (~2-3 seconds)
            response = self.openai_client.audio.transcriptions.create(**api_params)
            
            transcribed_text = response.text.strip()
            
            # Filter out Whisper hallucinations (common with short/quiet audio)
            hallucination_phrases = [
                "thank you", "thanks for watching", "subscribe", 
                "like and subscribe", "see you next time",
                "music", "applause", "silence"
            ]
            
            text_lower = transcribed_text.lower()
            if any(phrase in text_lower for phrase in hallucination_phrases) and len(transcribed_text) < 50:
                return {
                    "success": True,
                    "text": "",
                    "is_empty": True,
                    "reason": "Filtered potential hallucination"
                }
            
            return {
                "success": True,
                "text": transcribed_text,
                "is_empty": len(transcribed_text) < 3,
                "language": source_language or "auto-detected"
            }
            
        except Exception as e:
            print(f"Instant transcription error: {e}")
            return {
                "success": False,
                "text": "",
                "error": str(e),
                "is_empty": True
            }
        finally:
            # Cleanup temp files
            for tf in [temp_input, temp_output]:
                if tf and hasattr(tf, 'name'):
                    try:
                        os.unlink(tf.name)
                    except:
                        pass
    
    async def transcribe_and_translate_instant(
        self,
        audio_file,
        target_language: str = "vi",
        source_language: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fast transcription + translation for real-time display.
        When session_id is provided, attempts to identify speaker.
        """
        from services.translation_service import translate_text

        # Step 1: Get speaker ID if session tracking is active
        if session_id and session_id in self.session_speakers:
            speaker_info = await self.identify_current_speaker(audio_file, session_id)
        else:
            # Default behavior without speaker tracking
            speaker_info = {
                "speaker_id": "SPEAKER_1",
                "speaker_role": "Healthcare Provider",
                "speaker_name": "Unknown",
                "confidence": 0.5,
                "is_enrolled": False
            }

        # Step 2: Fast transcription
        transcription_result = await self.transcribe_chunk_instant(audio_file, source_language)

        if not transcription_result["success"] or transcription_result.get("is_empty"):
            return {
                "success": True,
                "has_speech": False,
                "text": "",
                "translation": "",
                "speaker_info": speaker_info,
                "reason": transcription_result.get("reason", "No speech detected")
            }

        original_text = transcription_result["text"]

        # Step 3: Translate
        try:
            # Fix source language for Google Translate
            src_lang = None if source_language in ["auto", "automatic", "", None] else source_language

            translation_result = await translate_text(original_text, target_language, src_lang)
            translated_text = translation_result.get("translated_text", "")
        except Exception as e:
            print(f"Translation error: {e}")
            translated_text = f"[Translation error: {str(e)}]"

        return {
            "success": True,
            "has_speech": True,
            "text": original_text,
            "translation": translated_text,
            "speaker_info": speaker_info,
            "timestamp": datetime.now().isoformat()
        }
    
    def store_audio_for_diarization(
        self,
        session_id: str,
        audio_data: bytes,
        transcript_segments: List[Dict]
    ):
        """
        Store audio and transcripts for post-recording diarization.
        Called when user stops recording.
        """
        if session_id not in self.pending_sessions:
            self.pending_sessions[session_id] = {
                "audio_chunks": [],
                "transcripts": [],
                "created_at": datetime.now()
            }
        
        self.pending_sessions[session_id]["audio_chunks"].append(audio_data)
        self.pending_sessions[session_id]["transcripts"].extend(transcript_segments)
    
    async def finalize_with_diarization(
        self,
        session_id: str,
        full_audio_blob: bytes,
        instant_transcripts: List[Dict],
        family_id: str
    ) -> Dict[str, Any]:
        """
        After recording stops, run speaker diarization on full audio
        and merge with instant transcripts.
        
        This adds accurate speaker labels to the already-transcribed text.
        """
        from services.cloud_speaker_service import cloud_speaker_service
        from services.voice_enrollment_service import voice_enrollment_service
        import tempfile
        import os as os_module
        
        try:
            print(f"Starting post-recording diarization for session {session_id}")
            print(f"Audio size: {len(full_audio_blob)} bytes, Transcripts: {len(instant_transcripts)}")
            
            # Save audio to temp file for AssemblyAI
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                temp_file.write(full_audio_blob)
                temp_path = temp_file.name
            
            try:
                # Create a file-like object for the cloud service
                class TempFileWrapper:
                    def __init__(self, path):
                        self.path = path
                        self.file = open(path, 'rb')
                        self.filename = "audio.webm"
                        self.content_type = "audio/webm"
                    
                    async def read(self):
                        return self.file.read()
                    
                    async def seek(self, pos):
                        self.file.seek(pos)
                    
                    def close(self):
                        self.file.close()
                
                file_wrapper = TempFileWrapper(temp_path)
                
                # Run AssemblyAI diarization (this takes 15-30 seconds but runs AFTER recording)
                diarized_segments = await cloud_speaker_service.process_audio_with_diarization(file_wrapper)
                file_wrapper.close()
                
                print(f"AssemblyAI returned {len(diarized_segments)} diarized segments")
                
                if not diarized_segments:
                    # Diarization failed - return instant transcripts with default speaker
                    print("Diarization failed, using instant transcripts with default speakers")
                    return self._apply_default_speakers(instant_transcripts)
                
                # Merge diarized segments with voice enrollment
                enhanced_segments = await self._enhance_with_enrollment(
                    diarized_segments, family_id, temp_path
                )
                
                return {
                    "success": True,
                    "segments": enhanced_segments,
                    "method": "post_recording_diarization",
                    "diarization_segments": len(diarized_segments),
                    "final_segments": len(enhanced_segments)
                }
                
            finally:
                # Clean up temp file
                try:
                    os_module.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            print(f"Post-recording diarization error: {e}")
            import traceback
            print(traceback.format_exc())
            
            # Fallback: return instant transcripts with alternating speakers
            return self._apply_default_speakers(instant_transcripts)
    
    async def _enhance_with_enrollment(
        self,
        diarized_segments: List[Dict],
        family_id: str,
        audio_path: str
    ) -> List[Dict]:
        """
        Enhance diarized segments with voice enrollment matching.
        Enrolled voices become SPEAKER_2 (Patient/Family - GREEN).
        Unknown voices become SPEAKER_1 (Healthcare Provider - BLUE).
        """
        from services.voice_enrollment_service import voice_enrollment_service
        import librosa
        import numpy as np
        
        try:
            # Load full audio for segment extraction
            audio_array, sr = librosa.load(audio_path, sr=16000, mono=True)
        except Exception as e:
            print(f"Could not load audio for enrollment matching: {e}")
            return self._apply_role_to_segments(diarized_segments)
        
        enhanced = []
        
        for segment in diarized_segments:
            start_time = segment.get("start_time", 0)
            end_time = segment.get("end_time", start_time + 3)
            
            # Extract segment audio
            start_sample = int(start_time * sr)
            end_sample = int(end_time * sr)
            
            if start_sample >= len(audio_array) or end_sample <= start_sample:
                segment["speaker"] = "SPEAKER_1"
                segment["speaker_role"] = "Healthcare Provider"
                enhanced.append(segment)
                continue
            
            segment_audio = audio_array[start_sample:min(end_sample, len(audio_array))]
            
            # Try to match with enrolled voice
            try:
                enrolled_name, confidence = await voice_enrollment_service.identify_enrolled_speaker(
                    segment_audio, family_id
                )
                
                if enrolled_name and confidence >= 0.70:
                    segment["speaker"] = "SPEAKER_2"
                    segment["speaker_role"] = "Patient/Family"
                    segment["enrolled_speaker"] = enrolled_name
                    segment["enrollment_confidence"] = confidence
                else:
                    segment["speaker"] = "SPEAKER_1"
                    segment["speaker_role"] = "Healthcare Provider"
                    segment["enrollment_confidence"] = confidence
                    
            except Exception as e:
                print(f"Enrollment matching error for segment: {e}")
                segment["speaker"] = "SPEAKER_1"
                segment["speaker_role"] = "Healthcare Provider"
            
            enhanced.append(segment)
        
        return enhanced
    
    def _apply_default_speakers(self, transcripts: List[Dict]) -> Dict[str, Any]:
        """
        Apply alternating speakers to transcripts when diarization fails.
        """
        segments = []
        current_speaker = "SPEAKER_1"
        
        for i, transcript in enumerate(transcripts):
            # Alternate speakers as a reasonable fallback
            if i > 0:
                current_speaker = "SPEAKER_2" if current_speaker == "SPEAKER_1" else "SPEAKER_1"
            
            segments.append({
                "speaker": current_speaker,
                "speaker_role": "Healthcare Provider" if current_speaker == "SPEAKER_1" else "Patient/Family",
                "text": transcript.get("text", ""),
                "translation": transcript.get("translation", ""),
                "confidence": 0.5,
                "method": "alternating_fallback"
            })
        
        return {
            "success": True,
            "segments": segments,
            "method": "alternating_fallback",
            "note": "Speaker detection unavailable - using alternating assignment"
        }
    
    def _apply_role_to_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Apply speaker roles based on AssemblyAI labels (A, B, etc.)
        """
        for segment in segments:
            speaker = segment.get("speaker", "SPEAKER_1")

            # SPEAKER_1 / A = Healthcare Provider (BLUE)
            # SPEAKER_2 / B = Patient/Family (GREEN)
            if speaker in ["SPEAKER_1", "A", "1"]:
                segment["speaker"] = "SPEAKER_1"
                segment["speaker_role"] = "Healthcare Provider"
            else:
                segment["speaker"] = "SPEAKER_2"
                segment["speaker_role"] = "Patient/Family"

        return segments

    def initialize_session_speakers(self, session_id: str, family_id: str):
        """
        Initialize speaker tracking for a session
        """
        self.session_speakers[session_id] = {
            "family_id": family_id,
            "active_speakers": {},  # Maps voice signatures to speaker IDs
            "speaker_assignments": {},  # Tracks assigned speaker roles
            "last_speaker": None,
            "timestamps": []
        }

    async def identify_current_speaker(
        self,
        audio_file,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Identify the speaker in the current audio chunk
        """
        from services.voice_enrollment_service import voice_enrollment_service

        try:
            # Load audio for feature extraction
            await audio_file.seek(0)
            audio_data = await audio_file.read()

            # Create a file-like object for voice enrollment service
            class TempAudioWrapper:
                def __init__(self, data):
                    self.data = data
                    self.position = 0

                async def read(self):
                    return self.data

                async def seek(self, pos):
                    self.position = pos

            temp_wrapper = TempAudioWrapper(audio_data)
            enrolled_speaker, confidence = await voice_enrollment_service.identify_enrolled_speaker(
                temp_wrapper,
                self.session_speakers[session_id]["family_id"]
            )

            # If we recognized an enrolled voice, assign it consistently
            if enrolled_speaker and confidence >= 0.70:
                # Assign as SPEAKER_2 (family/patient) if it's an enrolled speaker
                speaker_id = "SPEAKER_2"
                speaker_role = "Patient/Family"
                speaker_name = enrolled_speaker
            else:
                # Unknown speaker - likely healthcare provider
                speaker_id = "SPEAKER_1"
                speaker_role = "Healthcare Provider"
                speaker_name = "Unknown"

            # Store in session for continuity
            current_session = self.session_speakers.get(session_id, {})
            if current_session:
                current_session["last_speaker"] = {
                    "id": speaker_id,
                    "role": speaker_role,
                    "name": speaker_name,
                    "confidence": confidence
                }

            return {
                "speaker_id": speaker_id,
                "speaker_role": speaker_role,
                "speaker_name": speaker_name,
                "confidence": confidence,
                "is_enrolled": bool(enrolled_speaker)
            }

        except Exception as e:
            print(f"Speaker identification error: {e}")
            # Fallback to default speaker
            return {
                "speaker_id": "SPEAKER_1",
                "speaker_role": "Healthcare Provider",
                "speaker_name": "Unknown",
                "confidence": 0.0,
                "is_enrolled": False
            }

    async def transcribe_and_translate_instant_with_speaker(
        self,
        audio_file,
        target_language: str = "vi",
        source_language: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fast transcription + translation + speaker ID for real-time display.
        """
        from services.translation_service import translate_text

        # Step 1: Get speaker ID if session tracking is active
        if session_id and session_id in self.session_speakers:
            speaker_info = await self.identify_current_speaker(audio_file, session_id)
        else:
            # Default behavior without speaker tracking
            speaker_info = {
                "speaker_id": "SPEAKER_1",
                "speaker_role": "Healthcare Provider",
                "speaker_name": "Unknown",
                "confidence": 0.5,
                "is_enrolled": False
            }

        # Step 2: Fast transcription
        # Create a new file object for transcription since we consumed audio data
        await audio_file.seek(0)
        transcription_result = await self.transcribe_chunk_instant(audio_file, source_language)

        if not transcription_result["success"] or transcription_result.get("is_empty"):
            return {
                "success": True,
                "has_speech": False,
                "text": "",
                "translation": "",
                "speaker_info": speaker_info,
                "reason": transcription_result.get("reason", "No speech detected")
            }

        original_text = transcription_result["text"]

        # Step 3: Translate
        try:
            # Fix source language for Google Translate
            src_lang = None if source_language in ["auto", "automatic", "", None] else source_language

            translation_result = await translate_text(original_text, target_language, src_lang)
            translated_text = translation_result.get("translated_text", "")
        except Exception as e:
            print(f"Translation error: {e}")
            translated_text = f"[Translation error: {str(e)}]"

        return {
            "success": True,
            "has_speech": True,
            "text": original_text,
            "translation": translated_text,
            "speaker_info": speaker_info,
            "timestamp": datetime.now().isoformat()
        }


# Global instance
realtime_transcription_service = RealtimeTranscriptionService()
