# guardrails/speaker_confidence_guard.py
"""
SPEAKER CONFIDENCE GUARD

Priority: 15 (data quality)

Ensures speaker identification meets minimum confidence threshold.
Low-confidence speaker labels are set to SPEAKER_UNKNOWN to prevent
misattribution of medical statements.

This is critical for medical accuracy - we don't want to attribute
doctor statements to patients or vice versa.
"""

from typing import Optional, List, Any
from dataclasses import dataclass

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)


@dataclass
class SpeakerConfidenceConfig:
    """Configuration for speaker confidence guard"""
    min_confidence: float = 0.6  # Minimum confidence to keep speaker label
    unknown_label: str = "SPEAKER_UNKNOWN"
    warn_threshold: float = 0.7  # Warn but allow between warn and min


class SpeakerConfidenceGuard(BaseGuardrail):
    """
    Guard that validates speaker identification confidence.

    When diarization produces low-confidence speaker labels,
    this guard sets them to SPEAKER_UNKNOWN to prevent
    misattribution of medical statements.
    """

    NAME = "speaker_confidence_guard"
    PRIORITY = 15  # Data quality
    DESCRIPTION = "Validates speaker identification confidence"

    def __init__(
        self,
        enabled: bool = True,
        config: Optional[SpeakerConfidenceConfig] = None
    ):
        """
        Initialize speaker confidence guard.

        Args:
            enabled: Whether this guardrail is active
            config: Confidence threshold configuration
        """
        super().__init__(enabled)
        self.config = config or SpeakerConfidenceConfig()

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check speaker confidence in segments.

        Args:
            context: Context with segments to check

        Returns:
            GuardrailResult with confidence assessment
        """
        segments = context.segments or []

        if not segments:
            return self._allow("No segments to check")

        low_confidence_count = 0
        warn_confidence_count = 0
        total_segments = len(segments)

        for segment in segments:
            confidence = self._get_confidence(segment)

            if confidence < self.config.min_confidence:
                low_confidence_count += 1
            elif confidence < self.config.warn_threshold:
                warn_confidence_count += 1

        # Calculate percentages
        low_pct = (low_confidence_count / total_segments) * 100 if total_segments > 0 else 0
        warn_pct = (warn_confidence_count / total_segments) * 100 if total_segments > 0 else 0

        if low_confidence_count > 0:
            return self._warn(
                message=f"{low_confidence_count}/{total_segments} segments have low speaker confidence",
                low_confidence_count=low_confidence_count,
                warn_confidence_count=warn_confidence_count,
                total_segments=total_segments,
                low_confidence_pct=round(low_pct, 1),
                threshold=self.config.min_confidence
            )

        if warn_confidence_count > 0:
            return self._warn(
                message=f"{warn_confidence_count}/{total_segments} segments have marginal speaker confidence",
                warn_confidence_count=warn_confidence_count,
                total_segments=total_segments,
                warn_confidence_pct=round(warn_pct, 1),
                threshold=self.config.warn_threshold
            )

        return self._allow(
            message="All segments have sufficient speaker confidence",
            total_segments=total_segments,
            threshold=self.config.min_confidence
        )

    async def enforce(self, context: GuardrailContext) -> GuardrailResult:
        """
        Enforce speaker confidence by modifying low-confidence segments.

        Args:
            context: Context with segments to check

        Returns:
            GuardrailResult with modified segments if needed
        """
        if not self.enabled:
            return self._allow("Guardrail disabled")

        segments = context.segments or []

        if not segments:
            return self._allow("No segments to process")

        # Process segments and track modifications
        modified_segments = []
        modifications = 0
        warnings = 0

        for segment in segments:
            confidence = self._get_confidence(segment)
            modified_segment = self._copy_segment(segment)

            if confidence < self.config.min_confidence:
                # Set speaker to unknown
                modified_segment = self._set_speaker_unknown(modified_segment)
                modifications += 1
            elif confidence < self.config.warn_threshold:
                warnings += 1

            modified_segments.append(modified_segment)

        if modifications > 0:
            return self._modify(
                message=f"Set {modifications} low-confidence speakers to {self.config.unknown_label}",
                modified_content=modified_segments,
                modifications=modifications,
                warnings=warnings,
                total_segments=len(segments)
            )

        if warnings > 0:
            return self._warn(
                message=f"{warnings} segments have marginal confidence",
                warnings=warnings,
                total_segments=len(segments)
            )

        return self._allow(
            message="All segments have sufficient confidence",
            total_segments=len(segments)
        )

    def _get_confidence(self, segment: Any) -> float:
        """Extract confidence from segment."""
        # Try different attribute names
        if hasattr(segment, 'confidence'):
            return segment.confidence or 0.0
        if hasattr(segment, 'speaker_confidence'):
            return segment.speaker_confidence or 0.0
        if isinstance(segment, dict):
            return segment.get('confidence', segment.get('speaker_confidence', 0.0))
        return 0.0

    def _copy_segment(self, segment: Any) -> Any:
        """Create a copy of a segment."""
        if hasattr(segment, 'model_copy'):
            # Pydantic model
            return segment.model_copy()
        if hasattr(segment, 'copy'):
            return segment.copy()
        if isinstance(segment, dict):
            return segment.copy()
        # Can't copy, return as-is
        return segment

    def _set_speaker_unknown(self, segment: Any) -> Any:
        """Set speaker to unknown label."""
        if hasattr(segment, 'speaker'):
            segment.speaker = self.config.unknown_label
        elif isinstance(segment, dict):
            segment['speaker'] = self.config.unknown_label

        # Also set speaker role if available
        if hasattr(segment, 'speaker_role'):
            # Import here to avoid circular dependency
            try:
                from models.schemas import SpeakerRole
                segment.speaker_role = SpeakerRole.UNKNOWN
            except ImportError:
                segment.speaker_role = "Unknown"
        elif isinstance(segment, dict) and 'speaker_role' in segment:
            segment['speaker_role'] = "Unknown"

        return segment

    async def validate_segments(self, segments: List[Any]) -> dict:
        """
        Validate segments and return detailed confidence report.

        Args:
            segments: List of segments to validate

        Returns:
            Dict with confidence statistics
        """
        if not segments:
            return {
                "total": 0,
                "high_confidence": 0,
                "medium_confidence": 0,
                "low_confidence": 0,
                "average_confidence": 0.0
            }

        high = 0
        medium = 0
        low = 0
        total_confidence = 0.0

        for segment in segments:
            conf = self._get_confidence(segment)
            total_confidence += conf

            if conf >= self.config.warn_threshold:
                high += 1
            elif conf >= self.config.min_confidence:
                medium += 1
            else:
                low += 1

        return {
            "total": len(segments),
            "high_confidence": high,
            "medium_confidence": medium,
            "low_confidence": low,
            "average_confidence": round(total_confidence / len(segments), 3),
            "thresholds": {
                "high": self.config.warn_threshold,
                "min": self.config.min_confidence
            }
        }


# Global instance
_guard: Optional[SpeakerConfidenceGuard] = None


def get_speaker_confidence_guard() -> SpeakerConfidenceGuard:
    """Get or create the global speaker confidence guard."""
    global _guard
    if _guard is None:
        _guard = SpeakerConfidenceGuard()
    return _guard


# Convenience function
async def validate_speaker_confidence(segments: List[Any]) -> GuardrailResult:
    """Validate speaker confidence in segments."""
    guard = get_speaker_confidence_guard()
    context = GuardrailContext(session_id="validate", segments=segments)
    return await guard.enforce(context)
