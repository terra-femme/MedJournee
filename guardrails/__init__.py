# guardrails/__init__.py
"""
MEDJOURNEE GUARDRAILS MODULE

Production-grade safety checks for medical translation.

The 10 Priority Guardrails:
1. Medical Advice Filter - Legal liability protection (Priority 1)
2. Audio Deletion Enforcer - Privacy promise (Priority 2)
3. Token Budget Guard - Cost control (Priority 3)
4. Rate Limiter - Cost control (Priority 5)
5. Hallucination Detector - Data quality (Priority 10)
6. Speaker Confidence Guard - Data quality (Priority 15)
7. PII Scrubber - Privacy compliance (Priority 20)
8. Failsafe Manager - User experience (Priority 100)
9. Circuit Breaker - API resilience (in tools/base.py)
10. Database Duplicate Prevention - Data integrity (UUID-based)

Usage:
    from guardrails import get_guardrail_registry, GuardrailContext

    # Run all guardrails
    registry = get_guardrail_registry()
    context = GuardrailContext(session_id="sess-123", text="...")
    result = await registry.run_all(context)

    # Run stage-specific guardrails
    result = await registry.run_for_stage("summarization", context)
"""

# Base classes
from guardrails.base import (
    BaseGuardrail,
    GuardrailAction,
    GuardrailResult,
    GuardrailContext,
)

# Individual guardrails
from guardrails.medical_advice_filter import MedicalAdviceFilter
from guardrails.audio_deletion_enforcer import (
    AudioDeletionEnforcer,
    get_audio_deletion_enforcer,
    register_audio,
    verify_audio_deleted,
)
from guardrails.hallucination_detector import (
    HallucinationDetector,
    filter_hallucination,
)
from guardrails.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    get_rate_limiter,
    check_rate_limit,
)
from guardrails.failsafe_manager import (
    FailsafeManager,
    FallbackLevel,
    get_failsafe_manager,
    create_fallback_journal,
    get_error_message,
)
from guardrails.speaker_confidence_guard import (
    SpeakerConfidenceGuard,
    SpeakerConfidenceConfig,
    get_speaker_confidence_guard,
    validate_speaker_confidence,
)
from guardrails.token_budget_guard import (
    TokenBudgetGuard,
    BudgetConfig,
    get_token_budget_guard,
    check_budget,
    get_budget_status,
)
from guardrails.pii_scrubber import (
    PIIScrubber,
    detect_pii,
    redact_pii,
    check_pii,
)

# Keep original PII detector for backwards compatibility
from guardrails.pii_detector import (
    PIIDetector,
    PIIResult,
    PIIScanResult,
    PIIType,
)

# Registry
from guardrails.guardrail_registry import (
    GuardrailRegistry,
    GuardrailExecutionResult,
    create_default_registry,
    get_guardrail_registry,
    run_guardrails,
    run_stage_guardrails,
)

__all__ = [
    # Base classes
    "BaseGuardrail",
    "GuardrailAction",
    "GuardrailResult",
    "GuardrailContext",
    # Guardrails
    "MedicalAdviceFilter",
    "AudioDeletionEnforcer",
    "HallucinationDetector",
    "RateLimiter",
    "RateLimitConfig",
    "FailsafeManager",
    "FallbackLevel",
    "SpeakerConfidenceGuard",
    "SpeakerConfidenceConfig",
    "TokenBudgetGuard",
    "BudgetConfig",
    "PIIScrubber",
    # Legacy PII exports (backwards compatibility)
    "PIIDetector",
    "PIIResult",
    "PIIScanResult",
    "PIIType",
    # Registry
    "GuardrailRegistry",
    "GuardrailExecutionResult",
    "create_default_registry",
    "get_guardrail_registry",
    # Convenience functions
    "get_audio_deletion_enforcer",
    "register_audio",
    "verify_audio_deleted",
    "filter_hallucination",
    "get_rate_limiter",
    "check_rate_limit",
    "get_failsafe_manager",
    "create_fallback_journal",
    "get_error_message",
    "get_speaker_confidence_guard",
    "validate_speaker_confidence",
    "get_token_budget_guard",
    "check_budget",
    "get_budget_status",
    "detect_pii",
    "redact_pii",
    "check_pii",
    "run_guardrails",
    "run_stage_guardrails",
]
