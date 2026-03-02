# tools/translate_tool.py
"""
TRANSLATE TOOL - Wrapper for Google Translate (free via deep-translator)

Wraps:
- Text translation
- Language detection

Features:
- Circuit breaker protection
- Language code normalization
- Batch translation support
"""

from typing import Optional, List
import logging

from tools.base import BaseTool, ToolResult, CircuitBreaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import deep-translator (FREE, no API key)
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
    logger.info("Translate Tool: deep-translator loaded (FREE)")
except ImportError:
    TRANSLATOR_AVAILABLE = False
    logger.warning("Translate Tool: deep-translator not installed")


class TranslateTool(BaseTool):
    """
    Google Translate wrapper using free deep-translator library.

    Usage:
        tool = TranslateTool()

        # Single translation
        result = await tool.translate("Hello", target="vi")
        if result.success:
            translated = result.data["translated_text"]

        # Batch translation
        result = await tool.translate_batch(["Hello", "Goodbye"], target="vi")
    """

    TOOL_NAME = "translate"

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

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        correlation_id: Optional[str] = None
    ):
        super().__init__(circuit_breaker, correlation_id)

        if not TRANSLATOR_AVAILABLE:
            logger.warning("deep-translator not available - translations will fail")

    def _normalize_language(self, lang: str) -> str:
        """Normalize language code."""
        if not lang:
            return "auto"

        lang_lower = lang.lower().strip()
        return self.LANGUAGE_ALIASES.get(lang_lower, lang_lower)

    async def translate(
        self,
        text: str,
        target: str,
        source: Optional[str] = None
    ) -> ToolResult:
        """
        Translate text to target language.

        Args:
            text: Text to translate
            target: Target language code
            source: Source language code (auto-detect if None)

        Returns:
            ToolResult with translated_text, source_language, target_language
        """
        operation = "translate"
        start = self._start_timer()

        if not text or not text.strip():
            return self._make_result(
                success=False,
                error="No text provided",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        if not target:
            return self._make_result(
                success=False,
                error="No target language specified",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        if not TRANSLATOR_AVAILABLE:
            return self._make_result(
                success=False,
                error="deep-translator not installed",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        if not self._check_circuit():
            return self._make_result(
                success=False,
                error="Circuit breaker open - Translation service unavailable",
                operation=operation
            )

        target_normalized = self._normalize_language(target)
        source_normalized = self._normalize_language(source) if source else "auto"

        try:
            translator = GoogleTranslator(source=source_normalized, target=target_normalized)
            translated = translator.translate(text.strip())

            self.circuit_breaker.record_success()
            latency = self._end_timer(start)

            return self._make_result(
                success=True,
                data={
                    "translated_text": translated,
                    "original_text": text,
                    "source_language": source_normalized,
                    "target_language": target_normalized
                },
                operation=operation,
                latency_ms=latency
            )

        except Exception as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)

            return self._make_result(
                success=False,
                error=f"Translation failed: {str(e)}",
                operation=operation,
                latency_ms=latency
            )

    async def translate_batch(
        self,
        texts: List[str],
        target: str,
        source: Optional[str] = None
    ) -> ToolResult:
        """
        Translate multiple texts to target language.

        Args:
            texts: List of texts to translate
            target: Target language code
            source: Source language code (auto-detect if None)

        Returns:
            ToolResult with translations list
        """
        operation = "translate_batch"
        start = self._start_timer()

        if not texts:
            return self._make_result(
                success=False,
                error="No texts provided",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        if not TRANSLATOR_AVAILABLE:
            return self._make_result(
                success=False,
                error="deep-translator not installed",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        if not self._check_circuit():
            return self._make_result(
                success=False,
                error="Circuit breaker open - Translation service unavailable",
                operation=operation
            )

        target_normalized = self._normalize_language(target)
        source_normalized = self._normalize_language(source) if source else "auto"

        translations = []
        errors = []

        try:
            translator = GoogleTranslator(source=source_normalized, target=target_normalized)

            for text in texts:
                if not text or not text.strip():
                    translations.append("")
                    continue

                try:
                    translated = translator.translate(text.strip())
                    translations.append(translated)
                except Exception as e:
                    translations.append("")
                    errors.append(f"Failed to translate: {text[:30]}... - {str(e)}")

            self.circuit_breaker.record_success()
            latency = self._end_timer(start)

            return self._make_result(
                success=True,
                data={
                    "translations": translations,
                    "original_texts": texts,
                    "source_language": source_normalized,
                    "target_language": target_normalized,
                    "errors": errors
                },
                operation=operation,
                latency_ms=latency,
                translated_count=len([t for t in translations if t]),
                error_count=len(errors)
            )

        except Exception as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)

            return self._make_result(
                success=False,
                error=f"Batch translation failed: {str(e)}",
                operation=operation,
                latency_ms=latency
            )


# Singleton instance
_tool: Optional[TranslateTool] = None


def get_translate_tool(correlation_id: Optional[str] = None) -> TranslateTool:
    """Get or create the global translate tool."""
    global _tool
    if _tool is None:
        _tool = TranslateTool()
    if correlation_id:
        _tool.correlation_id = correlation_id
    return _tool
