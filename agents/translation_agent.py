# agents/translation_agent.py
"""
AGENT 3: TRANSLATION AGENT

Translates text between languages using FREE deep-translator library.
Supports bidirectional translation with 4-param language configuration.

Input: Text + language config
Output: TranslationResult

Features:
- FREE - no API key needed (uses Google Translate via deep-translator)
- Bidirectional: match_language_role() determines translation direction
- Language code normalization (zh -> zh-CN)
- Graceful fallback on errors
"""

from typing import Optional, List, Dict
import logging

from models.schemas import (
    TranslationResult,
    SpeakerSegment,
    TranslatedSegment,
    SpeakerRole,
    LanguageRoleResult
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import deep-translator (FREE, no API key)
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
    logger.info("Translation Agent: deep-translator loaded (FREE)")
except ImportError:
    TRANSLATOR_AVAILABLE = False
    logger.warning("Translation Agent: deep-translator not installed. Run: pip install deep-translator")


def match_language_role(
    detected_lang: str,
    provider_spoken: str,
    provider_translate_to: str,
    family_spoken: str,
    family_translate_to: str
) -> LanguageRoleResult:
    """
    Determine speaker role and translation target based on detected language.

    Each side has:
    - "spoken" language (for detection matching)
    - "translate_to" language (the subtext translation target)

    Returns LanguageRoleResult with speaker_role and translate_to
    """
    if not detected_lang:
        return LanguageRoleResult(
            speaker_role="provider",
            translate_to=provider_translate_to
        )

    def normalize(code: str) -> str:
        """Normalize Chinese variants: Whisper returns 'zh', user may configure 'zh-cn'"""
        code = code.lower().strip()
        if code in ("zh", "zh-cn", "zh-tw", "chinese"):
            return "zh"
        return code

    det_norm = normalize(detected_lang)
    prov_norm = normalize(provider_spoken)
    fam_norm = normalize(family_spoken)

    if det_norm == prov_norm:
        # Provider is speaking — translate into provider's translate_to (for family)
        return LanguageRoleResult(
            speaker_role="provider",
            translate_to=provider_translate_to
        )
    elif det_norm == fam_norm:
        # Family is speaking — translate into family's translate_to (for provider)
        return LanguageRoleResult(
            speaker_role="family",
            translate_to=family_translate_to
        )
    else:
        # Unknown language — default to treating as provider speech
        return LanguageRoleResult(
            speaker_role="provider",
            translate_to=provider_translate_to
        )


class TranslationAgent:
    """
    Handles text translation using FREE Google Translate.

    Usage:
        agent = TranslationAgent()
        result = await agent.translate("Hello doctor", target_language="vi")

        if result.success:
            print(result.translated_text)
    """

    LANGUAGE_ALIASES = {
        "zh": "zh-CN",
        "chinese": "zh-CN",
        "zh-tw": "zh-TW",
        "taiwanese": "zh-TW",
        "vietnamese": "vi",
        "spanish": "es",
        "french": "fr",
        "german": "de",
        "japanese": "ja",
        "korean": "ko",
        "tagalog": "tl",
        "filipino": "tl",
        "thai": "th",
    }

    SUPPORTED_LANGUAGES = {
        "en": "English",
        "vi": "Vietnamese",
        "es": "Spanish",
        "zh-CN": "Chinese (Simplified)",
        "zh-TW": "Chinese (Traditional)",
        "fr": "French",
        "de": "German",
        "ja": "Japanese",
        "ko": "Korean",
        "th": "Thai",
        "tl": "Tagalog/Filipino",
    }

    def __init__(self):
        """Initialize translation agent"""
        if not TRANSLATOR_AVAILABLE:
            logger.warning("deep-translator not available - translations will fail")

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> TranslationResult:
        """
        Translate text to target language.

        Args:
            text: Text to translate
            target_language: Target language code
            source_language: Source language code or None for auto-detect

        Returns:
            TranslationResult with translated text
        """
        if not text or not text.strip():
            return TranslationResult(
                success=False,
                original_text=text or "",
                translated_text="",
                error="No text provided"
            )

        if not target_language:
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text=text,
                error="No target language specified"
            )

        if not TRANSLATOR_AVAILABLE:
            return TranslationResult(
                success=False,
                original_text=text,
                translated_text=text,
                error="deep-translator not installed. Run: pip install deep-translator"
            )

        target = self._normalize_language(target_language)
        source = self._normalize_language(source_language) if source_language else "auto"

        try:
            translator = GoogleTranslator(source=source, target=target)
            translated = translator.translate(text.strip())

            logger.info(f"Translated {len(text)} chars: {source} -> {target}")

            return TranslationResult(
                success=True,
                original_text=text,
                translated_text=translated,
                source_language=source,
                target_language=target_language,
                error=None
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Translation error: {error_msg}")

            return TranslationResult(
                success=False,
                original_text=text,
                translated_text=text,
                source_language=source,
                target_language=target_language,
                error=f"Translation failed: {error_msg}"
            )

    async def translate_segments(
        self,
        segments: List[SpeakerSegment],
        provider_spoken: str,
        provider_translate_to: str,
        family_spoken: str,
        family_translate_to: str
    ) -> List[TranslatedSegment]:
        """
        Translate segments bidirectionally based on detected language.

        Args:
            segments: List of SpeakerSegment objects
            provider_spoken: Language provider speaks
            provider_translate_to: Language to translate provider speech into
            family_spoken: Language family speaks
            family_translate_to: Language to translate family speech into

        Returns:
            List of TranslatedSegment with translation and speaker_role assigned
        """
        translated_segments = []

        for segment in segments:
            # Determine translation direction based on detected language
            role_info = match_language_role(
                segment.detected_language,
                provider_spoken,
                provider_translate_to,
                family_spoken,
                family_translate_to
            )

            # Translate
            result = await self.translate(segment.text, role_info.translate_to, None)

            # Assign speaker role based on language detection
            if role_info.speaker_role == "provider":
                speaker_role = SpeakerRole.HEALTHCARE_PROVIDER
            elif role_info.speaker_role == "family":
                speaker_role = SpeakerRole.PATIENT_FAMILY
            else:
                speaker_role = segment.speaker_role

            translated_segment = TranslatedSegment(
                speaker=segment.speaker,
                speaker_role=speaker_role,
                text=segment.text,
                detected_language=segment.detected_language,
                start_time=segment.start_time,
                end_time=segment.end_time,
                confidence=segment.confidence,
                enrollment_match=segment.enrollment_match,
                enrolled_name=segment.enrolled_name,
                translation=result.translated_text if result.success else ""
            )

            translated_segments.append(translated_segment)

        return translated_segments

    def _normalize_language(self, lang: str) -> str:
        """Normalize language code to format expected by Google Translate"""
        if not lang:
            return "auto"

        lang_lower = lang.lower().strip()

        if lang_lower in self.LANGUAGE_ALIASES:
            return self.LANGUAGE_ALIASES[lang_lower]

        return lang_lower

    def get_supported_languages(self) -> dict:
        """Return dictionary of supported language codes and names"""
        return self.SUPPORTED_LANGUAGES.copy()


# =============================================================================
# STANDALONE FUNCTIONS
# =============================================================================

_agent: Optional[TranslationAgent] = None


def get_agent() -> TranslationAgent:
    """Get or create the global translation agent"""
    global _agent
    if _agent is None:
        _agent = TranslationAgent()
    return _agent


async def translate_text(
    text: str,
    target_lang: str,
    source_lang: Optional[str] = None
) -> dict:
    """Backward-compatible function"""
    agent = get_agent()
    result = await agent.translate(text, target_lang, source_lang)

    return {
        "translated_text": result.translated_text,
        "source_language": result.source_language,
        "target_language": result.target_language,
        "success": result.success,
        "error_message": result.error,
        "confidence": 0.95 if result.success else 0.0,
        "method": "free_deep_translator"
    }
