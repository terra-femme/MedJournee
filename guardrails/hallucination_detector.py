# guardrails/hallucination_detector.py
"""
HALLUCINATION DETECTOR GUARDRAIL

Priority: 10 (data quality)

Filters Whisper transcription hallucinations in multiple languages.
Whisper commonly generates phantom "subscribe to my channel" messages
in the language it thinks it's hearing.

Extracted from agents/transcription_agent.py for centralized use.

Detection Layers:
1. Short text filter - Very short suspicious texts
2. Exact match - Known hallucination phrases
3. Short text contains - Hallucination phrases in short text
4. Keyword density - Multiple hallucination keywords
5. Pattern matching - Regex patterns for common formats
6. Known exact strings - Specific Whisper hallucinations

Languages supported: English, Vietnamese, Spanish, Chinese
"""

import re
from typing import Optional, List, Tuple

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)


class HallucinationDetector(BaseGuardrail):
    """
    Detects and filters Whisper transcription hallucinations.

    Whisper commonly generates phantom "subscribe" messages in whatever
    language it thinks it's hearing - not just English!
    """

    NAME = "hallucination_detector"
    PRIORITY = 10  # Data quality
    DESCRIPTION = "Filters Whisper transcription hallucinations"

    # ==========================================================================
    # MULTI-LANGUAGE HALLUCINATION PHRASES
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
        "bye-bye",
        "byebye",
        "goodbye",
        "good bye",
        "good-bye",
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

    # Vietnamese hallucinations
    HALLUCINATION_VI = [
        "dang ky",
        "dang ki",
        "kenh",
        "video",
        "xem them",
        "bam like",
        "chia se",
        "binh luan",
        "cam on",
        "hen gap lai",
        "tam biet",
        "nho dang ky",
        "dung quen dang ky",
        "dung quen dang ki",
        "lalaschool",
        "khong bo lo",
        "hap dan",
        "theo doi",
        "nhan chuong",
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
        "订阅",
        "点赞",
        "关注",
        "评论",
        "分享",
        "谢谢观看",
        "再见",
    ]

    # Combined keywords for density checking
    HALLUCINATION_KEYWORDS = [
        # English
        "subscribe", "channel", "like", "comment", "share",
        "watching", "listening", "bell", "notification",
        # Vietnamese
        "dang ky", "dang ki", "kenh", "like", "binh luan",
        "chia se", "chuong", "theo doi", "video",
        # Spanish
        "suscr", "canal", "comenta",
        # Chinese
        "订阅", "点赞", "关注", "频道",
    ]

    # Pattern-based detection
    HALLUCINATION_PATTERNS = [
        # English patterns
        (r"subscribe.*channel", "subscribe+channel"),
        (r"channel.*subscribe", "channel+subscribe"),
        (r"like.*subscribe", "like+subscribe"),
        (r"comment.*below", "comment+below"),
        (r"thanks.*watching", "thanks+watching"),
        (r"see you.*next", "see you+next"),
        # Vietnamese patterns
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

    # Known exact hallucination strings
    KNOWN_EXACT_HALLUCINATIONS = [
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

    # Vietnamese diacritics mapping for normalization
    VIETNAMESE_DIACRITICS = {
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

    def __init__(self, enabled: bool = True):
        """Initialize hallucination detector."""
        super().__init__(enabled)

        # Combine all hallucination phrases
        self.all_hallucinations = (
            self.HALLUCINATION_EN +
            self.HALLUCINATION_VI +
            self.HALLUCINATION_ES +
            self.HALLUCINATION_ZH
        )

        # Pre-compile patterns
        self._patterns = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in self.HALLUCINATION_PATTERNS
        ]

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check text for hallucinations.

        Args:
            context: Context with text to check

        Returns:
            GuardrailResult - BLOCK if hallucination, ALLOW otherwise
        """
        if not context.text:
            return self._allow("No text to check")

        text = context.text
        detected_language = context.metadata.get("detected_language", "unknown")

        # Run detection
        is_hallucination, reason = self._detect_hallucination(text, detected_language)

        if is_hallucination:
            return self._modify(
                message=f"Hallucination filtered: {reason}",
                modified_content="",  # Replace with empty string
                filter_reason=reason,
                original_text=text[:100]  # First 100 chars for logging
            )

        return self._allow("No hallucination detected")

    def _detect_hallucination(self, text: str, detected_language: str = "unknown") -> Tuple[bool, Optional[str]]:
        """
        Multi-layer hallucination detection.

        Returns:
            Tuple of (is_hallucination, reason)
        """
        if not text:
            return False, None

        # Normalize text
        text_lower = text.lower().strip()
        text_normalized = self._normalize_for_comparison(text_lower)

        # =================================================================
        # CHECK 0: Audio artifacts (not speech)
        # =================================================================
        if len(text_normalized) <= 10:
            artifacts = ["music", "applause", "silence", "hmm", "um", "uh", "ah"]
            for artifact in artifacts:
                if text_normalized == artifact or text_normalized.rstrip(".!?,") == artifact:
                    return True, f"Audio artifact: '{artifact}'"

        # =================================================================
        # CHECK 0.5: Repetitive patterns (strong hallucination signal)
        # =================================================================
        words = text_lower.split()
        if len(words) >= 3:
            word_counts = {}
            for word in words:
                clean_word = word.rstrip(".,!?")
                if len(clean_word) > 1:
                    word_counts[clean_word] = word_counts.get(clean_word, 0) + 1
            for word, count in word_counts.items():
                if count >= 3 and word in ["bye", "thank", "thanks", "subscribe", "like"]:
                    return True, f"Repetitive: '{word}' x{count}"

            # Check for "thank" appearing 2+ times
            thank_count = word_counts.get("thank", 0) + word_counts.get("thanks", 0)
            if thank_count >= 2:
                return True, f"Multiple thanks ({thank_count})"

        # =================================================================
        # CHECK 0.75: Non-medical context indicators
        # =================================================================
        non_medical_indicators = [
            "donors", "viewers", "audience", "streaming", "podcast", "episode",
            "patreon", "sponsor", "sponsored", "advertisement", "promo",
            "youtube", "twitch", "tiktok", "instagram", "facebook",
            "followers", "subscribers", "membership",
        ]
        for indicator in non_medical_indicators:
            if indicator in text_lower:
                return True, f"Non-medical: '{indicator}'"

        # =================================================================
        # CHECK 1: Exact match against known hallucinations
        # =================================================================
        for phrase in self.all_hallucinations:
            phrase_lower = phrase.lower()
            phrase_normalized = self._normalize_for_comparison(phrase_lower)

            # Exact match only
            if text_lower == phrase_lower or text_normalized == phrase_normalized:
                return True, f"Exact match: '{phrase}'"

            # Starts with hallucination phrase - only for short text
            if len(text) < 40:
                if text_lower.startswith(phrase_lower + ".") or text_lower.startswith(phrase_lower + ","):
                    return True, f"Short starts with: '{phrase}'"

        # =================================================================
        # CHECK 2: Very short text that IS a hallucination phrase
        # =================================================================
        if len(text) < 50:
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
                if (text_lower == phrase_lower or
                    text_normalized == phrase_normalized or
                    text_lower.rstrip(".,!?") == phrase_lower):
                    return True, f"Hallucination phrase: '{phrase}'"

        # =================================================================
        # CHECK 3: Keyword density check (strict keywords only)
        # =================================================================
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

        if (keyword_count >= 2 and len(text) < 100) or keyword_count >= 3:
            return True, f"Keyword density ({keyword_count}): {matched_keywords[:3]}"

        # =================================================================
        # CHECK 4: Pattern-based detection
        # =================================================================
        for pattern, name in self._patterns:
            if pattern.search(text_lower) or pattern.search(text_normalized):
                return True, f"Pattern: {name}"

        # =================================================================
        # CHECK 5: Known exact hallucination strings
        # =================================================================
        for exact in self.KNOWN_EXACT_HALLUCINATIONS:
            exact_lower = exact.lower()
            exact_normalized = self._normalize_for_comparison(exact_lower)

            if exact_lower in text_lower or exact_normalized in text_normalized:
                return True, "Known hallucination"
            # Only check partial match if text is substantial (>15 chars)
            # Prevents blocking common short phrases like "I." or "Hello"
            if len(text_lower) > 15:
                if text_lower in exact_lower or text_normalized in exact_normalized:
                    return True, "Partial hallucination match"

        # Passed all checks
        return False, None

    def _normalize_for_comparison(self, text: str) -> str:
        """
        Normalize text for hallucination comparison.

        Handles Vietnamese diacritics, hyphens, whitespace.
        """
        # Remove Vietnamese diacritics
        result = text
        for vietnamese, ascii_char in self.VIETNAMESE_DIACRITICS.items():
            result = result.replace(vietnamese, ascii_char)

        # Replace hyphens and underscores with spaces
        result = result.replace("-", " ").replace("_", " ")

        # Remove common punctuation at end
        result = result.rstrip(".,!?;:")

        # Normalize whitespace
        result = " ".join(result.split())

        return result


# Convenience functions
def create_hallucination_detector() -> HallucinationDetector:
    """Create a new hallucination detector instance."""
    return HallucinationDetector()


async def filter_hallucination(text: str, detected_language: str = "unknown") -> Tuple[str, bool, Optional[str]]:
    """
    Filter hallucinations from text.

    Args:
        text: Text to check
        detected_language: Language code from Whisper

    Returns:
        Tuple of (filtered_text, was_filtered, filter_reason)
    """
    detector = HallucinationDetector()
    context = GuardrailContext(
        session_id="filter",
        text=text,
        metadata={"detected_language": detected_language}
    )
    result = await detector.check(context)

    if result.action == GuardrailAction.MODIFY:
        return result.modified_content, True, result.message
    return text, False, None
