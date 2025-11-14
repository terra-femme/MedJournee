# services/voice_enrollment_service.py - FIXED for Universal Mobile Support
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import os
import pymysql
from cryptography.fernet import Fernet
import io
import librosa
import soundfile as sf
import json
import uuid
import tempfile
import subprocess

def cosine_similarity_simple(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """Calculate cosine similarity without sklearn"""
    if len(embedding1.shape) > 1:
        embedding1 = embedding1.flatten()
    if len(embedding2.shape) > 1:
        embedding2 = embedding2.flatten()
    
    dot_product = np.dot(embedding1, embedding2)
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return float(dot_product / (norm1 * norm2))

class VoiceEnrollmentService:
    """Universal mobile audio support for voice enrollment"""
    
    def __init__(self):
        # FIXED: Database config
        self.db_config = {
            'host': os.getenv("GOOGLE_SQL_HOST", "35.188.10.95"),
            'user': os.getenv("GOOGLE_SQL_USER", "user001"),
            'password': os.getenv("GOOGLE_SQL_PASSWORD", "0000"),
            'database': os.getenv("GOOGLE_SQL_DATABASE", "mjournee"),
            'charset': 'utf8mb4'
        }
        
        encryption_key = os.getenv("VOICE_ENCRYPTION_KEY")
        if not encryption_key:
            encryption_key = Fernet.generate_key()
            print(f"Generated encryption key: {encryption_key.decode()}")
        else:
            encryption_key = encryption_key.encode()
            
        self.cipher = Fernet(encryption_key)
        
        self.enrollment_threshold = 0.80
        self.unknown_threshold = 0.70
        
        # Check FFmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=5)
            self.ffmpeg_available = True
            print("FFmpeg available")
        except:
            self.ffmpeg_available = False
            print("FFmpeg not available - using native processing")
    
    def get_db_connection(self):
        """Create database connection"""
        return pymysql.connect(**self.db_config)
    
    async def load_audio_universal(self, audio_input, target_sr=16000) -> Tuple[np.ndarray, int]:
        """
        FIXED: Universal audio loader for ALL mobile formats
        Handles: webm, mp4, aac, wav, m4a (iOS/Android/Desktop)
        """
        # Handle numpy array input directly (for segments)
        if isinstance(audio_input, np.ndarray):
            return audio_input, target_sr
        
        # Handle file-like objects
        await audio_input.seek(0)
        audio_data = await audio_input.read()
        
        # Try native Python libraries FIRST (faster, more reliable)
        try:
            audio_array, sr = librosa.load(io.BytesIO(audio_data), sr=target_sr, mono=True)
            print(f"Native audio load successful: {len(audio_array)/sr:.1f}s")
            return audio_array, sr
        except Exception as native_error:
            print(f"Native load failed: {native_error}, trying FFmpeg...")
        
        # Fallback to FFmpeg for exotic formats
        if not self.ffmpeg_available:
            print("No FFmpeg available and native load failed")
            return np.array([]), target_sr
        
        # FFmpeg conversion
        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix='.webm')
        temp_input.write(audio_data)
        temp_input.close()
        input_path = temp_input.name
        
        temp_output = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        temp_output.close()
        output_path = temp_output.name
        
        try:
            cmd = [
                'ffmpeg', '-i', input_path,
                '-ar', str(target_sr),
                '-ac', '1',
                '-c:a', 'pcm_s16le',
                '-y',
                output_path,  # FIXED: Output file must be specified
                '-loglevel', 'error'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"FFmpeg failed: {result.stderr}")
                return np.array([]), target_sr
            
            audio_array, sr = librosa.load(output_path, sr=target_sr, mono=True)
            print(f"FFmpeg conversion successful: {len(audio_array)/sr:.1f}s")
            return audio_array, sr
            
        except Exception as e:
            print(f"FFmpeg processing error: {e}")
            return np.array([]), target_sr
        finally:
            for path in [input_path, output_path]:
                try:
                    os.unlink(path)
                except:
                    pass
    
    async def enroll_family_voice(
        self, 
        audio_file, 
        family_id: str, 
        speaker_name: str,
        relationship: str = "family_member"
    ) -> Dict:
        """Enroll family member's voice"""
        try:
            print(f"Enrolling voice for {speaker_name} in family {family_id}")
            
            voice_embeddings = await self._extract_multiple_embeddings(audio_file)
            
            if not voice_embeddings:
                return {
                    "success": False,
                    "error": "Could not extract voice characteristics",
                    "recommendation": "Record 15-20 seconds of clear speech"
                }
            
            voice_profile = self._create_voice_profile(voice_embeddings, speaker_name)
            enrollment_id = await self._store_encrypted_profile(
                family_id, speaker_name, relationship, voice_profile
            )
            
            return {
                "success": True,
                "enrollment_id": enrollment_id,
                "speaker_name": speaker_name,
                "voice_samples_processed": len(voice_embeddings),
                "enrollment_quality": voice_profile["quality_score"],
                "message": f"Successfully enrolled {speaker_name}'s voice"
            }
            
        except Exception as e:
            print(f"Voice enrollment error: {e}")
            return {
                "success": False,
                "error": f"Enrollment failed: {str(e)}",
                "speaker_name": speaker_name
            }
    
    async def _extract_multiple_embeddings(self, audio_file) -> List[np.ndarray]:
        """Extract voice embeddings from audio sample"""
        try:
            audio_array, sr = await self.load_audio_universal(audio_file)
            
            if len(audio_array) == 0:
                print("Failed to load audio")
                return []
            
            quality_report = self._validate_audio_quality(audio_array, sr)
            
            if not quality_report["is_valid"]:
                print(f"Audio quality issues: {quality_report['issues']}")
                return []
            
            embeddings = []
            segment_duration = 3.0
            total_duration = len(audio_array) / sr
            
            for start_time in range(0, int(total_duration - segment_duration), 2):
                start_sample = int(start_time * sr)
                end_sample = int((start_time + segment_duration) * sr)
                segment = audio_array[start_sample:end_sample]
                
                embedding = self._extract_voice_features(segment, sr)
                if embedding is not None:
                    embeddings.append(embedding)
            
            print(f"Extracted {len(embeddings)} voice embeddings from {total_duration:.1f}s")
            return embeddings if len(embeddings) >= 5 else []
            
        except Exception as e:
            print(f"Embedding extraction error: {e}")
            return []
    
    def _validate_audio_quality(self, audio_array: np.ndarray, sr: int) -> dict:
        """Validate audio quality"""
        duration = len(audio_array) / sr
        rms_energy = np.sqrt(np.mean(audio_array ** 2))
        
        quality_report = {
            "duration_seconds": duration,
            "rms_energy": float(rms_energy),
            "is_valid": True,
            "issues": [],
            "recommendations": []
        }
        
        if duration < 15.0:
            quality_report["issues"].append("Audio too short")
            quality_report["recommendations"].append("Record at least 15-20 seconds")
            quality_report["is_valid"] = False
        
        if rms_energy < 0.001:
            quality_report["issues"].append("Audio too quiet")
            quality_report["recommendations"].append("Speak louder")
            quality_report["is_valid"] = False
        
        return quality_report
    
    def _extract_voice_features(self, audio_segment: np.ndarray, sr: int) -> Optional[np.ndarray]:
        """Extract voice features from segment"""
        try:
            energy = librosa.feature.rms(y=audio_segment)[0]
            if np.mean(energy) < 0.01:
                return None
            
            features = []
            
            # MFCCs
            mfccs = librosa.feature.mfcc(y=audio_segment, sr=sr, n_mfcc=13)
            features.extend(np.mean(mfccs, axis=1))
            features.extend(np.std(mfccs, axis=1))
            
            # Pitch characteristics - FIXED: Always 5 features for consistency
            pitches, magnitudes = librosa.piptrack(y=audio_segment, sr=sr, threshold=0.1)
            pitch_values = []
            for t in range(pitches.shape[1]):
                index = magnitudes[:, t].argmax()
                pitch = pitches[index, t]
                if pitch > 0:
                    pitch_values.append(pitch)
            
            if pitch_values:
                features.extend([
                    np.mean(pitch_values),
                    np.std(pitch_values),
                    np.median(pitch_values),
                    np.percentile(pitch_values, 25),
                    np.percentile(pitch_values, 75)
                ])
            else:
                # Default values - MUST be 5 features to match enrollment
                features.extend([150.0, 20.0, 150.0, 130.0, 170.0])
            
            # Spectral features - FIXED: Need 4 features (mean + std of both)
            spectral_centroids = librosa.feature.spectral_centroid(y=audio_segment, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=audio_segment, sr=sr)[0]
            
            features.extend([
                np.mean(spectral_centroids),
                np.std(spectral_centroids),
                np.mean(spectral_rolloff),
                np.std(spectral_rolloff)
            ])
            
            # Rhythm and timing features - FIXED: Need 2 features
            zero_crossings = librosa.feature.zero_crossing_rate(audio_segment)[0]
            features.extend([
                np.mean(zero_crossings),
                np.std(zero_crossings)
            ])
            
            return np.array(features, dtype=np.float32)
            
        except Exception as e:
            print(f"Feature extraction error: {e}")
            return None
    
    def _create_voice_profile(self, embeddings: List[np.ndarray], speaker_name: str) -> Dict:
        """Create voice profile"""
        embedding_matrix = np.stack(embeddings)
        mean_embedding = np.mean(embedding_matrix, axis=0)
        std_embedding = np.std(embedding_matrix, axis=0)
        
        consistency_score = max(0.0, min(1.0, 1.0 - np.mean(std_embedding) / np.mean(np.abs(mean_embedding))))
        quality_score = min(1.0, (len(embeddings) / 10.0) * consistency_score)
        
        return {
            "speaker_name": speaker_name,
            "mean_embedding": mean_embedding.tolist(),
            "std_embedding": std_embedding.tolist(),
            "sample_count": len(embeddings),
            "consistency_score": float(consistency_score),
            "quality_score": float(quality_score),
            "enrollment_date": datetime.now().isoformat(),
            "feature_version": "v1.0"
        }
    
    async def _store_encrypted_profile(self, family_id: str, speaker_name: str, relationship: str, voice_profile: Dict) -> str:
        """Store encrypted profile"""
        profile_json = json.dumps(voice_profile).encode()
        encrypted_profile = self.cipher.encrypt(profile_json)
        enrollment_id = str(uuid.uuid4())
        
        conn = self.get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO voice_enrollments 
                (id, family_id, speaker_name, relationship, encrypted_voice_profile, 
                 quality_score, sample_count, enrollment_date, active, privacy_note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    enrollment_id, family_id, speaker_name, relationship,
                    encrypted_profile.decode(), voice_profile["quality_score"],
                    voice_profile["sample_count"], voice_profile["enrollment_date"],
                    True, "Voice profile stored as encrypted embeddings only"
                ))
            conn.commit()
            return enrollment_id
        finally:
            conn.close()
    
    async def identify_enrolled_speaker(self, audio_input, family_id: str) -> Tuple[Optional[str], float]:
        """
        FIXED: Identify speaker from audio segment or file
        Handles both numpy arrays and file objects
        """
        try:
            audio_array, sr = await self.load_audio_universal(audio_input)
            
            if len(audio_array) == 0:
                return None, 0.0
            
            embedding = self._extract_voice_features(audio_array, sr)
            if embedding is None:
                return None, 0.0
            
            enrolled_profiles = await self._get_family_profiles(family_id)
            
            if not enrolled_profiles:
                return None, 0.0
            
            best_match = None
            best_similarity = 0.0
            
            for profile in enrolled_profiles:
                similarity = self._calculate_voice_similarity(embedding, profile)
                if similarity > best_similarity and similarity >= self.enrollment_threshold:
                    best_similarity = similarity
                    best_match = profile["speaker_name"]
            
            if best_match:
                print(f"Matched: {best_match} ({best_similarity:.3f})")
            
            return best_match, best_similarity
            
        except Exception as e:
            print(f"Speaker identification error: {e}")
            return None, 0.0
    
    async def _get_family_profiles(self, family_id: str) -> List[Dict]:
        """Get enrolled profiles"""
        try:
            conn = self.get_db_connection()
            profiles = []
            
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM voice_enrollments WHERE family_id = %s AND active = TRUE", (family_id,))
                    records = cursor.fetchall()
                
                for record in records:
                    encrypted_profile = record["encrypted_voice_profile"].encode()
                    decrypted_data = self.cipher.decrypt(encrypted_profile)
                    voice_profile = json.loads(decrypted_data.decode())
                    voice_profile["record_id"] = record["id"]
                    profiles.append(voice_profile)
            finally:
                conn.close()
            
            return profiles
        except Exception as e:
            print(f"Failed to get profiles: {e}")
            return []
    
    def _calculate_voice_similarity(self, current_embedding: np.ndarray, enrolled_profile: Dict) -> float:
        """Calculate similarity"""
        try:
            enrolled_embedding = np.array(enrolled_profile["mean_embedding"])
            cosine_sim = cosine_similarity_simple(current_embedding, enrolled_embedding)
            
            weighted_similarity = cosine_sim * enrolled_profile["quality_score"] * enrolled_profile["consistency_score"]
            return max(0.0, min(1.0, weighted_similarity))
        except Exception as e:
            print(f"Similarity error: {e}")
            return 0.0

# Global instance
voice_enrollment_service = VoiceEnrollmentService()

async def enhanced_speaker_processing(audio_file, family_id: str):
    """FIXED: Segment-based enrollment matching (from working code)"""
    from services.cloud_speaker_service import cloud_speaker_service
    
    try:
        print(f"Enhanced processing for family: {family_id}")
        
        # Load full audio
        await audio_file.seek(0)
        full_audio_data = await audio_file.read()
        full_audio, sr = await voice_enrollment_service.load_audio_universal(audio_file, target_sr=16000)
        print(f"Loaded: {len(full_audio)/sr:.1f}s")
        
        # Get cloud diarization
        await audio_file.seek(0)
        speaker_segments = await cloud_speaker_service.process_audio_with_diarization(audio_file)
        
        if not speaker_segments:
            return []
        
        print(f"Cloud found {len(speaker_segments)} segments")
        
        # Process each segment individually
        enhanced_segments = []
        
        for i, segment in enumerate(speaker_segments):
            start_time = segment.get("start_time", 0)
            end_time = segment.get("end_time", start_time + 3.0)
            
            start_sample = max(0, int(start_time * sr))
            end_sample = min(len(full_audio), int(end_time * sr))
            
            if start_sample >= end_sample:
                segment["enrollment_match"] = False
                segment["enrollment_confidence"] = 0.0
                enhanced_segments.append(segment)
                continue
            
            # Extract segment audio as numpy array
            segment_audio = full_audio[start_sample:end_sample]
            
            # Create temp file for this segment
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_segment:
                import soundfile as sf
                sf.write(temp_segment.name, segment_audio, sr)
                temp_path = temp_segment.name
            
            try:
                # Open as file-like object for identify_enrolled_speaker
                with open(temp_path, 'rb') as segment_file:
                    class AsyncFileWrapper:
                        def __init__(self, file):
                            self.file = file
                        async def seek(self, pos):
                            self.file.seek(pos)
                        async def read(self):
                            return self.file.read()
                    
                    async_file = AsyncFileWrapper(segment_file)
                    enrolled_name, confidence = await voice_enrollment_service.identify_enrolled_speaker(
                        async_file, family_id
                    )
                
                print(f"Segment {i}: enrolled_name={enrolled_name}, confidence={confidence:.3f}")
                
                if enrolled_name and confidence >= 0.70:  # Lower threshold
                    segment["speaker"] = enrolled_name
                    segment["enrollment_match"] = True
                    segment["enrollment_confidence"] = confidence
                    segment["method"] = "voice_enrollment_match"
                else:
                    segment["enrollment_match"] = False
                    segment["enrollment_confidence"] = confidence
                    segment["method"] = "cloud_diarization"
                
            finally:
                os.unlink(temp_path)
            
            enhanced_segments.append(segment)
        
        matches = sum(1 for s in enhanced_segments if s.get("enrollment_match"))
        print(f"Enrollment matches: {matches}/{len(enhanced_segments)}")
        
        return enhanced_segments
        
    except Exception as e:
        print(f"Enhanced processing error: {e}")
        import traceback
        print(traceback.format_exc())
        return speaker_segments if 'speaker_segments' in locals() else []

async def enroll_voice_endpoint(file, family_id: str, speaker_name: str, relationship: str = "family_member"):
    """Endpoint for voice enrollment"""
    return await voice_enrollment_service.enroll_family_voice(file, family_id, speaker_name, relationship)