# evaluation/evaluator.py
"""
PIPELINE EVALUATOR

Evaluates the quality of pipeline outputs:
- Transcription accuracy (word error rate, keyword detection)
- Translation quality (semantic similarity, BLEU-like scores)
- Summarization quality (completeness, accuracy)
- Medical term detection (recall, precision)
- Medication extraction accuracy

Supports automated testing and regression detection.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from enum import Enum
import re


class EvalMetric(str, Enum):
    """Types of evaluation metrics"""
    TRANSCRIPTION_ACCURACY = "transcription_accuracy"
    KEYWORD_RECALL = "keyword_recall"
    TRANSLATION_QUALITY = "translation_quality"
    TERM_DETECTION_RECALL = "term_detection_recall"
    MEDICATION_ACCURACY = "medication_accuracy"
    DIAGNOSIS_ACCURACY = "diagnosis_accuracy"
    SUMMARIZATION_COMPLETENESS = "summarization_completeness"
    OVERALL_QUALITY = "overall_quality"


@dataclass
class EvalResult:
    """Result of evaluating a single aspect"""
    test_name: str
    metric: EvalMetric
    passed: bool
    score: float  # 0.0 - 1.0
    expected: Any
    actual: Any
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_perfect(self) -> bool:
        return self.score >= 1.0

    @property
    def needs_improvement(self) -> bool:
        return self.score < 0.8


@dataclass
class EvalReport:
    """Complete evaluation report for a test run"""
    test_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    passed: bool = False
    overall_score: float = 0.0
    results: List[EvalResult] = field(default_factory=list)
    summary: str = ""
    duration_ms: float = 0.0

    # Breakdown scores
    transcription_score: float = 0.0
    translation_score: float = 0.0
    summarization_score: float = 0.0
    terminology_score: float = 0.0

    @property
    def failed_metrics(self) -> List[EvalResult]:
        return [r for r in self.results if not r.passed]

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)


class PipelineEvaluator:
    """
    Evaluate pipeline output quality.

    Usage:
        evaluator = PipelineEvaluator()

        # Evaluate transcription
        result = evaluator.evaluate_transcription(
            actual_text="Patient has diabetes",
            expected_keywords=["diabetes", "patient"]
        )

        # Run full test case
        report = await evaluator.run_test_case(test_case, pipeline_result)
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize evaluator.

        Args:
            strict_mode: If True, use stricter thresholds
        """
        self.strict_mode = strict_mode

        # Quality thresholds
        self.thresholds = {
            "transcription_min": 0.7 if not strict_mode else 0.8,
            "translation_min": 0.6 if not strict_mode else 0.7,
            "summarization_min": 0.6 if not strict_mode else 0.7,
            "terminology_min": 0.7 if not strict_mode else 0.8,
        }

    def evaluate_transcription(
        self,
        actual_text: str,
        expected_keywords: List[str] = None,
        expected_text: str = None,
        min_confidence: float = None
    ) -> EvalResult:
        """
        Evaluate transcription quality.

        Args:
            actual_text: Transcribed text
            expected_keywords: Keywords that should appear
            expected_text: Full expected text (for WER calculation)
            min_confidence: Minimum confidence threshold

        Returns:
            EvalResult with transcription evaluation
        """
        errors = []
        details = {}
        score = 1.0

        actual_lower = actual_text.lower() if actual_text else ""

        # Keyword recall evaluation
        if expected_keywords:
            found_keywords = []
            missing_keywords = []

            for keyword in expected_keywords:
                if keyword.lower() in actual_lower:
                    found_keywords.append(keyword)
                else:
                    missing_keywords.append(keyword)

            keyword_recall = len(found_keywords) / len(expected_keywords) if expected_keywords else 1.0
            details["keyword_recall"] = keyword_recall
            details["found_keywords"] = found_keywords
            details["missing_keywords"] = missing_keywords

            score = keyword_recall

            if missing_keywords:
                errors.append(f"Missing keywords: {missing_keywords}")

        # Word Error Rate (simplified)
        if expected_text:
            wer = self._calculate_wer(expected_text, actual_text)
            details["word_error_rate"] = wer
            wer_score = max(0, 1 - wer)  # WER of 0 = score 1.0
            score = (score + wer_score) / 2 if expected_keywords else wer_score

        # Empty text check
        if not actual_text or not actual_text.strip():
            score = 0.0
            errors.append("Empty transcription")

        threshold = min_confidence or self.thresholds["transcription_min"]
        passed = score >= threshold

        return EvalResult(
            test_name="transcription",
            metric=EvalMetric.TRANSCRIPTION_ACCURACY,
            passed=passed,
            score=score,
            expected=expected_keywords or expected_text,
            actual=actual_text[:200] if actual_text else "",
            errors=errors,
            details=details
        )

    def evaluate_translation(
        self,
        original_text: str,
        translated_text: str,
        expected_keywords: List[str] = None,
        source_lang: str = "en",
        target_lang: str = "vi"
    ) -> EvalResult:
        """
        Evaluate translation quality.

        Args:
            original_text: Original text
            translated_text: Translated text
            expected_keywords: Keywords expected in translation
            source_lang: Source language
            target_lang: Target language

        Returns:
            EvalResult with translation evaluation
        """
        errors = []
        details = {}
        score = 1.0

        # Basic checks
        if not translated_text or not translated_text.strip():
            return EvalResult(
                test_name="translation",
                metric=EvalMetric.TRANSLATION_QUALITY,
                passed=False,
                score=0.0,
                expected="Non-empty translation",
                actual="",
                errors=["Empty translation"]
            )

        # Length ratio check (translations shouldn't be dramatically different in length)
        if original_text:
            length_ratio = len(translated_text) / len(original_text)
            details["length_ratio"] = length_ratio

            # Very short or very long translations may indicate issues
            if length_ratio < 0.3:
                score *= 0.7
                errors.append("Translation seems too short")
            elif length_ratio > 3.0:
                score *= 0.7
                errors.append("Translation seems too long")

        # Check for untranslated content (if source is detected in target)
        if source_lang == "en" and target_lang != "en":
            # Simple heuristic: check if common English words remain
            english_markers = ["the", "and", "is", "are", "was", "were", "have", "has"]
            untranslated_count = sum(
                1 for word in english_markers
                if f" {word} " in f" {translated_text.lower()} "
            )
            if untranslated_count > 3:
                score *= 0.8
                errors.append("Possible untranslated content detected")
                details["untranslated_markers"] = untranslated_count

        # Keyword check in translation (if provided)
        if expected_keywords:
            trans_lower = translated_text.lower()
            found = sum(1 for kw in expected_keywords if kw.lower() in trans_lower)
            keyword_score = found / len(expected_keywords)
            details["keyword_presence"] = keyword_score
            score = (score + keyword_score) / 2

        passed = score >= self.thresholds["translation_min"]

        return EvalResult(
            test_name="translation",
            metric=EvalMetric.TRANSLATION_QUALITY,
            passed=passed,
            score=score,
            expected=f"Translation from {source_lang} to {target_lang}",
            actual=translated_text[:200] if translated_text else "",
            errors=errors,
            details=details
        )

    def evaluate_terminology(
        self,
        detected_terms: List[str],
        expected_terms: List[str]
    ) -> EvalResult:
        """
        Evaluate medical terminology detection.

        Args:
            detected_terms: Terms detected by the pipeline
            expected_terms: Terms that should have been detected

        Returns:
            EvalResult with terminology evaluation
        """
        errors = []
        details = {}

        if not expected_terms:
            return EvalResult(
                test_name="terminology",
                metric=EvalMetric.TERM_DETECTION_RECALL,
                passed=True,
                score=1.0,
                expected=[],
                actual=detected_terms,
                details={"note": "No expected terms specified"}
            )

        # Normalize terms for comparison
        detected_lower = set(t.lower() for t in detected_terms)
        expected_lower = set(t.lower() for t in expected_terms)

        # Calculate recall (what percentage of expected terms were found)
        found = detected_lower & expected_lower
        missed = expected_lower - detected_lower
        extra = detected_lower - expected_lower

        recall = len(found) / len(expected_lower) if expected_lower else 1.0
        precision = len(found) / len(detected_lower) if detected_lower else 1.0

        # F1 score
        if precision + recall > 0:
            f1 = 2 * (precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        details["recall"] = recall
        details["precision"] = precision
        details["f1_score"] = f1
        details["found_terms"] = list(found)
        details["missed_terms"] = list(missed)
        details["extra_terms"] = list(extra)

        if missed:
            errors.append(f"Missed terms: {list(missed)}")

        passed = recall >= self.thresholds["terminology_min"]

        return EvalResult(
            test_name="terminology",
            metric=EvalMetric.TERM_DETECTION_RECALL,
            passed=passed,
            score=recall,  # Use recall as primary score
            expected=expected_terms,
            actual=detected_terms,
            errors=errors,
            details=details
        )

    def evaluate_medications(
        self,
        detected_medications: List[str],
        expected_medications: List[str]
    ) -> EvalResult:
        """
        Evaluate medication extraction.

        Args:
            detected_medications: Medications extracted by pipeline
            expected_medications: Expected medications

        Returns:
            EvalResult with medication evaluation
        """
        errors = []
        details = {}

        if not expected_medications:
            return EvalResult(
                test_name="medications",
                metric=EvalMetric.MEDICATION_ACCURACY,
                passed=True,
                score=1.0,
                expected=[],
                actual=detected_medications,
                details={"note": "No expected medications specified"}
            )

        # Normalize for comparison
        detected_lower = set(m.lower() for m in detected_medications)
        expected_lower = set(m.lower() for m in expected_medications)

        found = detected_lower & expected_lower
        missed = expected_lower - detected_lower

        recall = len(found) / len(expected_lower) if expected_lower else 1.0

        details["found_medications"] = list(found)
        details["missed_medications"] = list(missed)
        details["recall"] = recall

        if missed:
            errors.append(f"Missed medications: {list(missed)}")

        # Medications are critical - require high accuracy
        passed = recall >= 0.9  # 90% recall for medications

        return EvalResult(
            test_name="medications",
            metric=EvalMetric.MEDICATION_ACCURACY,
            passed=passed,
            score=recall,
            expected=expected_medications,
            actual=detected_medications,
            errors=errors,
            details=details
        )

    def evaluate_summarization(
        self,
        journal_entry: Any,
        expected_diagnoses: List[str] = None,
        expected_medications: List[str] = None,
        min_family_summary_length: int = 50
    ) -> EvalResult:
        """
        Evaluate summarization quality.

        Args:
            journal_entry: JournalEntry from pipeline
            expected_diagnoses: Expected diagnoses
            expected_medications: Expected medications
            min_family_summary_length: Minimum length for family summary

        Returns:
            EvalResult with summarization evaluation
        """
        errors = []
        details = {}
        scores = []

        if journal_entry is None:
            return EvalResult(
                test_name="summarization",
                metric=EvalMetric.SUMMARIZATION_COMPLETENESS,
                passed=False,
                score=0.0,
                expected="Valid journal entry",
                actual=None,
                errors=["No journal entry generated"]
            )

        # Check family summary
        family_summary = getattr(journal_entry, 'family_summary', '')
        if len(family_summary) < min_family_summary_length:
            errors.append(f"Family summary too short ({len(family_summary)} chars)")
            scores.append(0.5)
        else:
            scores.append(1.0)
        details["family_summary_length"] = len(family_summary)

        # Check diagnoses
        if expected_diagnoses:
            diagnoses = getattr(journal_entry, 'diagnoses', [])
            diagnoses_lower = set(d.lower() for d in diagnoses)
            expected_lower = set(d.lower() for d in expected_diagnoses)

            # Partial matching for diagnoses
            found = 0
            for expected in expected_lower:
                if any(expected in d or d in expected for d in diagnoses_lower):
                    found += 1

            diagnosis_score = found / len(expected_diagnoses)
            scores.append(diagnosis_score)
            details["diagnosis_recall"] = diagnosis_score

        # Check medications
        if expected_medications:
            medications = getattr(journal_entry, 'medications', [])
            med_names = [m.name.lower() if hasattr(m, 'name') else str(m).lower()
                        for m in medications]

            found = sum(1 for exp in expected_medications
                       if any(exp.lower() in m for m in med_names))
            med_score = found / len(expected_medications)
            scores.append(med_score)
            details["medication_recall"] = med_score

        # Check required fields exist
        required_fields = ['visit_type', 'chief_complaint', 'family_summary']
        for field_name in required_fields:
            value = getattr(journal_entry, field_name, None)
            if not value:
                errors.append(f"Missing required field: {field_name}")
                scores.append(0.5)
            else:
                scores.append(1.0)

        overall_score = sum(scores) / len(scores) if scores else 0.0
        passed = overall_score >= self.thresholds["summarization_min"]

        return EvalResult(
            test_name="summarization",
            metric=EvalMetric.SUMMARIZATION_COMPLETENESS,
            passed=passed,
            score=overall_score,
            expected={
                "diagnoses": expected_diagnoses,
                "medications": expected_medications
            },
            actual={
                "family_summary": family_summary[:100] if family_summary else "",
                "diagnoses": getattr(journal_entry, 'diagnoses', []),
            },
            errors=errors,
            details=details
        )

    async def run_test_case(
        self,
        test_case: Any,  # TestCase from test_cases.py
        pipeline_state: Any  # PipelineState from pipeline
    ) -> EvalReport:
        """
        Run a complete test case evaluation.

        Args:
            test_case: Test case definition
            pipeline_state: Pipeline execution result

        Returns:
            EvalReport with all evaluation results
        """
        import time
        start_time = time.time()

        results = []

        # Evaluate transcription
        transcription_text = ""
        if pipeline_state.diarization and pipeline_state.diarization.segments:
            transcription_text = " ".join(
                s.text for s in pipeline_state.diarization.segments
            )

        trans_result = self.evaluate_transcription(
            actual_text=transcription_text,
            expected_keywords=test_case.expected_terms,
            min_confidence=test_case.min_transcription_confidence
        )
        results.append(trans_result)

        # Evaluate terminology
        detected_terms = []
        if pipeline_state.terminology:
            detected_terms = [t.term for t in pipeline_state.terminology.terms_found]

        term_result = self.evaluate_terminology(
            detected_terms=detected_terms,
            expected_terms=test_case.expected_terms
        )
        results.append(term_result)

        # Evaluate medications (from summarization)
        if pipeline_state.summarization and pipeline_state.summarization.journal_entry:
            journal = pipeline_state.summarization.journal_entry
            detected_meds = [m.name for m in journal.medications]

            med_result = self.evaluate_medications(
                detected_medications=detected_meds,
                expected_medications=test_case.expected_medications
            )
            results.append(med_result)

            # Evaluate summarization
            sum_result = self.evaluate_summarization(
                journal_entry=journal,
                expected_diagnoses=test_case.expected_diagnoses,
                expected_medications=test_case.expected_medications
            )
            results.append(sum_result)

        # Calculate overall score
        if results:
            overall_score = sum(r.score for r in results) / len(results)
            all_passed = all(r.passed for r in results)
        else:
            overall_score = 0.0
            all_passed = False

        duration_ms = (time.time() - start_time) * 1000

        return EvalReport(
            test_name=test_case.name,
            passed=all_passed,
            overall_score=overall_score,
            results=results,
            duration_ms=duration_ms,
            transcription_score=trans_result.score if trans_result else 0.0,
            terminology_score=term_result.score if term_result else 0.0,
            summarization_score=sum_result.score if 'sum_result' in locals() else 0.0,
            summary=self._generate_summary(results, all_passed)
        )

    async def run_test_suite(
        self,
        test_cases: List[Any],
        pipeline: Any
    ) -> List[EvalReport]:
        """
        Run multiple test cases.

        Args:
            test_cases: List of test cases
            pipeline: Pipeline instance to run

        Returns:
            List of EvalReports
        """
        reports = []

        for test_case in test_cases:
            # Skip tests without transcript text (would need audio files)
            if not test_case.transcript_text:
                continue

            # Create mock pipeline state from transcript
            # In real usage, would run actual pipeline
            report = await self._evaluate_synthetic_test(test_case)
            reports.append(report)

        return reports

    async def _evaluate_synthetic_test(self, test_case: Any) -> EvalReport:
        """Evaluate a synthetic test case (using transcript text directly)."""
        results = []

        # Transcription evaluation (using transcript as "actual")
        trans_result = self.evaluate_transcription(
            actual_text=test_case.transcript_text,
            expected_keywords=test_case.expected_terms
        )
        results.append(trans_result)

        # Terminology would need actual pipeline run
        # For now, do keyword-based evaluation
        term_result = self.evaluate_terminology(
            detected_terms=self._extract_terms_from_text(
                test_case.transcript_text, test_case.expected_terms
            ),
            expected_terms=test_case.expected_terms
        )
        results.append(term_result)

        overall_score = sum(r.score for r in results) / len(results) if results else 0.0
        all_passed = all(r.passed for r in results)

        return EvalReport(
            test_name=test_case.name,
            passed=all_passed,
            overall_score=overall_score,
            results=results,
            summary=self._generate_summary(results, all_passed)
        )

    def _extract_terms_from_text(self, text: str, expected: List[str]) -> List[str]:
        """Simple extraction of expected terms from text."""
        text_lower = text.lower()
        return [term for term in expected if term.lower() in text_lower]

    def _calculate_wer(self, expected: str, actual: str) -> float:
        """Calculate Word Error Rate (simplified)."""
        expected_words = expected.lower().split()
        actual_words = actual.lower().split()

        if not expected_words:
            return 0.0 if not actual_words else 1.0

        # Simple WER using Levenshtein-like approach
        m, n = len(expected_words), len(actual_words)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if expected_words[i-1] == actual_words[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])

        return dp[m][n] / m

    def _generate_summary(self, results: List[EvalResult], passed: bool) -> str:
        """Generate human-readable summary."""
        if passed:
            return f"All {len(results)} checks passed."

        failed = [r for r in results if not r.passed]
        return f"{len(failed)}/{len(results)} checks failed: " + \
               ", ".join(r.metric.value for r in failed)
