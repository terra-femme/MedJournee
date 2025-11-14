# services/cloud_speaker_service.py
import requests
import os
import asyncio
import time
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()

class CloudSpeakerService:
    def __init__(self):
        self.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        self.base_url = "https://api.assemblyai.com/v2"
        
        if not self.api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")
    
    async def process_audio_with_diarization(self, audio_file) -> List[Dict[str, Any]]:
        """
        Process audio with cloud-based speaker diarization.
        Audio is automatically deleted by AssemblyAI after processing.
        """
        try:
            print("Starting cloud diarization process...")
            
            # Step 1: Upload audio file
            upload_url = await self._upload_audio(audio_file)
            print(f"Audio uploaded successfully")
            
            # Step 2: Request transcription with speaker diarization
            transcript_id = await self._request_transcription(upload_url)
            print(f"Transcription requested: {transcript_id}")
            
            # Step 3: Poll for completion
            transcript_result = await self._wait_for_completion(transcript_id)
            print("Transcription completed successfully")
            
            # Step 4: Parse speaker segments
            speaker_segments = self._parse_speaker_segments(transcript_result)
            print(f"Parsed {len(speaker_segments)} speaker segments")
            
            # Debug: Print speaker distribution
            speaker_counts = {}
            for segment in speaker_segments:
                speaker = segment.get('speaker', 'UNKNOWN')
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
            
            print(f"Speaker distribution: {speaker_counts}")
            
            return speaker_segments
            
        except Exception as e:
            print(f"Cloud diarization error: {e}")
            return []
    
    async def _upload_audio(self, audio_file) -> str:
        """Upload audio file and get temporary URL"""
        await audio_file.seek(0)
        audio_data = await audio_file.read()
        
        print(f"Uploading audio: {len(audio_data)} bytes, type: {audio_file.content_type}")
        
        headers = {
            "authorization": self.api_key,
            "content-type": "application/octet-stream"
        }
        
        # Use asyncio to make non-blocking request
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(
                f"{self.base_url}/upload",
                headers=headers,
                data=audio_data
            )
        )
        
        print(f"Upload response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Upload successful: {result}")
            return result["upload_url"]
        else:
            raise Exception(f"Upload failed: {response.status_code} - {response.text}")
    
    async def _request_transcription(self, upload_url: str) -> str:
        """Request transcription with speaker diarization enabled"""
        headers = {
            "authorization": self.api_key,
            "content-type": "application/json"
        }
        
        # Enhanced settings for better speaker detection
        data = {
            "audio_url": upload_url,
            "speaker_labels": True,  # Enable speaker diarization
            "speakers_expected": 2,  # Tell AssemblyAI to expect 2 speakers
            "auto_chapters": False,
            "filter_profanity": False,
            "format_text": True,
            "punctuate": True,
            "dual_channel": False,
            "speech_model": "best"  # Use highest accuracy model
        }
        
        print(f"Requesting transcription with data: {data}")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(
                f"{self.base_url}/transcript",
                headers=headers,
                json=data
            )
        )
        
        print(f"Transcription request response: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Transcription started: {result}")
            return result["id"]
        else:
            raise Exception(f"Transcription request failed: {response.status_code} - {response.text}")
    
    async def _wait_for_completion(self, transcript_id: str, max_wait_time: int = 300) -> Dict:
        """Poll for transcription completion"""
        headers = {"authorization": self.api_key}
        
        start_time = time.time()
        while time.time() - start_time < max_wait_time:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    f"{self.base_url}/transcript/{transcript_id}",
                    headers=headers
                )
            )
            
            if response.status_code == 200:
                result = response.json()
                status = result["status"]
                
                if status == "completed":
                    print(f"Completed transcript keys: {list(result.keys())}")
                    return result
                elif status == "error":
                    raise Exception(f"Transcription failed: {result.get('error')}")
                else:
                    # Still processing, wait before polling again
                    await asyncio.sleep(2)
            else:
                raise Exception(f"Status check failed: {response.status_code}")
        
        raise Exception("Transcription timed out")
    
    def _parse_speaker_segments(self, transcript_result: Dict) -> List[Dict[str, Any]]:
        """Parse AssemblyAI response into speaker segments with robust fallback"""
        segments = []
        
        # Check if we have any text at all
        full_text = transcript_result.get("text", "").strip()
        if not full_text:
            print("No text in transcript result")
            return []
        
        print(f"Full transcript text: {full_text[:100]}...")
        
        # Try to get utterances (best case)
        if "utterances" in transcript_result and transcript_result["utterances"]:
            print("Using utterances for speaker segmentation")
            utterances = transcript_result["utterances"]
            
            for i, utterance in enumerate(utterances):
                if not utterance.get("text", "").strip():
                    continue
                    
                # Get speaker label
                speaker_letter = utterance.get("speaker", "A")
                speaker_mapping = {"A": "1", "B": "2", "C": "3", "D": "4"}
                speaker_number = speaker_mapping.get(speaker_letter, "1")
                
                segments.append({
                    "speaker": f"SPEAKER_{speaker_number}",
                    "text": utterance["text"].strip(),
                    "start_time": utterance.get("start", 0) / 1000,
                    "end_time": utterance.get("end", 1000) / 1000,
                    "confidence": utterance.get("confidence", 0.95),
                    "method": "cloud_diarization"
                })
            
            return segments
        
        # Try words-level parsing (second best)
        if "words" in transcript_result and transcript_result["words"]:
            print("Using words for speaker segmentation")
            return self._parse_words_to_segments(transcript_result)
        
        # Last resort: return full text as single speaker
        print("No speaker information available - using full text as single speaker")
        return [{
            "speaker": "SPEAKER_1",
            "text": full_text,
            "start_time": 0,
            "end_time": 30,  # Estimate
            "confidence": 0.8,
            "method": "no_diarization_fallback"
        }]
    
    def _parse_words_to_segments(self, transcript_result: Dict) -> List[Dict[str, Any]]:
        """Fallback: group words by speaker"""
        words = transcript_result.get("words", [])
        if not words:
            return []
        
        segments = []
        current_speaker = None
        current_text = []
        current_start = None
        current_end = None
        
        for word in words:
            speaker_letter = word.get('speaker', 'A')
            speaker_mapping = {"A": "1", "B": "2", "C": "3", "D": "4"}
            speaker_number = speaker_mapping.get(speaker_letter, "1")
            speaker = f"SPEAKER_{speaker_number}"
            
            if speaker != current_speaker:
                # Save previous segment
                if current_text and current_speaker:
                    segments.append({
                        "speaker": current_speaker,
                        "text": " ".join(current_text),
                        "start_time": (current_start or 0) / 1000,
                        "end_time": (current_end or 1000) / 1000,
                        "confidence": 0.9,
                        "method": "word_level_diarization"
                    })
                
                # Start new segment
                current_speaker = speaker
                current_text = [word.get("text", "")]
                current_start = word.get("start", 0)
                current_end = word.get("end", 1000)
            else:
                current_text.append(word.get("text", ""))
                current_end = word.get("end", current_end)
        
        # Add final segment
        if current_text and current_speaker:
            segments.append({
                "speaker": current_speaker,
                "text": " ".join(current_text),
                "start_time": (current_start or 0) / 1000,
                "end_time": (current_end or 1000) / 1000,
                "confidence": 0.9,
                "method": "word_level_diarization"
            })
        
        return segments

# Global instance
cloud_speaker_service = CloudSpeakerService()