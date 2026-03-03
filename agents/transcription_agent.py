# agents/transcription_agent.py
"""
AGENT 1: TRANSCRIPTION AGENT

Converts audio to text using OpenAI Whisper API.

Input: Audio file (webm, mp4, wav, m4a)
Output: TranscriptionResult

Features:
- FFmpeg conversion for browser audio chunks
- verbose_json response for language detection
- MULTI-LANGUAGE hallucination filtering (English, Vietnamese, Spanish, etc.)
- Graceful error handling
"""

import openai
import os
import tempfile
import subprocess
import re
import time
from typing import Optional
from dotenv import load_dotenv

from models.schemas import TranscriptionResult

load_dotenv()


class TranscriptionAgent:
    """
    Handles audio-to-text conversion using OpenAI Whisper API.

    CRITICAL: Filters hallucinations in MULTIPLE languages.
    Whisper commonly generates phantom "subscribe" messages in the
    language it detects, not just English.

    Test Mode:
        agent = TranscriptionAgent(test_mode=True)
        result = await agent.transcribe(audio_file)
        print(agent.test_log)  # Detailed processing log
    """

    # ==========================================================================
    # MULTI-LANGUAGE HALLUCINATION DETECTION
    # ==========================================================================
    
    # English hallucinations
    HALLUCINATION_EN = [
        "thank you",
        "thanks for watching",
        "subscribe",
        "like and subscribe",
        "don't forget to subscribe",
        "see you next time",
        "see you in the next",
        "bye bye",
        "bye-bye",  # hyphenated version
        "byebye",   # no space version
        "goodbye",
        "good bye",
        "good-bye",
        "good night",
        "good morning",
        "good evening",
        "go ahead",
        "hi",
        "hello",
        "hey",
        "music",
        "applause",
        "silence",
        "you",
        "thanks for listening",
        "please subscribe",
        "hit the like button",
        "comment below",
        "share this video",
        "click the bell",
        "ring the bell",
    ]
    
    # Vietnamese hallucinations (CRITICAL - this is what you're seeing!)
    HALLUCINATION_VI = [
        "dang ky",  # subscribe (no diacritics)
        "dang ki",  # subscribe (no diacritics alt)
        "kenh",  # channel (no diacritics)
        "video",
        "xem them",  # watch more
        "bam like",  # hit like
        "chia se",  # share
        "binh luan",  # comment
        "cam on",  # thank you
        "hen gap lai",  # see you again
        "tam biet",  # goodbye
        "nho dang ky",  # remember to subscribe
        "dung quen dang ky",  # don't forget to subscribe
        "dung quen dang ki",  # don't forget to subscribe
        "lalaschool",  # specific channel name hallucination
        "khong bo lo",  # don't miss
        "hap dan",  # exciting
        "theo doi",  # follow
        "nhan chuong",  # hit the bell
    ]
    
    # Spanish hallucinations
    HALLUCINATION_ES = [
        "suscribete",
        "no olvides suscribirte",
        "dale like",
        "comparte",
        "comenta",
        "gracias por ver",
        "hasta la proxima",
        "hasta luego",
        "adios",
    ]
    
    # Chinese hallucinations
    HALLUCINATION_ZH = [
        "订阅",  # subscribe
        "点赞",  # like
        "关注",  # follow
        "评论",  # comment
        "分享",  # share
        "谢谢观看",  # thanks for watching
        "再见",  # goodbye
    ]
    
    # Combined pattern keywords that indicate hallucination
    # If text contains 2+ of these, it's likely a hallucination
    HALLUCINATION_KEYWORDS = [
        # English
        "subscribe", "channel", "like", "comment", "share",
        "watching", "listening", "bell", "notification",
        # Vietnamese (with and without diacritics)
        "dang ky", "dang ki", "kenh", "like", "binh luan",
        "chia se", "chuong", "theo doi", "video",
        # Spanish
        "suscr", "canal", "comenta",
        # Chinese
        "订阅", "点赞", "关注", "频道",
    ]

    # Audio content type to file extension mapping
    CONTENT_TYPE_MAP = {
        "audio/webm": "webm",
        "audio/webm;codecs=opus": "webm",
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/ogg": "ogg",
        "audio/m4a": "m4a",
    }

    def __init__(self, api_key: Optional[str] = None, test_mode: bool = False):
        """
        Initialize with OpenAI API key.

        Args:
            api_key: OpenAI API key (uses env var if not provided)
            test_mode: If True, collects detailed logs for testing/debugging
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.client = openai.OpenAI(api_key=self.api_key)

        # Combine all hallucination phrases
        self.all_hallucinations = (
            self.HALLUCINATION_EN +
            self.HALLUCINATION_VI +
            self.HALLUCINATION_ES +
            self.HALLUCINATION_ZH
        )

        # Test mode for detailed logging
        self.test_mode = test_mode
        self.test_log: list = []  # Stores detailed processing steps when test_mode=True

    def _log_test(self, event: str, data: dict = None):
        """Log event for test mode debugging"""
        if self.test_mode:
            self.test_log.append({
                "timestamp": time.time(),
                "event": event,
                "data": data or {}
            })

    def clear_test_log(self):
        """Clear test log for new test run"""
        self.test_log = []

    def get_test_log(self) -> list:
        """Get test log entries"""
        return self.test_log

    async def transcribe(self, audio_file) -> TranscriptionResult:
        """
        Transcribe audio file to text with language detection.

        CRITICAL: Filters hallucinations in multiple languages.
        """
        start_time = time.time()
        self._log_test("transcribe_start", {"timestamp": start_time})

        try:
            await audio_file.seek(0)
            audio_content = await audio_file.read()
            await audio_file.seek(0)

            self._log_test("audio_loaded", {
                "size_bytes": len(audio_content),
                "content_type": getattr(audio_file, 'content_type', 'unknown')
            })

            # Skip very short audio (likely no speech or too short for reliable transcription)
            # Increased threshold from 5000 to 10000 bytes to reduce hallucinations
            if len(audio_content) < 10000:
                self._log_test("audio_too_short", {"size_bytes": len(audio_content), "threshold": 10000})
                return TranscriptionResult(
                    success=True,
                    text="",
                    detected_language="unknown",
                    confidence=0.0,
                    duration_seconds=0.0,
                    processing_time_ms=(time.time() - start_time) * 1000
                )

            # Determine file extension
            content_type = getattr(audio_file, 'content_type', 'audio/webm') or 'audio/webm'
            base_content_type = content_type.split(";")[0].strip()
            input_ext = self.CONTENT_TYPE_MAP.get(base_content_type, "webm")

            # Try direct upload first (Whisper supports webm, mp4, wav, etc. natively)
            # FFmpeg conversion was causing issues
            print(f"[Audio] Sending direct: {len(audio_content)} bytes, type={base_content_type}, ext={input_ext}")
            file_tuple = (f"audio.{input_ext}", audio_content, base_content_type)

            # Use verbose_json to get detected language and segment info
            # temperature=0 disables Whisper's probabilistic sampling — prevents it from
            # "completing" conversational gaps with hallucinated responses (e.g. adding
            # "Are you okay?" during a pause after "Hello, how are you?").
            # initial_prompt gives medical domain context without echoing back — keep it
            # short (< 10 words) to avoid the known prompt-echo issue.
            api_params = {
                "model": "whisper-1",
                "file": file_tuple,
                "response_format": "verbose_json",
                "temperature": 0,
                "prompt": "Medical appointment. Patient and doctor.",
            }

            response = self.client.audio.transcriptions.create(**api_params)

            raw_text = response.text.strip() if response.text else ""
            detected_language = getattr(response, "language", None) or "unknown"

            # DEBUG: Log what Whisper returned
            print(f"[Whisper Raw] Language: {detected_language}, Text: '{raw_text[:100]}...' ({len(raw_text)} chars)")

            self._log_test("whisper_response", {
                "raw_text": raw_text,
                "detected_language": detected_language,
                "text_length": len(raw_text)
            })

            # Check no_speech_prob from segments (if available)
            segments = getattr(response, "segments", [])
            segment_data = []
            if segments:
                # DEBUG: Show segment details
                for i, seg in enumerate(segments[:3]):  # First 3 segments
                    seg_text = getattr(seg, "text", seg.get("text", "") if isinstance(seg, dict) else "")
                    no_speech = getattr(seg, "no_speech_prob", seg.get("no_speech_prob", 0) if isinstance(seg, dict) else 0)
                    print(f"[Whisper Seg {i}] no_speech={no_speech:.2f}, text='{seg_text[:50]}'")
                    segment_data.append({"index": i, "no_speech_prob": no_speech, "text": seg_text[:100]})

                self._log_test("whisper_segments", {
                    "segment_count": len(segments),
                    "segments": segment_data
                })
            if segments and len(segments) > 0:
                # Filter out segments with high no_speech probability (likely hallucinations)
                valid_segments = []
                for seg in segments:
                    no_speech_prob = getattr(seg, "no_speech_prob", seg.get("no_speech_prob", 0) if isinstance(seg, dict) else 0)
                    if no_speech_prob < 0.5:  # Keep segments with <50% no-speech probability
                        seg_text = getattr(seg, "text", seg.get("text", "") if isinstance(seg, dict) else "")
                        valid_segments.append(seg_text)

                if valid_segments:
                    raw_text = " ".join(valid_segments).strip()
                elif raw_text:
                    # All segments had high no_speech_prob - likely all hallucinations
                    print(f"[Transcription] All segments had high no_speech_prob, returning empty")
                    return TranscriptionResult(
                        success=True,
                        text="",
                        detected_language=detected_language,
                        confidence=0.0,
                        duration_seconds=len(audio_content) / 32000,
                        was_filtered=True,
                        filter_reason="High no_speech_prob in all segments",
                        processing_time_ms=(time.time() - start_time) * 1000
                    )

            # CRITICAL: Multi-language hallucination filtering
            cleaned_text, was_filtered, filter_reason = self._filter_hallucinations(raw_text, detected_language)

            self._log_test("hallucination_filter", {
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
                "was_filtered": was_filtered,
                "filter_reason": filter_reason
            })

            confidence = self._estimate_confidence(raw_text, cleaned_text, len(audio_content))

            self._log_test("transcribe_complete", {
                "final_text": cleaned_text,
                "confidence": confidence,
                "processing_time_ms": (time.time() - start_time) * 1000
            })

            return TranscriptionResult(
                success=True,
                text=cleaned_text,
                detected_language=detected_language,
                confidence=confidence,
                duration_seconds=len(audio_content) / 32000,
                was_filtered=was_filtered,
                filter_reason=filter_reason,
                processing_time_ms=(time.time() - start_time) * 1000
            )

        except openai.APIError as e:
            return TranscriptionResult(
                success=False,
                text="",
                error=f"OpenAI API error: {str(e)}",
                processing_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return TranscriptionResult(
                success=False,
                text="",
                error=f"Transcription failed: {str(e)}",
                processing_time_ms=(time.time() - start_time) * 1000
            )
        finally:
            # No temp files to clean up (direct upload)
            pass

    def _filter_hallucinations(self, text: str, detected_language: str = "unknown") -> tuple:
        """
        Filter out common Whisper hallucinations in MULTIPLE languages.

        Whisper generates phantom "subscribe to my channel" in whatever
        language it thinks it's hearing - not just English!

        Args:
            text: Raw transcription text
            detected_language: Language code from Whisper (en, vi, es, zh, etc.)

        Returns:
            Tuple of (filtered_text, was_filtered, filter_reason)
        """
        if not text:
            return "", False, None

        # Normalize text: remove diacritics AND normalize punctuation
        text_lower = text.lower().strip()
        text_normalized = self._normalize_for_comparison(text_lower)

        # =================================================================
        # CHECK 0: Repetitive phrase hallucinations
        # Whisper often repeats the same short phrase when it can't understand audio
        # Examples: "Hi. Hi. Hi. Hi.", "Go ahead. Go ahead. Go ahead."
        # =================================================================
        # Split by sentence-ending punctuation
        sentences = [s.strip() for s in text_lower.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if len(sentences) >= 3:
            # Check if most sentences are identical
            from collections import Counter
            sentence_counts = Counter(sentences)
            most_common, count = sentence_counts.most_common(1)[0]
            repetition_ratio = count / len(sentences)
            if repetition_ratio >= 0.6 and len(most_common) < 20:
                print(f"[Hallucination Filter] Repetitive phrase blocked ('{most_common}' x{count}): '{text}'")
                return "", True, f"Repetitive: '{most_common}' x{count}"

        # =================================================================
        # CHECK 0.5: Filler word hallucinations
        # When Whisper can't understand speech, it often returns filler words
        # =================================================================
        filler_words = {"mhm", "mmhm", "mm", "ummm", "umm", "um", "uh", "ah", "hmm", "hm", "yeah", "yes", "no", "oh", "hi", "hello", "hey"}
        words = text_lower.replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ").split()
        if words:
            filler_count = sum(1 for w in words if w.strip() in filler_words)
            filler_ratio = filler_count / len(words)
            # If more than 70% filler words, it's likely hallucination
            if filler_ratio > 0.7 and len(words) >= 2:
                print(f"[Hallucination Filter] Filler words blocked ({filler_count}/{len(words)}): '{text}'")
                return "", True, f"Filler words ({filler_count}/{len(words)})"

        # =================================================================
        # CHECK 0.5: Very short suspicious text (high hallucination risk)
        # Only block these specific non-speech artifacts, not common words
        # =================================================================
        if len(text_normalized) <= 10:
            # Only block obvious non-speech artifacts
            artifacts = [
                "music", "applause", "silence", "hmm", "um", "uh", "ah", "mhm", "mm",
            ]
            for artifact in artifacts:
                if text_normalized == artifact or text_normalized.rstrip(".!?,") == artifact:
                    print(f"[Hallucination Filter] Audio artifact blocked: '{text}'")
                    return "", True, f"Audio artifact: '{artifact}'"

        # =================================================================
        # CHECK 0.5: Repetitive patterns (strong hallucination signal)
        # =================================================================
        # Detect repetitive "Bye. Bye. Bye." or "Thank you. Thank you." patterns
        words = text_lower.split()
        if len(words) >= 3:
            # Count repetitions
            word_counts = {}
            for word in words:
                clean_word = word.rstrip(".,!?")
                if len(clean_word) > 1:  # Skip single chars
                    word_counts[clean_word] = word_counts.get(clean_word, 0) + 1

            # If any word repeats 3+ times, likely hallucination
            for word, count in word_counts.items():
                if count >= 3 and word in ["bye", "thank", "thanks", "subscribe", "like"]:
                    print(f"[Hallucination Filter] Repetitive pattern blocked: '{text}'")
                    return "", True, f"Repetitive: '{word}' x{count}"

            # Also check for "thank" appearing 2+ times (common hallucination pattern)
            thank_count = word_counts.get("thank", 0) + word_counts.get("thanks", 0)
            if thank_count >= 2:
                print(f"[Hallucination Filter] Multiple thanks blocked: '{text}'")
                return "", True, f"Multiple thanks ({thank_count})"

        # =================================================================
        # CHECK 0.75: Non-medical context indicators (likely hallucinations)
        # =================================================================
        # These words almost never appear in medical conversations
        non_medical_indicators = [
            "donors", "viewers", "audience", "streaming", "podcast", "episode",
            "patreon", "sponsor", "sponsored", "advertisement", "promo",
            "youtube", "twitch", "tiktok", "instagram", "facebook",
            "followers", "subscribers", "membership",
        ]
        for indicator in non_medical_indicators:
            if indicator in text_lower:
                print(f"[Hallucination Filter] Non-medical indicator blocked: '{text}'")
                return "", True, f"Non-medical: '{indicator}'"

        # =================================================================
        # CHECK 1: Exact match against known hallucinations
        # =================================================================
        for phrase in self.all_hallucinations:
            phrase_lower = phrase.lower()
            phrase_normalized = self._normalize_for_comparison(phrase_lower)

            # Exact match only
            if text_lower == phrase_lower or text_normalized == phrase_normalized:
                print(f"[Hallucination Filter] Exact match blocked: '{text}'")
                return "", True, f"Exact match: '{phrase}'"

            # Starts with hallucination phrase - only if text is very short
            # (longer text starting with "thank you" might be legitimate like "Thank you for explaining...")
            if len(text) < 40:
                if text_lower.startswith(phrase_lower + ".") or text_lower.startswith(phrase_lower + ","):
                    print(f"[Hallucination Filter] Short starts-with blocked: '{text}'")
                    return "", True, f"Short starts with: '{phrase}'"

        # =================================================================
        # CHECK 2: Very short text that IS a hallucination phrase
        # Only block if the text is essentially just the hallucination phrase
        # =================================================================
        if len(text) < 50:
            # Only check multi-word hallucination phrases (more specific)
            multi_word_hallucinations = [
                "thanks for watching", "like and subscribe", "don't forget to subscribe",
                "see you next time", "see you in the next", "thanks for listening",
                "please subscribe", "hit the like button", "comment below",
                "share this video", "click the bell", "ring the bell",
                "dang ky kenh", "nho dang ky", "dung quen dang ky",
                "no olvides suscribirte", "gracias por ver", "hasta la proxima",
            ]
            for phrase in multi_word_hallucinations:
                phrase_lower = phrase.lower()
                phrase_normalized = self._normalize_for_comparison(phrase_lower)

                # Must be very close match (text is mostly just this phrase)
                if (text_lower == phrase_lower or
                    text_normalized == phrase_normalized or
                    text_lower.rstrip(".,!?") == phrase_lower):
                    print(f"[Hallucination Filter] Short hallucination phrase blocked: '{text}'")
                    return "", True, f"Hallucination phrase: '{phrase}'"

        # =================================================================
        # CHECK 3: Keyword density check (catches new variations)
        # Only block if MANY hallucination keywords in SHORT text
        # =================================================================
        # Use stricter keywords (exclude common words like "like", "watching")
        strict_keywords = [
            "subscribe", "channel", "notification", "bell",
            "dang ky", "dang ki", "kenh", "binh luan",
            "suscr", "canal",
            "订阅", "点赞", "关注", "频道",
        ]

        keyword_count = 0
        matched_keywords = []
        for keyword in strict_keywords:
            keyword_lower = keyword.lower()
            keyword_normalized = self._normalize_for_comparison(keyword_lower)

            if keyword_lower in text_lower or keyword_normalized in text_normalized:
                keyword_count += 1
                matched_keywords.append(keyword)

        # Require 2+ strict keywords in short text (<100 chars), or 3+ in any text
        if (keyword_count >= 2 and len(text) < 100) or keyword_count >= 3:
            print(f"[Hallucination Filter] Keyword density blocked ({keyword_count} keywords): '{text}'")
            return "", True, f"Keyword density ({keyword_count}): {matched_keywords[:3]}"

        # =================================================================
        # CHECK 4: Pattern-based detection
        # Catches "don't forget to subscribe to X channel" variations
        # =================================================================
        hallucination_patterns = [
            # English patterns
            (r"subscribe.*channel", "subscribe+channel"),
            (r"channel.*subscribe", "channel+subscribe"),
            (r"like.*subscribe", "like+subscribe"),
            (r"comment.*below", "comment+below"),
            (r"thanks.*watching", "thanks+watching"),
            # NOTE: "see you next time" checked separately with length guard below
            # Vietnamese patterns (with and without diacritics)
            (r"dang k[yi].*kenh", "dang ky+kenh"),
            (r"kenh.*dang k[yi]", "kenh+dang ky"),
            (r"dung quen.*dang", "dung quen+dang"),
            (r"nho.*dang k[yi]", "nho+dang ky"),
            (r"bam.*like", "bam+like"),
            (r"khong bo lo", "khong bo lo"),
            (r"đăng k[ýí].*kênh", "dang ky+kenh"),
            (r"kênh.*đăng k[ýí]", "kenh+dang ky"),
            (r"đừng quên.*đăng", "dung quen+dang"),
            (r"nhớ.*đăng k[ýí]", "nho+dang ky"),
            (r"bấm.*like", "bam+like"),
            (r"không bỏ lỡ", "khong bo lo"),
            # Spanish patterns
            (r"suscr.*canal", "suscr+canal"),
            (r"no olvides.*suscr", "no olvides+suscr"),
            (r"dale.*like", "dale+like"),
        ]

        for pattern, name in hallucination_patterns:
            if re.search(pattern, text_lower) or re.search(pattern, text_normalized):
                print(f"[Hallucination Filter] Pattern blocked ('{pattern}'): '{text}'")
                return "", True, f"Pattern: {name}"

        # "see you next time" is a normal medical farewell — only block as hallucination
        # if it appears as a short standalone phrase (< 80 chars), not inside a real conversation
        if len(text) < 80 and (re.search(r"see you.*next", text_lower) or re.search(r"see you.*next", text_normalized)):
            print(f"[Hallucination Filter] Pattern blocked ('see you.*next' short-form): '{text}'")
            return "", True, "Pattern: see you+next"

        # =================================================================
        # CHECK 5: Specific known hallucination strings
        # These are exact strings Whisper commonly generates
        # =================================================================
        known_exact_hallucinations = [
            "dung quen dang ki cho kenh lalaschool de khong bo lo nhung video hap dan",
            "đừng quên đăng kí cho kênh lalaschool để không bỏ lỡ những video hấp dẫn",
            "don't forget to subscribe to lalaschool channel",
            "thanks for watching and see you next time",
            "please like and subscribe",
            "nho dang ky kenh de khong bo lo video moi",
            "nhớ đăng ký kênh để không bỏ lỡ video mới",
            "cam on cac ban da xem video",
            "cảm ơn các bạn đã xem video",
        ]

        for exact in known_exact_hallucinations:
            exact_lower = exact.lower()
            exact_normalized = self._normalize_for_comparison(exact_lower)

            if exact_lower in text_lower or exact_normalized in text_normalized:
                print(f"[Hallucination Filter] Known hallucination blocked: '{text}'")
                return "", True, "Known hallucination"
            # Only check partial match if text is substantial (>15 chars)
            # Prevents blocking common short phrases like "I." or "Hello"
            if len(text_lower) > 15:
                if text_lower in exact_lower or text_normalized in exact_normalized:
                    print(f"[Hallucination Filter] Partial hallucination blocked: '{text}'")
                    return "", True, "Partial hallucination match"

        # Text passed all filters
        return text, False, None

    def _normalize_for_comparison(self, text: str) -> str:
        """
        Normalize text for hallucination comparison.

        Handles:
        - Vietnamese diacritics (đăng ký -> dang ky)
        - Hyphens (bye-bye -> bye bye)
        - Extra whitespace
        - Common punctuation

        Example: "Bye-bye!" -> "bye bye"
        """
        # First remove Vietnamese diacritics
        result = self._remove_vietnamese_diacritics(text)

        # Replace hyphens and underscores with spaces
        result = result.replace("-", " ").replace("_", " ")

        # Remove common punctuation at end
        result = result.rstrip(".,!?;:")

        # Normalize whitespace (multiple spaces -> single space)
        result = " ".join(result.split())

        return result

    def _remove_vietnamese_diacritics(self, text: str) -> str:
        """
        Remove Vietnamese diacritics for comparison.
        This helps catch hallucinations regardless of accent marks.
        
        Example: "đăng ký" -> "dang ky"
        """
        # Vietnamese character mapping
        replacements = {
            'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
            'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
            'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
            'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
            'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
            'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
            'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
            'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
            'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
            'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
            'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
            'đ': 'd',
        }
        
        result = text
        for vietnamese, ascii_char in replacements.items():
            result = result.replace(vietnamese, ascii_char)
        
        return result

    def _estimate_confidence(self, raw_text: str, cleaned_text: str, audio_size: int) -> float:
        """Estimate transcription confidence"""
        if not cleaned_text:
            return 0.0

        confidence = 0.5

        # Bonus for surviving hallucination filter
        if raw_text == cleaned_text:
            confidence += 0.2

        # Bonus for reasonable word count
        words = len(cleaned_text.split())
        if 3 <= words <= 100:
            confidence += 0.2

        # Bonus for ending with punctuation
        if cleaned_text and cleaned_text[-1] in ".!?":
            confidence += 0.1

        return min(1.0, confidence)


# =============================================================================
# STANDALONE FUNCTION (backward compatibility)
# =============================================================================

_agent: Optional[TranscriptionAgent] = None


def get_agent() -> TranscriptionAgent:
    """Get or create the global transcription agent"""
    global _agent
    if _agent is None:
        _agent = TranscriptionAgent()
    return _agent


async def transcribe_audio(file, source_language: Optional[str] = None) -> dict:
    """
    Backward-compatible function.
    """
    agent = get_agent()
    result = await agent.transcribe(file)

    return {
        "text": result.text,
        "language": result.detected_language,
        "success": result.success,
        "error": result.error
    }
