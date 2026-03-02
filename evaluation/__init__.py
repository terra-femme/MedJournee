# evaluation/__init__.py
"""
MEDJOURNEE EVALUATION FRAMEWORK

Comprehensive evaluation for the medical translation pipeline:
- Test cases with known medical conversations
- Automated quality evaluation
- Regression testing
- Performance benchmarking
"""

from evaluation.evaluator import (
    PipelineEvaluator,
    EvalResult,
    EvalReport,
    EvalMetric,
)
from evaluation.test_cases import (
    MEDICAL_CONVERSATION_TESTS,
    TestCase,
    get_test_suite,
)
from evaluation.regression import (
    RegressionRunner,
    run_regression_suite,
)

__all__ = [
    # Evaluator
    "PipelineEvaluator",
    "EvalResult",
    "EvalReport",
    "EvalMetric",
    # Test Cases
    "MEDICAL_CONVERSATION_TESTS",
    "TestCase",
    "get_test_suite",
    # Regression
    "RegressionRunner",
    "run_regression_suite",
]
