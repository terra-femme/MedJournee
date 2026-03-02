#!/usr/bin/env python3
"""
MedJournee Automated Audio Testing Framework

CLI Test Runner for pipeline testing with pre-recorded audio fixtures.

Usage:
    python tests/test_pipeline.py                      # Run all fixtures
    python tests/test_pipeline.py --fixture english    # Run specific fixture
    python tests/test_pipeline.py --suite basic        # Run test suite
    python tests/test_pipeline.py --isolate english    # Compare Whisper API vs pipeline
    python tests/test_pipeline.py --record my_test     # Record new fixture
    python tests/test_pipeline.py --verbose            # Detailed output
    python tests/test_pipeline.py --list               # List available fixtures

Features:
    - Runs pre-recorded audio through the pipeline
    - Compares results to expected outputs
    - Detects regressions across test runs
    - API isolation mode to identify Whisper vs pipeline issues
    - Verbose mode for debugging with raw Whisper responses
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from io import BytesIO

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests import FIXTURES_DIR, EXPECTED_DIR, REPORTS_DIR


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TestResult:
    """Result of a single test"""
    fixture_name: str
    passed: bool = False
    score: float = 0.0

    # Transcription results
    transcription_text: str = ""
    expected_transcript: str = ""
    detected_language: str = ""
    confidence: float = 0.0
    was_filtered: bool = False
    filter_reason: Optional[str] = None

    # Accuracy metrics
    word_error_rate: Optional[float] = None  # 0.0 = perfect, 1.0 = completely wrong
    wer_passed: bool = True

    # Checks
    language_match: bool = False
    keywords_found: List[str] = field(default_factory=list)
    keywords_missing: List[str] = field(default_factory=list)
    hallucinations_detected: List[str] = field(default_factory=list)

    # Diarization
    speaker_count: int = 0
    segments: List[Dict] = field(default_factory=list)

    # Timing
    processing_time_ms: float = 0.0

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# WORD ERROR RATE CALCULATION
# =============================================================================

def calculate_wer(expected: str, actual: str) -> float:
    """
    Calculate Word Error Rate (WER) between expected and actual transcripts.

    WER = (Substitutions + Insertions + Deletions) / Words in Expected

    Returns:
        0.0 = perfect match
        1.0 = completely different
        >1.0 = more errors than words (very bad)
    """
    if not expected:
        return 0.0 if not actual else 1.0

    # Normalize: lowercase, remove punctuation, split into words
    def normalize(text: str) -> List[str]:
        import re
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
        return text.split()

    expected_words = normalize(expected)
    actual_words = normalize(actual)

    if not expected_words:
        return 0.0 if not actual_words else 1.0

    # Dynamic programming for Levenshtein distance at word level
    m, n = len(expected_words), len(actual_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # Base cases
    for i in range(m + 1):
        dp[i][0] = i  # Deletions
    for j in range(n + 1):
        dp[0][j] = j  # Insertions

    # Fill the matrix
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if expected_words[i-1] == actual_words[j-1]:
                dp[i][j] = dp[i-1][j-1]  # No operation needed
            else:
                dp[i][j] = 1 + min(
                    dp[i-1][j],      # Deletion
                    dp[i][j-1],      # Insertion
                    dp[i-1][j-1]     # Substitution
                )

    # WER = edit distance / number of words in reference
    return dp[m][n] / m


@dataclass
class IsolationResult:
    """Result of API isolation test"""
    fixture_name: str

    # Direct Whisper API results
    whisper_text: str = ""
    whisper_language: str = ""
    whisper_confidence: float = 0.0
    whisper_success: bool = False
    whisper_error: str = ""

    # Pipeline results
    pipeline_text: str = ""
    pipeline_language: str = ""
    pipeline_confidence: float = 0.0
    pipeline_filtered: bool = False
    pipeline_filter_reason: str = ""
    pipeline_success: bool = False
    pipeline_error: str = ""

    # Diagnosis
    diagnosis: str = ""
    recommendation: str = ""


@dataclass
class TestReport:
    """Complete test run report"""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    overall_score: float = 0.0
    results: List[TestResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed_tests / self.total_tests if self.total_tests > 0 else 0.0


# =============================================================================
# FIXTURE LOADER
# =============================================================================

class FixtureLoader:
    """Load and manage audio test fixtures"""

    def __init__(self):
        self.fixtures_config = self._load_config()

    def _load_config(self) -> Dict:
        """Load fixtures.json config"""
        config_path = EXPECTED_DIR / "fixtures.json"
        if not config_path.exists():
            return {"fixtures": {}, "test_suites": {}}

        with open(config_path) as f:
            return json.load(f)

    def list_fixtures(self) -> List[str]:
        """List available fixture names"""
        return list(self.fixtures_config.get("fixtures", {}).keys())

    def list_suites(self) -> List[str]:
        """List available test suites"""
        return list(self.fixtures_config.get("test_suites", {}).keys())

    def get_fixture(self, name: str) -> Optional[Dict]:
        """Get fixture configuration by name"""
        return self.fixtures_config.get("fixtures", {}).get(name)

    def get_suite_fixtures(self, suite_name: str) -> List[str]:
        """Get fixture names in a test suite"""
        return self.fixtures_config.get("test_suites", {}).get(suite_name, [])

    def load_audio(self, fixture_name: str) -> Optional[bytes]:
        """Load audio file for fixture"""
        fixture = self.get_fixture(fixture_name)
        if not fixture:
            return None

        audio_path = FIXTURES_DIR / fixture["audio_file"]
        if not audio_path.exists():
            return None

        with open(audio_path, "rb") as f:
            return f.read()

    def save_config(self):
        """Save updated fixtures config"""
        config_path = EXPECTED_DIR / "fixtures.json"
        with open(config_path, "w") as f:
            json.dump(self.fixtures_config, f, indent=2)


# =============================================================================
# MOCK AUDIO FILE CLASS
# =============================================================================

class MockAudioFile:
    """Mock audio file object for testing"""

    def __init__(self, content: bytes, filename: str = "test.webm", content_type: str = "audio/webm"):
        self.content = content
        self.filename = filename
        self.content_type = content_type
        self._position = 0

    async def read(self) -> bytes:
        return self.content

    async def seek(self, position: int):
        self._position = position


# =============================================================================
# TEST RUNNER
# =============================================================================

class PipelineTestRunner:
    """Run tests against the MedJournee pipeline"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.loader = FixtureLoader()

        # Import pipeline components lazily
        self._transcription_agent = None
        self._pipeline = None

    @property
    def transcription_agent(self):
        """Lazy load transcription agent"""
        if self._transcription_agent is None:
            from agents.transcription_agent import TranscriptionAgent
            self._transcription_agent = TranscriptionAgent()
        return self._transcription_agent

    @property
    def pipeline(self):
        """Lazy load pipeline"""
        if self._pipeline is None:
            from pipeline.orchestrator import MedJourneePipeline
            self._pipeline = MedJourneePipeline(
                enable_guardrails=False,
                enable_cost_tracking=False
            )
        return self._pipeline

    async def run_all(self) -> TestReport:
        """Run all available fixtures"""
        fixtures = self.loader.list_fixtures()
        return await self._run_fixtures(fixtures)

    async def run_fixture(self, fixture_name: str) -> TestReport:
        """Run a single fixture"""
        return await self._run_fixtures([fixture_name])

    async def run_suite(self, suite_name: str) -> TestReport:
        """Run a test suite"""
        fixtures = self.loader.get_suite_fixtures(suite_name)
        if not fixtures:
            print(f"Unknown suite: {suite_name}")
            print(f"Available suites: {self.loader.list_suites()}")
            return TestReport()
        return await self._run_fixtures(fixtures)

    async def _run_fixtures(self, fixture_names: List[str]) -> TestReport:
        """Run a list of fixtures"""
        start_time = time.time()
        results = []
        passed = 0
        failed = 0

        # Filter to fixtures that have audio files
        available = []
        for name in fixture_names:
            audio = self.loader.load_audio(name)
            if audio:
                available.append(name)
            else:
                print(f"  [SKIP] {name} - Audio file not found")

        if not available:
            print("\nNo audio fixtures available. Add .webm files to tests/audio_fixtures/")
            print("Or record new fixtures with: python tests/test_pipeline.py --record my_test")
            return TestReport()

        print(f"\n{'=' * 60}")
        print(f" MedJournee Pipeline Test")
        print(f"{'=' * 60}")

        for i, fixture_name in enumerate(available, 1):
            print(f"\n[{i}/{len(available)}] {fixture_name}")

            result = await self._test_fixture(fixture_name)
            results.append(result)

            if result.passed:
                passed += 1
                print(f"  [PASS] Score: {result.score:.2f}")
            else:
                failed += 1
                print(f"  [FAIL] Score: {result.score:.2f}")
                for error in result.errors:
                    print(f"    - {error}")

        total_time = (time.time() - start_time) * 1000
        overall_score = sum(r.score for r in results) / len(results) if results else 0.0

        report = TestReport(
            total_tests=len(results),
            passed_tests=passed,
            failed_tests=failed,
            overall_score=overall_score,
            results=results,
            duration_ms=total_time
        )

        self._print_summary(report)
        self._save_report(report)

        return report

    async def _test_fixture(self, fixture_name: str) -> TestResult:
        """Test a single fixture"""
        fixture = self.loader.get_fixture(fixture_name)
        audio_content = self.loader.load_audio(fixture_name)

        result = TestResult(fixture_name=fixture_name)

        if not fixture or not audio_content:
            result.errors.append("Fixture or audio not found")
            return result

        # Create mock audio file
        audio_file = MockAudioFile(
            audio_content,
            filename=fixture.get("audio_file", "test.webm"),
            content_type="audio/webm"
        )

        start_time = time.time()

        try:
            # Run transcription
            transcription = await self.transcription_agent.transcribe(audio_file)

            result.transcription_text = transcription.text
            result.detected_language = transcription.detected_language
            result.confidence = transcription.confidence
            result.was_filtered = transcription.was_filtered
            result.filter_reason = transcription.filter_reason

            if self.verbose:
                print(f"    Raw text: '{transcription.text[:100]}...' ({len(transcription.text)} chars)")
                print(f"    Language: {transcription.detected_language}")
                print(f"    Confidence: {transcription.confidence:.2f}")
                if transcription.was_filtered:
                    print(f"    Filtered: {transcription.filter_reason}")

            # Check language
            expected_lang = fixture.get("expected_language", "").lower()
            if expected_lang:
                detected = (transcription.detected_language or "").lower()
                result.language_match = detected.startswith(expected_lang[:2]) or expected_lang.startswith(detected[:2])
                if result.language_match:
                    print(f"    [OK] Language: {detected} (expected: {expected_lang})")
                else:
                    print(f"    [FAIL] Language: {detected} (expected: {expected_lang})")
                    result.errors.append(f"Language mismatch: got {detected}, expected {expected_lang}")

            # Check expected keywords
            expected_contains = fixture.get("expected_text_contains", [])
            text_lower = transcription.text.lower()
            for keyword in expected_contains:
                if keyword.lower() in text_lower:
                    result.keywords_found.append(keyword)
                else:
                    result.keywords_missing.append(keyword)

            if expected_contains:
                if result.keywords_missing:
                    print(f"    [FAIL] Missing keywords: {result.keywords_missing}")
                    result.errors.append(f"Missing keywords: {result.keywords_missing}")
                else:
                    print(f"    [OK] Contains: {result.keywords_found}")

            # Check for hallucinations
            not_contains = fixture.get("expected_text_not_contains", [])
            for bad_word in not_contains:
                if bad_word.lower() in text_lower:
                    result.hallucinations_detected.append(bad_word)

            if result.hallucinations_detected:
                print(f"    [FAIL] Hallucinations detected: {result.hallucinations_detected}")
                result.errors.append(f"Hallucinations: {result.hallucinations_detected}")
            elif not_contains:
                print(f"    [OK] No hallucinations")

            # Check confidence threshold
            min_conf = fixture.get("min_confidence", 0.5)
            if transcription.confidence >= min_conf:
                print(f"    [OK] Confidence: {transcription.confidence:.2f} (min: {min_conf})")
            else:
                print(f"    [WARN] Low confidence: {transcription.confidence:.2f} (min: {min_conf})")
                result.warnings.append(f"Low confidence: {transcription.confidence:.2f}")

            # Check if expected empty
            if fixture.get("expect_empty", False):
                if not transcription.text.strip():
                    print(f"    [OK] Empty as expected")
                else:
                    print(f"    [WARN] Expected empty, got: '{transcription.text[:50]}'")
                    result.warnings.append("Expected empty transcription")

            # Check Word Error Rate (WER) against ground truth transcript
            expected_transcript = fixture.get("expected_transcript", "")
            if expected_transcript:
                result.expected_transcript = expected_transcript
                result.word_error_rate = calculate_wer(expected_transcript, transcription.text)
                max_wer = fixture.get("max_wer", 0.3)  # Default: 30% error rate allowed

                if result.word_error_rate <= max_wer:
                    print(f"    [OK] WER: {result.word_error_rate:.1%} (max: {max_wer:.0%})")
                    result.wer_passed = True
                else:
                    print(f"    [FAIL] WER: {result.word_error_rate:.1%} (max: {max_wer:.0%})")
                    result.wer_passed = False
                    result.errors.append(f"WER too high: {result.word_error_rate:.1%} > {max_wer:.0%}")

                if self.verbose:
                    print(f"    Expected: '{expected_transcript}'")
                    print(f"    Actual:   '{transcription.text}'")

            # Calculate score
            score_components = []

            if expected_lang:
                score_components.append(1.0 if result.language_match else 0.0)

            if expected_contains:
                keyword_score = len(result.keywords_found) / len(expected_contains)
                score_components.append(keyword_score)

            if not_contains:
                hallucination_penalty = len(result.hallucinations_detected) / len(not_contains)
                score_components.append(1.0 - hallucination_penalty)

            # Add WER score (inverted: 0% WER = 1.0 score, 100% WER = 0.0 score)
            if result.word_error_rate is not None:
                wer_score = max(0.0, 1.0 - result.word_error_rate)
                score_components.append(wer_score)

            score_components.append(transcription.confidence)

            result.score = sum(score_components) / len(score_components) if score_components else 0.5
            result.passed = len(result.errors) == 0 and result.score >= 0.6

        except Exception as e:
            result.errors.append(f"Exception: {str(e)}")
            if self.verbose:
                import traceback
                traceback.print_exc()

        result.processing_time_ms = (time.time() - start_time) * 1000
        return result

    async def run_isolation_test(self, fixture_name: str) -> IsolationResult:
        """
        Run API isolation test to compare direct Whisper API vs pipeline.

        This helps diagnose whether issues are:
        - Whisper API issue: Both fail -> audio quality or Whisper problem
        - Pipeline issue: Direct API works, pipeline fails -> bug in code
        """
        print(f"\n{'=' * 60}")
        print(f" API Isolation Test: {fixture_name}")
        print(f"{'=' * 60}")

        audio_content = self.loader.load_audio(fixture_name)
        if not audio_content:
            print(f"Audio file not found for fixture: {fixture_name}")
            return IsolationResult(fixture_name=fixture_name)

        result = IsolationResult(fixture_name=fixture_name)

        # Test 1: Direct Whisper API (bypass all filtering)
        print("\n[1] Direct Whisper API")
        print("-" * 40)

        try:
            import openai
            import os
            from dotenv import load_dotenv
            load_dotenv()

            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=("test.webm", audio_content, "audio/webm"),
                response_format="verbose_json"
            )

            result.whisper_text = response.text.strip() if response.text else ""
            result.whisper_language = getattr(response, "language", "unknown")
            result.whisper_success = True

            # Estimate confidence from segments
            segments = getattr(response, "segments", [])
            if segments:
                probs = []
                for seg in segments:
                    no_speech = getattr(seg, "no_speech_prob", seg.get("no_speech_prob", 0) if isinstance(seg, dict) else 0)
                    probs.append(1.0 - no_speech)
                result.whisper_confidence = sum(probs) / len(probs) if probs else 0.5
            else:
                result.whisper_confidence = 0.5

            print(f"  Text: '{result.whisper_text[:100]}...' ({len(result.whisper_text)} chars)")
            print(f"  Language: {result.whisper_language}")
            print(f"  Confidence: {result.whisper_confidence:.2f}")

            if self.verbose and segments:
                print(f"  Segments: {len(segments)}")
                for i, seg in enumerate(segments[:3]):
                    seg_text = getattr(seg, "text", seg.get("text", "") if isinstance(seg, dict) else "")
                    no_speech = getattr(seg, "no_speech_prob", seg.get("no_speech_prob", 0) if isinstance(seg, dict) else 0)
                    print(f"    [{i}] no_speech={no_speech:.2f}: '{seg_text[:50]}'")

        except Exception as e:
            result.whisper_error = str(e)
            print(f"  ERROR: {e}")

        # Test 2: Pipeline (with all filtering)
        print("\n[2] MedJournee Pipeline")
        print("-" * 40)

        try:
            audio_file = MockAudioFile(audio_content)
            transcription = await self.transcription_agent.transcribe(audio_file)

            result.pipeline_text = transcription.text
            result.pipeline_language = transcription.detected_language
            result.pipeline_confidence = transcription.confidence
            result.pipeline_filtered = transcription.was_filtered
            result.pipeline_filter_reason = transcription.filter_reason or ""
            result.pipeline_success = transcription.success

            print(f"  Text: '{result.pipeline_text[:100]}...' ({len(result.pipeline_text)} chars)")
            print(f"  Language: {result.pipeline_language}")
            print(f"  Confidence: {result.pipeline_confidence:.2f}")
            if result.pipeline_filtered:
                print(f"  Filtered: {result.pipeline_filter_reason}")

        except Exception as e:
            result.pipeline_error = str(e)
            print(f"  ERROR: {e}")

        # Diagnosis
        print(f"\n{'=' * 60}")
        print(" DIAGNOSIS")
        print(f"{'=' * 60}")

        whisper_empty = not result.whisper_text.strip()
        pipeline_empty = not result.pipeline_text.strip()

        if whisper_empty and pipeline_empty:
            result.diagnosis = "AUDIO ISSUE"
            result.recommendation = "Audio quality may be too poor or too short for transcription"
            print("  Both Whisper API and Pipeline returned empty.")
            print("  -> Audio issue: Check audio quality, duration, or format")

        elif whisper_empty and not pipeline_empty:
            result.diagnosis = "UNEXPECTED"
            result.recommendation = "Pipeline returned text when Whisper did not - investigate"
            print("  Whisper API empty, but Pipeline has text.")
            print("  -> Unexpected behavior, investigate further")

        elif not whisper_empty and pipeline_empty:
            if result.pipeline_filtered:
                result.diagnosis = "FILTERED"
                result.recommendation = f"Review hallucination filter: {result.pipeline_filter_reason}"
                print("  Whisper API works, Pipeline filtered the output.")
                print(f"  -> Filter reason: {result.pipeline_filter_reason}")
                print("  -> May need to adjust hallucination detection")
            else:
                result.diagnosis = "PIPELINE BUG"
                result.recommendation = "Debug pipeline - Whisper works but pipeline fails"
                print("  Whisper API works, Pipeline returned empty (not filtered).")
                print("  -> Pipeline bug: Something in the processing is wrong")

        else:
            # Both have text - compare them
            whisper_lower = result.whisper_text.lower()
            pipeline_lower = result.pipeline_text.lower()

            if whisper_lower == pipeline_lower:
                result.diagnosis = "WORKING"
                result.recommendation = "Both produce identical output"
                print("  Both APIs return identical text.")
                print("  -> Working correctly!")
            else:
                # Check if pipeline is a subset (filtered version)
                common_words = set(pipeline_lower.split()) & set(whisper_lower.split())
                similarity = len(common_words) / max(len(whisper_lower.split()), 1)

                if similarity > 0.7:
                    result.diagnosis = "MINOR FILTERING"
                    result.recommendation = "Pipeline filtered some content, mostly working"
                    print(f"  Outputs are similar ({similarity:.0%} overlap).")
                    print("  -> Minor filtering applied, mostly working")
                else:
                    result.diagnosis = "SIGNIFICANT DIFFERENCE"
                    result.recommendation = "Large difference between Whisper and Pipeline - investigate"
                    print(f"  Outputs differ significantly ({similarity:.0%} overlap).")
                    print("  -> Investigate the filtering or processing logic")

        print(f"{'=' * 60}\n")

        return result

    def _print_summary(self, report: TestReport):
        """Print test summary"""
        print(f"\n{'=' * 60}")
        print(f" Summary")
        print(f"{'=' * 60}")
        print(f"  Total:  {report.total_tests}")
        print(f"  Passed: {report.passed_tests}")
        print(f"  Failed: {report.failed_tests}")
        print(f"  Score:  {report.overall_score:.2f}")
        print(f"  Time:   {report.duration_ms:.0f}ms")
        print(f"{'=' * 60}\n")

    def _save_report(self, report: TestReport):
        """Save report to file"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_path = REPORTS_DIR / f"{timestamp}.json"

        # Convert to dict for JSON serialization
        report_dict = {
            "timestamp": report.timestamp,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "overall_score": report.overall_score,
            "duration_ms": report.duration_ms,
            "results": [asdict(r) for r in report.results]
        }

        with open(report_path, "w") as f:
            json.dump(report_dict, f, indent=2)

        # Also save as 'latest.json' for easy access
        latest_path = REPORTS_DIR / "latest.json"
        with open(latest_path, "w") as f:
            json.dump(report_dict, f, indent=2)

        print(f"Report saved: {report_path}")


# =============================================================================
# CLI
# =============================================================================

def list_fixtures():
    """List available fixtures and suites"""
    loader = FixtureLoader()

    print("\nAvailable Fixtures:")
    print("-" * 40)
    for name in loader.list_fixtures():
        fixture = loader.get_fixture(name)
        audio_path = FIXTURES_DIR / fixture.get("audio_file", "")
        status = "[OK]" if audio_path.exists() else "[MISSING]"
        print(f"  {status} {name}")
        print(f"       {fixture.get('description', 'No description')}")

    print("\nAvailable Suites:")
    print("-" * 40)
    for suite in loader.list_suites():
        fixtures = loader.get_suite_fixtures(suite)
        print(f"  {suite}: {', '.join(fixtures)}")

    print("\nTo add a fixture:")
    print("  1. Add audio file to tests/audio_fixtures/")
    print("  2. Update tests/expected_outputs/fixtures.json")
    print("  3. Or use: python tests/test_pipeline.py --record my_test")
    print()


async def main():
    parser = argparse.ArgumentParser(
        description="MedJournee Pipeline Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tests/test_pipeline.py                      # Run all fixtures
    python tests/test_pipeline.py --fixture english    # Run specific fixture
    python tests/test_pipeline.py --suite basic        # Run test suite
    python tests/test_pipeline.py --isolate english    # API isolation test
    python tests/test_pipeline.py --verbose            # Detailed output
    python tests/test_pipeline.py --list               # List fixtures
    python tests/test_pipeline.py --record my_test     # Record new fixture
        """
    )

    parser.add_argument("--fixture", "-f", help="Run specific fixture by name")
    parser.add_argument("--suite", "-s", help="Run test suite (basic, full, etc.)")
    parser.add_argument("--isolate", "-i", help="Run API isolation test for fixture")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--list", "-l", action="store_true", help="List available fixtures")
    parser.add_argument("--record", "-r", help="Record new fixture with given name")
    parser.add_argument("--duration", "-d", type=int, default=15, help="Recording duration in seconds")

    args = parser.parse_args()

    if args.list:
        list_fixtures()
        return

    if args.record:
        from tests.fixture_recorder import record_fixture
        await record_fixture(args.record, args.duration)
        return

    runner = PipelineTestRunner(verbose=args.verbose)

    if args.isolate:
        await runner.run_isolation_test(args.isolate)
    elif args.fixture:
        await runner.run_fixture(args.fixture)
    elif args.suite:
        await runner.run_suite(args.suite)
    else:
        await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
