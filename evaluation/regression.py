# evaluation/regression.py
"""
REGRESSION TEST RUNNER

Automated regression testing for the MedJournee pipeline:
- Run test suites against pipeline
- Compare against baseline results
- Detect performance regressions
- Generate reports
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import json
import asyncio

from evaluation.evaluator import PipelineEvaluator, EvalReport
from evaluation.test_cases import (
    MEDICAL_CONVERSATION_TESTS,
    TestCase,
    get_test_suite,
)


@dataclass
class RegressionResult:
    """Result of comparing current vs baseline"""
    test_name: str
    current_score: float
    baseline_score: Optional[float]
    regression_detected: bool
    improvement_detected: bool
    delta: float  # current - baseline
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegressionReport:
    """Complete regression test report"""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    regressions_detected: int = 0
    improvements_detected: int = 0
    overall_score: float = 0.0
    baseline_score: Optional[float] = None
    test_reports: List[EvalReport] = field(default_factory=list)
    regression_results: List[RegressionResult] = field(default_factory=list)
    summary: str = ""

    @property
    def pass_rate(self) -> float:
        return self.passed_tests / self.total_tests if self.total_tests > 0 else 0.0

    @property
    def has_regressions(self) -> bool:
        return self.regressions_detected > 0


class RegressionRunner:
    """
    Run regression tests against the pipeline.

    Usage:
        runner = RegressionRunner()

        # Run all tests
        report = await runner.run_all()

        # Run specific category
        report = await runner.run_category("diabetes")

        # Compare against baseline
        report = await runner.run_with_baseline("baseline.json")

        # Save results
        runner.save_report(report, "results.json")
    """

    def __init__(
        self,
        evaluator: PipelineEvaluator = None,
        regression_threshold: float = 0.05  # 5% decrease = regression
    ):
        """
        Initialize regression runner.

        Args:
            evaluator: PipelineEvaluator instance
            regression_threshold: Score decrease threshold for regression
        """
        self.evaluator = evaluator or PipelineEvaluator()
        self.regression_threshold = regression_threshold
        self._baseline: Dict[str, float] = {}

    async def run_all(
        self,
        pipeline: Any = None
    ) -> RegressionReport:
        """
        Run all test cases.

        Args:
            pipeline: Pipeline instance (optional for synthetic tests)

        Returns:
            RegressionReport with results
        """
        return await self._run_tests(MEDICAL_CONVERSATION_TESTS, pipeline)

    async def run_category(
        self,
        category: str,
        pipeline: Any = None
    ) -> RegressionReport:
        """
        Run tests for a specific category.

        Args:
            category: Category name (diabetes, cardiovascular, etc.)
            pipeline: Pipeline instance (optional)

        Returns:
            RegressionReport with results
        """
        tests = get_test_suite(category=category)
        return await self._run_tests(tests, pipeline)

    async def run_with_baseline(
        self,
        baseline_path: str,
        pipeline: Any = None
    ) -> RegressionReport:
        """
        Run tests and compare against baseline.

        Args:
            baseline_path: Path to baseline JSON file
            pipeline: Pipeline instance (optional)

        Returns:
            RegressionReport with regression analysis
        """
        # Load baseline
        self._load_baseline(baseline_path)

        # Run tests
        report = await self.run_all(pipeline)

        # Add regression analysis
        report.regression_results = self._analyze_regressions(report.test_reports)
        report.regressions_detected = sum(
            1 for r in report.regression_results if r.regression_detected
        )
        report.improvements_detected = sum(
            1 for r in report.regression_results if r.improvement_detected
        )
        report.baseline_score = (
            sum(self._baseline.values()) / len(self._baseline)
            if self._baseline else None
        )

        return report

    async def _run_tests(
        self,
        test_cases: List[TestCase],
        pipeline: Any = None
    ) -> RegressionReport:
        """Run a set of test cases."""
        test_reports: List[EvalReport] = []
        passed = 0
        failed = 0

        for test_case in test_cases:
            if not test_case.transcript_text:
                continue

            if pipeline:
                # Run actual pipeline
                # This would need actual implementation based on pipeline interface
                report = await self._run_pipeline_test(test_case, pipeline)
            else:
                # Run synthetic evaluation
                report = await self.evaluator._evaluate_synthetic_test(test_case)

            test_reports.append(report)

            if report.passed:
                passed += 1
            else:
                failed += 1

        # Calculate overall score
        overall_score = (
            sum(r.overall_score for r in test_reports) / len(test_reports)
            if test_reports else 0.0
        )

        # Generate summary
        summary = self._generate_summary(passed, failed, test_reports)

        return RegressionReport(
            total_tests=len(test_reports),
            passed_tests=passed,
            failed_tests=failed,
            overall_score=overall_score,
            test_reports=test_reports,
            summary=summary
        )

    async def _run_pipeline_test(
        self,
        test_case: TestCase,
        pipeline: Any
    ) -> EvalReport:
        """
        Run a test case through the actual pipeline.

        This is a placeholder - actual implementation would depend on
        the pipeline interface and how to provide test audio.
        """
        # For now, fall back to synthetic evaluation
        return await self.evaluator._evaluate_synthetic_test(test_case)

    def _load_baseline(self, path: str):
        """Load baseline scores from file."""
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            # Extract scores by test name
            if 'test_reports' in data:
                for report in data['test_reports']:
                    self._baseline[report['test_name']] = report['overall_score']
            elif 'scores' in data:
                self._baseline = data['scores']
        except FileNotFoundError:
            print(f"Warning: Baseline file not found: {path}")
        except json.JSONDecodeError:
            print(f"Warning: Invalid baseline file: {path}")

    def _analyze_regressions(
        self,
        test_reports: List[EvalReport]
    ) -> List[RegressionResult]:
        """Analyze test results for regressions."""
        results = []

        for report in test_reports:
            baseline = self._baseline.get(report.test_name)
            current = report.overall_score

            if baseline is not None:
                delta = current - baseline
                regression = delta < -self.regression_threshold
                improvement = delta > self.regression_threshold
            else:
                delta = 0.0
                regression = False
                improvement = False

            results.append(RegressionResult(
                test_name=report.test_name,
                current_score=current,
                baseline_score=baseline,
                regression_detected=regression,
                improvement_detected=improvement,
                delta=delta,
                details={
                    "passed": report.passed,
                    "failed_metrics": [r.metric.value for r in report.failed_metrics]
                }
            ))

        return results

    def _generate_summary(
        self,
        passed: int,
        failed: int,
        reports: List[EvalReport]
    ) -> str:
        """Generate human-readable summary."""
        total = passed + failed
        pass_rate = (passed / total * 100) if total > 0 else 0

        summary = f"Regression Test Results: {passed}/{total} passed ({pass_rate:.1f}%)\n"

        if failed > 0:
            summary += "\nFailed tests:\n"
            for report in reports:
                if not report.passed:
                    summary += f"  - {report.test_name}: {report.summary}\n"

        return summary

    def save_report(self, report: RegressionReport, path: str):
        """
        Save report to JSON file.

        Args:
            report: RegressionReport to save
            path: Output file path
        """
        data = {
            "timestamp": report.timestamp,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "overall_score": report.overall_score,
            "baseline_score": report.baseline_score,
            "regressions_detected": report.regressions_detected,
            "improvements_detected": report.improvements_detected,
            "summary": report.summary,
            "test_reports": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "overall_score": r.overall_score,
                    "results": [
                        {
                            "metric": res.metric.value,
                            "passed": res.passed,
                            "score": res.score,
                            "errors": res.errors
                        }
                        for res in r.results
                    ]
                }
                for r in report.test_reports
            ],
            "regression_results": [
                {
                    "test_name": r.test_name,
                    "current_score": r.current_score,
                    "baseline_score": r.baseline_score,
                    "delta": r.delta,
                    "regression": r.regression_detected,
                    "improvement": r.improvement_detected
                }
                for r in report.regression_results
            ]
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def save_baseline(self, report: RegressionReport, path: str):
        """
        Save current results as new baseline.

        Args:
            report: RegressionReport to use as baseline
            path: Output file path
        """
        data = {
            "timestamp": report.timestamp,
            "overall_score": report.overall_score,
            "scores": {
                r.test_name: r.overall_score
                for r in report.test_reports
            }
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def print_report(self, report: RegressionReport):
        """Print report to console."""
        print("=" * 60)
        print("MEDJOURNEE REGRESSION TEST REPORT")
        print("=" * 60)
        print(f"Timestamp: {report.timestamp}")
        print(f"Total Tests: {report.total_tests}")
        print(f"Passed: {report.passed_tests}")
        print(f"Failed: {report.failed_tests}")
        print(f"Pass Rate: {report.pass_rate * 100:.1f}%")
        print(f"Overall Score: {report.overall_score:.3f}")

        if report.baseline_score is not None:
            delta = report.overall_score - report.baseline_score
            print(f"Baseline Score: {report.baseline_score:.3f}")
            print(f"Delta: {delta:+.3f}")

        if report.has_regressions:
            print(f"\n⚠️  REGRESSIONS DETECTED: {report.regressions_detected}")

        if report.improvements_detected > 0:
            print(f"\n✓ Improvements: {report.improvements_detected}")

        print("\n" + "-" * 60)
        print("INDIVIDUAL TEST RESULTS")
        print("-" * 60)

        for test_report in report.test_reports:
            status = "✓" if test_report.passed else "✗"
            print(f"{status} {test_report.test_name}: {test_report.overall_score:.3f}")

            if not test_report.passed:
                for result in test_report.failed_metrics:
                    print(f"    - {result.metric.value}: {result.errors}")

        print("=" * 60)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def run_regression_suite(
    category: str = None,
    baseline_path: str = None,
    output_path: str = None
) -> RegressionReport:
    """
    Convenience function to run regression tests.

    Args:
        category: Optional category filter
        baseline_path: Optional baseline file for comparison
        output_path: Optional output file path

    Returns:
        RegressionReport
    """
    runner = RegressionRunner()

    if baseline_path:
        report = await runner.run_with_baseline(baseline_path)
    elif category:
        report = await runner.run_category(category)
    else:
        report = await runner.run_all()

    runner.print_report(report)

    if output_path:
        runner.save_report(report, output_path)

    return report


# CLI entry point
if __name__ == "__main__":
    import sys

    async def main():
        category = sys.argv[1] if len(sys.argv) > 1 else None
        baseline = sys.argv[2] if len(sys.argv) > 2 else None
        output = sys.argv[3] if len(sys.argv) > 3 else None

        await run_regression_suite(category, baseline, output)

    asyncio.run(main())
