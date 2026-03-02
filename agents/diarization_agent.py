# agents/diarization_agent.py
"""
AGENT 2: DIARIZATION AGENT

Identifies who is speaking in the audio.

Input: Audio file + family_id for voice enrollment
Output: DiarizationResult with speaker-labeled segments

Speaker Assignment Rules:
- Enrolled speakers → Patient/Family (GREEN in UI) with their name
- Non-enrolled speakers → Healthcare Provider (BLUE in UI)
- Falls back to position-based assignment if no enrollment

Voice enrollment matching is ENABLED when family_id is provided.
"""

import os
import asyncio
import time
import requests
import tempfile
from typing import Optional, List, Dict, Tuple
from dotenv import load_dotenv

from models.schemas import (
    DiarizationResult,
    SpeakerSegment,
    SpeakerRole
)

load_dotenv()


class DiarizationAgent:
    """
    Handles speaker identification using AssemblyAI cloud service.

    Integrates with voice enrollment to recognize enrolled family members.

    Usage:
        agent = DiarizationAgent()
        result = await agent.diarize(audio_file, family_id="family-001")

        for segment in result.segments:
            print(f"{segment.speaker_role}: {segment.text}")
            if segment.enrollment_match:
                print(f"  Matched enrolled speaker: {segment.enrolled_name}")
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with AssemblyAI API key"""
        self.api_key = api_key or os.getenv("ASSEMBLYAI_API_KEY")
        if not self.api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found in environment")

        self.base_url = "https://api.assemblyai.com/v2"

        # Voice enrollment service (lazy loaded)
        self._voice_service = None

    @property
    def voice_service(self):
        """Lazy load voice enrollment service"""
        if self._voice_service is None:
            try:
                from services.voice_enrollment_service import voice_enrollment_service
                self._voice_service = voice_enrollment_service
            except ImportError:
                print("[Diarization] Voice enrollment service not available")
                self._voice_service = None
        return self._voice_service

    async def diarize(
        self,
        audio_file,
        family_id: Optional[str] = None
    ) -> DiarizationResult:
        """
        Process audio and identify speakers.

        Args:
            audio_file: File-like object with audio data
            family_id: Optional family ID for voice enrollment matching

        Returns:
            DiarizationResult with speaker-labeled segments
        """
        try:
            # Store audio for later enrollment matching
            await audio_file.seek(0)
            audio_content = await audio_file.read()
            await audio_file.seek(0)

            # Step 1: Upload audio
            upload_url = await self._upload_audio(audio_file)
            if not upload_url:
                return DiarizationResult(
                    success=False,
                    error="Failed to upload audio"
                )

            # Step 2: Request transcription with diarization
            transcript_id = await self._request_transcription(upload_url)
            if not transcript_id:
                return DiarizationResult(
                    success=False,
                    error="Failed to start transcription"
                )

            # Step 3: Wait for completion
            transcript_result = await self._wait_for_completion(transcript_id)
            if not transcript_result:
                return DiarizationResult(
                    success=False,
                    error="Transcription timed out"
                )

            # Step 4: Parse speaker segments
            raw_segments = self._parse_speaker_segments(transcript_result)

            if not raw_segments:
                return DiarizationResult(
                    success=True,
                    segments=[],
                    total_speakers=0,
                    error=None
                )

            # Step 5: Apply default roles first
            final_segments = self._apply_default_roles(raw_segments)

            # Step 6: Match against enrolled speakers (if family_id provided)
            if family_id and self.voice_service:
                final_segments = await self._match_enrolled_speakers(
                    final_segments, audio_content, family_id
                )

            unique_speakers = len(set(s.speaker for s in final_segments))

            return DiarizationResult(
                success=True,
                segments=final_segments,
                total_speakers=unique_speakers,
                error=None
            )

        except Exception as e:
            return DiarizationResult(
                success=False,
                error=f"Diarization failed: {str(e)}"
            )

    async def _upload_audio(self, audio_file) -> Optional[str]:
        """Upload audio to AssemblyAI"""
        try:
            await audio_file.seek(0)
            audio_data = await audio_file.read()

            headers = {
                "authorization": self.api_key,
                "content-type": "application/octet-stream"
            }

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.base_url}/upload",
                    headers=headers,
                    data=audio_data,
                    timeout=60
                )
            )

            if response.status_code == 200:
                return response.json().get("upload_url")
            else:
                print(f"Upload failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Upload error: {e}")
            return None

    async def _request_transcription(self, upload_url: str) -> Optional[str]:
        """Request transcription with speaker diarization"""
        headers = {
            "authorization": self.api_key,
            "content-type": "application/json"
        }

        data = {
            "audio_url": upload_url,
            "speaker_labels": True,
            "speakers_expected": 2,
            "punctuate": True,
            "format_text": True,
            "speech_model": "best"
        }

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.base_url}/transcript",
                    headers=headers,
                    json=data,
                    timeout=30
                )
            )

            if response.status_code == 200:
                return response.json().get("id")
            else:
                print(f"Transcription request failed: {response.status_code}")
                return None

        except Exception as e:
            print(f"Transcription request error: {e}")
            return None

    async def _wait_for_completion(
        self,
        transcript_id: str,
        max_wait: int = 300
    ) -> Optional[Dict]:
        """Poll for transcription completion"""
        headers = {"authorization": self.api_key}

        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        f"{self.base_url}/transcript/{transcript_id}",
                        headers=headers,
                        timeout=10
                    )
                )

                if response.status_code == 200:
                    result = response.json()
                    status = result.get("status")

                    if status == "completed":
                        return result
                    elif status == "error":
                        print(f"Transcription error: {result.get('error')}")
                        return None
                    else:
                        await asyncio.sleep(2)
                else:
                    return None

            except Exception as e:
                print(f"Polling error: {e}")
                await asyncio.sleep(2)

        return None

    def _parse_speaker_segments(self, transcript_result: Dict) -> List[SpeakerSegment]:
        """Parse AssemblyAI response into speaker segments"""
        segments = []

        utterances = transcript_result.get("utterances", [])
        if utterances:
            for utterance in utterances:
                text = utterance.get("text", "").strip()
                if not text:
                    continue

                speaker_letter = utterance.get("speaker", "A")
                speaker_map = {"A": "1", "B": "2", "C": "3", "D": "4"}
                speaker_num = speaker_map.get(speaker_letter, "1")

                segments.append(SpeakerSegment(
                    speaker=f"SPEAKER_{speaker_num}",
                    speaker_role=SpeakerRole.UNKNOWN,
                    text=text,
                    detected_language="",
                    start_time=utterance.get("start", 0) / 1000,
                    end_time=utterance.get("end", 0) / 1000,
                    confidence=utterance.get("confidence", 0.8)
                ))

            return segments

        # Fallback: use words
        words = transcript_result.get("words", [])
        if words:
            return self._words_to_segments(words)

        # Last resort: full text
        full_text = transcript_result.get("text", "").strip()
        if full_text:
            segments.append(SpeakerSegment(
                speaker="SPEAKER_1",
                speaker_role=SpeakerRole.UNKNOWN,
                text=full_text,
                start_time=0,
                end_time=30,
                confidence=0.5
            ))

        return segments

    def _words_to_segments(self, words: List[Dict]) -> List[SpeakerSegment]:
        """Group words by speaker into segments"""
        if not words:
            return []

        segments = []
        current_speaker = None
        current_words = []
        current_start = None
        current_end = None

        for word in words:
            speaker_letter = word.get("speaker", "A")
            speaker_map = {"A": "1", "B": "2", "C": "3", "D": "4"}
            speaker = f"SPEAKER_{speaker_map.get(speaker_letter, '1')}"

            if speaker != current_speaker:
                if current_words and current_speaker:
                    segments.append(SpeakerSegment(
                        speaker=current_speaker,
                        speaker_role=SpeakerRole.UNKNOWN,
                        text=" ".join(current_words),
                        start_time=(current_start or 0) / 1000,
                        end_time=(current_end or 0) / 1000,
                        confidence=0.7
                    ))

                current_speaker = speaker
                current_words = [word.get("text", "")]
                current_start = word.get("start", 0)
                current_end = word.get("end", 0)
            else:
                current_words.append(word.get("text", ""))
                current_end = word.get("end", current_end)

        if current_words and current_speaker:
            segments.append(SpeakerSegment(
                speaker=current_speaker,
                speaker_role=SpeakerRole.UNKNOWN,
                text=" ".join(current_words),
                start_time=(current_start or 0) / 1000,
                end_time=(current_end or 0) / 1000,
                confidence=0.7
            ))

        return segments

    def _apply_default_roles(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        Apply default speaker roles.
        SPEAKER_1 = Healthcare Provider (BLUE)
        SPEAKER_2 = Patient/Family (GREEN)
        """
        for segment in segments:
            if segment.speaker == "SPEAKER_2":
                segment.speaker_role = SpeakerRole.PATIENT_FAMILY
            else:
                segment.speaker_role = SpeakerRole.HEALTHCARE_PROVIDER

        return segments

    async def _match_enrolled_speakers(
        self,
        segments: List[SpeakerSegment],
        audio_content: bytes,
        family_id: str
    ) -> List[SpeakerSegment]:
        """
        Match segments against enrolled family voices.

        If an enrolled speaker is matched:
        - Set enrollment_match = True
        - Set enrolled_name = their name
        - Override speaker_role to PATIENT_FAMILY (enrolled = family member)

        Args:
            segments: Speaker segments from cloud diarization
            audio_content: Raw audio bytes
            family_id: Family ID to check enrollments against

        Returns:
            Segments with enrollment info and corrected roles
        """
        try:
            import librosa
            import soundfile as sf
            import io
            import numpy as np
            import subprocess

            # Try to load audio directly first
            audio_array = None
            sr = 16000

            try:
                audio_array, sr = librosa.load(io.BytesIO(audio_content), sr=16000, mono=True)
            except Exception as native_error:
                print(f"[Diarization] Native audio load failed: {native_error}, trying FFmpeg conversion...")

                # Save to temp file and convert with FFmpeg (handles WebM, MP4, etc.)
                temp_input = tempfile.NamedTemporaryFile(delete=False, suffix='.webm')
                temp_input.write(audio_content)
                temp_input.close()

                temp_output = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                temp_output.close()

                try:
                    cmd = [
                        'ffmpeg', '-i', temp_input.name,
                        '-ar', '16000',
                        '-ac', '1',
                        '-c:a', 'pcm_s16le',
                        '-y', temp_output.name,
                        '-loglevel', 'error'
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                    if result.returncode == 0:
                        audio_array, sr = librosa.load(temp_output.name, sr=16000, mono=True)
                        print(f"[Diarization] FFmpeg conversion successful: {len(audio_array)/sr:.1f}s")
                    else:
                        print(f"[Diarization] FFmpeg failed: {result.stderr}")
                finally:
                    try:
                        os.unlink(temp_input.name)
                        os.unlink(temp_output.name)
                    except:
                        pass

            if audio_array is None or len(audio_array) == 0:
                print("[Diarization] Could not load audio for enrollment matching")
                return segments

            print(f"[Diarization] Matching {len(segments)} segments against enrolled speakers for family {family_id}")

            # Track which cloud speakers map to enrolled names
            speaker_to_enrolled: Dict[str, Tuple[str, float]] = {}

            for i, segment in enumerate(segments):
                # Extract segment audio
                start_sample = max(0, int(segment.start_time * sr))
                end_sample = min(len(audio_array), int(segment.end_time * sr))

                if end_sample - start_sample < sr * 0.5:  # Less than 0.5s
                    continue

                segment_audio = audio_array[start_sample:end_sample]

                # Save segment to temp file for voice matching
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                    sf.write(temp_file.name, segment_audio, sr)
                    temp_path = temp_file.name

                try:
                    # Create async file wrapper
                    class AsyncFileWrapper:
                        def __init__(self, path):
                            self.path = path
                            self.file = None
                        async def seek(self, pos):
                            if self.file is None:
                                self.file = open(self.path, 'rb')
                            self.file.seek(pos)
                        async def read(self):
                            if self.file is None:
                                self.file = open(self.path, 'rb')
                            return self.file.read()
                        def close(self):
                            if self.file:
                                self.file.close()

                    wrapper = AsyncFileWrapper(temp_path)
                    enrolled_name, confidence = await self.voice_service.identify_enrolled_speaker(
                        wrapper, family_id
                    )
                    wrapper.close()

                    # Accept matches with confidence >= 0.65 (lowered from 0.70)
                    # Voice enrollment service now returns matches at 0.65 threshold
                    if enrolled_name and confidence >= 0.65:
                        # Track this speaker mapping
                        current_best = speaker_to_enrolled.get(segment.speaker, (None, 0.0))
                        if confidence > current_best[1]:
                            speaker_to_enrolled[segment.speaker] = (enrolled_name, confidence)

                        print(f"[Diarization] Segment {i} ({segment.speaker}): Matched '{enrolled_name}' with {confidence:.2f} confidence")

                finally:
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

            # Apply enrollment matches to all segments
            for segment in segments:
                if segment.speaker in speaker_to_enrolled:
                    enrolled_name, confidence = speaker_to_enrolled[segment.speaker]
                    segment.enrollment_match = True
                    segment.enrolled_name = enrolled_name
                    # CRITICAL: Override role - enrolled speakers are ALWAYS family members
                    segment.speaker_role = SpeakerRole.PATIENT_FAMILY
                    print(f"[Diarization] {segment.speaker} → '{enrolled_name}' (Patient/Family)")

            matches = sum(1 for s in segments if s.enrollment_match)
            print(f"[Diarization] Enrollment matching complete: {matches}/{len(segments)} segments matched")

            return segments

        except Exception as e:
            print(f"[Diarization] Enrollment matching error: {e}")
            import traceback
            traceback.print_exc()
            return segments


# =============================================================================
# STANDALONE FUNCTION
# =============================================================================

_agent: Optional[DiarizationAgent] = None


def get_agent() -> DiarizationAgent:
    """Get or create the global diarization agent"""
    global _agent
    if _agent is None:
        _agent = DiarizationAgent()
    return _agent


async def process_audio_with_diarization(audio_file, family_id: Optional[str] = None) -> List[Dict]:
    """Backward-compatible function"""
    agent = get_agent()
    result = await agent.diarize(audio_file, family_id)

    if not result.success:
        return []

    return [
        {
            "speaker": s.speaker,
            "speaker_role": s.speaker_role.value,
            "text": s.text,
            "detected_language": s.detected_language,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "confidence": s.confidence,
            "enrollment_match": s.enrollment_match,
            "enrolled_name": s.enrolled_name
        }
        for s in result.segments
    ]
