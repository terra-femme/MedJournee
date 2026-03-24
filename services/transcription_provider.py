# services/transcription_provider.py
"""
TranscriptionProvider abstraction for MedJournee.

Lets the orchestrator swap Whisper / GPT-4o / Gemini via one line:
    agent = TranscriptionAgent(provider=GPT4oProvider())

Return contract for .transcribe():
    {
        "text": str,
        "language": str,
        "segments": [{"text": str, "no_speech_prob": float}],
        "success": bool,
        "error": str | None,
    }
"""

from abc import ABC, abstractmethod
import os
import openai
import subprocess
import tempfile
from dotenv import load_dotenv

load_dotenv()


class TranscriptionProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_file, languages: list[str] = None) -> dict:
        """
        Transcribe audio to text.

        Args:
            audio_file: UploadFile-like object with async read/seek.
            languages:  Expected language codes.
                        - len == 1 → force Whisper to that language (best accuracy for monolingual sessions)
                        - len == 0, None, or >= 2 → omit language param; Whisper auto-detects
                          (handles code-switching when provider and family speak different languages)

        Returns dict with keys: text, language, segments, success, error.
        """
        pass


# ---------------------------------------------------------------------------
# CONTENT-TYPE → FILE EXTENSION MAP  (shared by all Whisper-based providers)
# ---------------------------------------------------------------------------
_CT_MAP = {
    "audio/webm": "webm",
    "audio/webm;codecs=opus": "webm",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/m4a": "m4a",
}


class WhisperProvider(TranscriptionProvider):
    """
    Production Whisper provider.

    Wraps OpenAI Whisper-1 with:
    - Multi-language: single language → forced, 2+ languages → auto-detect
    - verbose_json for segment-level no_speech_prob
    - temperature=0 to suppress hallucinations
    - Medical context prompt
    """

    # Minimum audio bytes to attempt transcription (avoids API call on near-silence)
    MIN_AUDIO_BYTES = 10_000

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        self.client = openai.OpenAI(api_key=self.api_key)

    async def transcribe(self, audio_file, languages: list[str] = None) -> dict:
        """Call Whisper API with multi-language support."""
        audio_content = b""
        try:
            await audio_file.seek(0)
            audio_content = await audio_file.read()
            await audio_file.seek(0)

            # Skip tiny chunks — likely silence
            if len(audio_content) < self.MIN_AUDIO_BYTES:
                return {
                    "text": "",
                    "language": "unknown",
                    "segments": [],
                    "success": True,
                    "error": None,
                    "audio_size": len(audio_content),
                    "_skipped": True,  # consumed by TranscriptionAgent for logging
                }

            content_type = getattr(audio_file, "content_type", "audio/webm") or "audio/webm"
            base_ct = content_type.split(";")[0].strip()
            ext = _CT_MAP.get(base_ct, "webm")
            audio_size = len(audio_content)

            # --- FFmpeg conversion ---
            # MediaRecorder chunks after the first lack the EBML container header
            # and are rejected by Whisper as "Invalid file format".
            # Force-mux through FFmpeg → WAV to produce a self-contained file.
            file_tuple = self._convert_with_ffmpeg(audio_content, ext, base_ct)
            if file_tuple is None:
                # FFmpeg failed on a webm chunk — unusable, skip silently
                return {
                    "text": "",
                    "language": "unknown",
                    "segments": [],
                    "success": True,
                    "error": None,
                    "audio_size": audio_size,
                    "_skipped": True,
                }

            api_params = {
                "model": "whisper-1",
                "file": file_tuple,
                "response_format": "verbose_json",
                "temperature": 0,
                "prompt": "Medical appointment. Patient and doctor.",
            }

            # Single language → force for maximum accuracy.
            # 2+ languages (or none) → omit so Whisper auto-detects per segment.
            clean_langs = [l for l in (languages or []) if l and l not in ("auto", "")]
            if len(clean_langs) == 1:
                api_params["language"] = clean_langs[0]
            # else: omit — auto-detect handles code-switching

            response = self.client.audio.transcriptions.create(**api_params)

            raw_text = response.text.strip() if response.text else ""
            detected_language = getattr(response, "language", None) or "unknown"

            # Normalise segments to plain dicts
            raw_segs = getattr(response, "segments", []) or []
            segments = []
            for seg in raw_segs:
                if isinstance(seg, dict):
                    segments.append(
                        {"text": seg.get("text", ""), "no_speech_prob": seg.get("no_speech_prob", 0.0)}
                    )
                else:
                    segments.append(
                        {
                            "text": getattr(seg, "text", ""),
                            "no_speech_prob": getattr(seg, "no_speech_prob", 0.0),
                        }
                    )

            print(
                f"[WhisperProvider] lang={detected_language}, "
                f"text='{raw_text[:80]}...' ({len(raw_text)} chars), "
                f"forced={len(clean_langs)==1}"
            )

            return {
                "text": raw_text,
                "language": detected_language,
                "segments": segments,
                "success": True,
                "error": None,
                "audio_size": audio_size,
            }

        except Exception as e:
            print(f"[WhisperProvider] Error: {e}")
            return {
                "text": "",
                "language": "error",
                "segments": [],
                "success": False,
                "error": str(e),
                "audio_size": len(audio_content),
            }

    def _convert_with_ffmpeg(self, audio_content: bytes, ext: str, base_ct: str):
        """
        Convert audio bytes to WAV via FFmpeg.

        Forces the input format (-f ext) so that partial WebM chunks without
        EBML headers are still muxed correctly.

        Returns:
            (filename, bytes, content_type) tuple on success, or
            None if FFmpeg failed on a webm chunk (chunk is unusable).
        """
        temp_input = None
        temp_output = None
        try:
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
            temp_input.write(audio_content)
            temp_input.close()

            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_output.close()

            # Use matroska demuxer (not webm) — it handles Chrome's streaming WebM where
            # the EBML header element has unknown length (0x1A43B675 at pos 0x0 error).
            ffmpeg_fmt = "matroska" if ext == "webm" else ext
            result = subprocess.run(
                [
                    "ffmpeg", "-loglevel", "error",
                    "-f", ffmpeg_fmt,
                    "-i", temp_input.name,
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                    "-y", temp_output.name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and os.path.getsize(temp_output.name) > 1000:
                with open(temp_output.name, "rb") as f:
                    wav_bytes = f.read()
                print(f"[WhisperProvider] FFmpeg → WAV: {len(wav_bytes)} bytes")
                return ("audio.wav", wav_bytes, "audio/wav")

            stderr = result.stderr.strip() if result.stderr else "no stderr"
            print(f"[WhisperProvider] FFmpeg failed (rc={result.returncode}): {stderr}")
            if ext == "webm":
                return None  # Raw webm without header — chunk is unusable
            return (f"audio.{ext}", audio_content, base_ct)  # Non-webm may still work

        except subprocess.TimeoutExpired:
            print("[WhisperProvider] FFmpeg timeout, using original")
            return (f"audio.{ext}", audio_content, base_ct)
        except FileNotFoundError:
            print("[WhisperProvider] FFmpeg not found, using original")
            return (f"audio.{ext}", audio_content, base_ct)
        finally:
            for tf in [temp_input, temp_output]:
                if tf:
                    try:
                        os.unlink(tf.name)
                    except OSError:
                        pass  # Temp file already deleted or inaccessible — non-critical, ignore


class GPT4oProvider(TranscriptionProvider):
    """Stub — GPT-4o audio transcription. Not yet implemented."""

    async def transcribe(self, audio_file, languages: list[str] = None) -> dict:
        raise NotImplementedError("GPT4oProvider is not yet implemented")


class GeminiProvider(TranscriptionProvider):
    """Stub — Gemini audio transcription. Not yet implemented."""

    async def transcribe(self, audio_file, languages: list[str] = None) -> dict:
        raise NotImplementedError("GeminiProvider is not yet implemented")
