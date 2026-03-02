# validators/quality_gates.py
"""
QUALITY GATES - Validate Agent Outputs

Quality Gates enforce standards at each pipeline stage:
- Define minimum quality thresholds
- Validate outputs before passing to next stage
- Provide actionable feedback for self-correction
- Enable graceful degradation

This is a key pattern from production agent pipelines:
"Enforce quality gates - this is how you get senior-level reasoning"
"""

from typing import List, Optional
from models.schemas import (
    ValidationResult,
    ValidationStatus,
    TranscriptionResult,
    DiarizationResult,
    TranslatedSegment,
    SummarizationResult,
)


class QualityThresholds:
    """Configurable quality thresholds for each stage."""
    # Transcription
    TRANSCRIPTION_MIN_CONFIDENCE = 0.4
    TRANSCRIPTION_MIN_WORDS = 2

    # Diarization
    DIARIZATION_MIN_SEGMENTS = 1
    DIARIZATION_MIN_AVG_CONFIDENCE = 0.5
    DIARIZATION_PREFER_MULTI_SPEAKER = True

    # Translation
    TRANSLATION_MIN_LENGTH_RATIO = 0.2
    TRANSLATION_MAX_EMPTY_RATIO = 0.3

    # Summarization
    SUMMARIZATION_MIN_CONFIDENCE = 0.4
    SUMMARIZATION_REQUIRED_FIELDS = ["chief_complaint", "family_summary"]
    SUMMARIZATION_MIN_SUMMARY_LENGTH = 20


class TranscriptionValidator:
    """Validates transcription output"""

    @staticmethod
    def validate(result: TranscriptionResult) -> ValidationResult:
        issues = []
        warnings = []
        suggestions = []
        score = 1.0

        if not result.success:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                score=0.0,
                issues=[result.error or "Transcription failed"]
            )

        if result.was_filtered:
            warnings.append(f"Hallucination filtered: {result.filter_reason}")
            score -= 0.1

        if not result.text:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                score=0.5,
                warnings=["No speech detected in audio"]
            )

        word_count = len(result.text.split())
        if word_count < QualityThresholds.TRANSCRIPTION_MIN_WORDS:
            warnings.append(f"Very short transcription: {word_count} words")
            score -= 0.2

        if result.confidence < QualityThresholds.TRANSCRIPTION_MIN_CONFIDENCE:
            issues.append(f"Low confidence: {result.confidence:.2f}")
            score -= 0.3
            suggestions.append("Consider re-recording with clearer audio")

        status = ValidationStatus.PASSED if score >= 0.7 else (
            ValidationStatus.WARNING if score >= 0.4 else ValidationStatus.FAILED
        )

        return ValidationResult(
            status=status,
            score=max(0.0, score),
            issues=issues,
            warnings=warnings,
            suggestions=suggestions
        )


class DiarizationValidator:
    """Validates diarization output"""

    @staticmethod
    def validate(result: DiarizationResult) -> ValidationResult:
        issues = []
        warnings = []
        suggestions = []
        score = 1.0

        if not result.success:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                score=0.0,
                issues=[result.error or "Diarization failed"]
            )

        if not result.segments:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                score=0.0,
                issues=["No speech segments detected"]
            )

        if len(result.segments) < QualityThresholds.DIARIZATION_MIN_SEGMENTS:
            issues.append(f"Too few segments: {len(result.segments)}")
            score -= 0.3

        avg_confidence = sum(s.confidence for s in result.segments) / len(result.segments)
        if avg_confidence < QualityThresholds.DIARIZATION_MIN_AVG_CONFIDENCE:
            warnings.append(f"Low average confidence: {avg_confidence:.2f}")
            score -= 0.2

        speakers = set(s.speaker for s in result.segments)
        if len(speakers) < 2 and QualityThresholds.DIARIZATION_PREFER_MULTI_SPEAKER:
            warnings.append("Only one speaker detected")
            score -= 0.1
            suggestions.append("Ensure both provider and patient are audible")

        status = ValidationStatus.PASSED if score >= 0.7 else (
            ValidationStatus.WARNING if score >= 0.4 else ValidationStatus.FAILED
        )

        return ValidationResult(
            status=status,
            score=max(0.0, score),
            issues=issues,
            warnings=warnings,
            suggestions=suggestions
        )


class TranslationValidator:
    """Validates translation output"""

    @staticmethod
    def validate(
        original_segments: List,
        translated_segments: List[TranslatedSegment]
    ) -> ValidationResult:
        issues = []
        warnings = []
        suggestions = []
        score = 1.0

        if not translated_segments:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                score=0.0,
                issues=["No translated segments"]
            )

        empty_count = sum(1 for s in translated_segments if not s.translation)
        empty_ratio = empty_count / len(translated_segments)

        if empty_ratio > QualityThresholds.TRANSLATION_MAX_EMPTY_RATIO:
            issues.append(f"Too many empty translations: {empty_count}/{len(translated_segments)}")
            score -= 0.3
        elif empty_count > 0:
            warnings.append(f"{empty_count} segments without translation")
            score -= 0.1

        short_translations = 0
        for seg in translated_segments:
            if seg.text and seg.translation:
                ratio = len(seg.translation) / len(seg.text)
                if ratio < QualityThresholds.TRANSLATION_MIN_LENGTH_RATIO:
                    short_translations += 1

        if short_translations > len(translated_segments) * 0.2:
            warnings.append(f"{short_translations} translations seem too short")
            score -= 0.15

        status = ValidationStatus.PASSED if score >= 0.7 else (
            ValidationStatus.WARNING if score >= 0.4 else ValidationStatus.FAILED
        )

        return ValidationResult(
            status=status,
            score=max(0.0, score),
            issues=issues,
            warnings=warnings,
            suggestions=suggestions
        )


class SummarizationValidator:
    """Validates summarization output"""

    @staticmethod
    def validate(result: SummarizationResult) -> ValidationResult:
        issues = []
        warnings = []
        suggestions = []
        score = result.confidence_score if result.confidence_score else 0.5

        if not result.success:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                score=0.0,
                issues=[result.error or "Summarization failed"]
            )

        if not result.journal_entry:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                score=0.0,
                issues=["No journal entry generated"]
            )

        journal = result.journal_entry

        for field in QualityThresholds.SUMMARIZATION_REQUIRED_FIELDS:
            value = getattr(journal, field, None)
            if not value:
                issues.append(f"Missing required field: {field}")
                score -= 0.15
                suggestions.append(f"Try to extract {field} from the conversation")

        if journal.family_summary:
            if len(journal.family_summary) < QualityThresholds.SUMMARIZATION_MIN_SUMMARY_LENGTH:
                issues.append("Family summary too short")
                score -= 0.1
                suggestions.append("Expand the family summary with more details")

            uncertainty_phrases = ["not mentioned", "unclear", "no information", "unknown"]
            uncertainty_count = sum(
                1 for phrase in uncertainty_phrases
                if phrase in journal.family_summary.lower()
            )
            if uncertainty_count > 2:
                warnings.append("Many uncertain statements in summary")
                score -= 0.1
        else:
            issues.append("No family summary")
            score -= 0.2

        if result.confidence_score < QualityThresholds.SUMMARIZATION_MIN_CONFIDENCE:
            warnings.append(f"Low confidence: {result.confidence_score:.2f}")

        status = ValidationStatus.PASSED if score >= 0.6 and not issues else (
            ValidationStatus.WARNING if score >= 0.4 else ValidationStatus.FAILED
        )

        return ValidationResult(
            status=status,
            score=max(0.0, min(1.0, score)),
            issues=issues,
            warnings=warnings,
            suggestions=suggestions
        )


class QualityGateValidator:
    """Unified validator for all stages"""

    def __init__(self):
        self.transcription = TranscriptionValidator()
        self.diarization = DiarizationValidator()
        self.translation = TranslationValidator()
        self.summarization = SummarizationValidator()

    def validate_transcription(self, result: TranscriptionResult) -> ValidationResult:
        return self.transcription.validate(result)

    def validate_diarization(self, result: DiarizationResult) -> ValidationResult:
        return self.diarization.validate(result)

    def validate_translation(
        self,
        original_segments: List,
        translated_segments: List[TranslatedSegment]
    ) -> ValidationResult:
        return self.translation.validate(original_segments, translated_segments)

    def validate_summarization(self, result: SummarizationResult) -> ValidationResult:
        return self.summarization.validate(result)
