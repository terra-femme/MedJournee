# guardrails/guardrail_registry.py
"""
GUARDRAIL REGISTRY

Central orchestration for all MedJournee guardrails.

Features:
- Register guardrails with priority ordering
- Run guardrails in priority order
- Stop on BLOCK action
- Aggregate results for reporting
- Stage-specific guardrail execution
"""

from typing import Optional, List, Dict, Any, Type
from dataclasses import dataclass, field
from datetime import datetime

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)

# Import all guardrails
from guardrails.medical_advice_filter import MedicalAdviceFilter
from guardrails.audio_deletion_enforcer import AudioDeletionEnforcer
from guardrails.hallucination_detector import HallucinationDetector
from guardrails.rate_limiter import RateLimiter
from guardrails.failsafe_manager import FailsafeManager
from guardrails.speaker_confidence_guard import SpeakerConfidenceGuard
from guardrails.token_budget_guard import TokenBudgetGuard
from guardrails.pii_scrubber import PIIScrubber


@dataclass
class GuardrailExecutionResult:
    """Result of executing all guardrails"""
    passed: bool
    blocked_by: Optional[str] = None
    block_reason: Optional[str] = None
    results: List[GuardrailResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    modifications: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "passed": self.passed,
            "blocked_by": self.blocked_by,
            "block_reason": self.block_reason,
            "results_count": len(self.results),
            "warnings": self.warnings,
            "modifications_count": len(self.modifications),
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp
        }


class GuardrailRegistry:
    """
    Central registry for all MedJournee guardrails.

    Manages guardrail registration, priority ordering, and execution.
    """

    # Mapping of pipeline stages to relevant guardrails
    STAGE_GUARDRAILS = {
        "pre_pipeline": ["rate_limiter", "token_budget_guard"],
        "transcription": ["hallucination_detector"],
        "diarization": ["speaker_confidence_guard", "audio_deletion_enforcer"],
        "translation": [],
        "terminology": [],
        "summarization": ["medical_advice_filter", "pii_detector"],
        "post_pipeline": ["audio_deletion_enforcer", "failsafe_manager"],
    }

    def __init__(self):
        """Initialize the registry."""
        self._guardrails: Dict[str, BaseGuardrail] = {}
        self._execution_stats: Dict[str, Dict[str, int]] = {}

    def register(self, guardrail: BaseGuardrail) -> None:
        """
        Register a guardrail.

        Args:
            guardrail: Guardrail instance to register
        """
        self._guardrails[guardrail.NAME] = guardrail
        self._execution_stats[guardrail.NAME] = {
            "checks": 0,
            "blocks": 0,
            "warnings": 0,
            "modifications": 0
        }

    def unregister(self, name: str) -> None:
        """
        Unregister a guardrail by name.

        Args:
            name: Name of guardrail to remove
        """
        self._guardrails.pop(name, None)
        self._execution_stats.pop(name, None)

    def get(self, name: str) -> Optional[BaseGuardrail]:
        """
        Get a guardrail by name.

        Args:
            name: Guardrail name

        Returns:
            Guardrail instance or None
        """
        return self._guardrails.get(name)

    def get_all(self) -> List[BaseGuardrail]:
        """Get all registered guardrails sorted by priority."""
        return sorted(
            self._guardrails.values(),
            key=lambda g: g.PRIORITY
        )

    def get_for_stage(self, stage: str) -> List[BaseGuardrail]:
        """
        Get guardrails relevant to a pipeline stage.

        Args:
            stage: Pipeline stage name

        Returns:
            List of guardrails for that stage, sorted by priority
        """
        guardrail_names = self.STAGE_GUARDRAILS.get(stage, [])
        guardrails = [
            self._guardrails[name]
            for name in guardrail_names
            if name in self._guardrails
        ]
        return sorted(guardrails, key=lambda g: g.PRIORITY)

    async def run_all(self, context: GuardrailContext) -> GuardrailExecutionResult:
        """
        Run all guardrails in priority order.

        Stops on first BLOCK action.

        Args:
            context: Guardrail context

        Returns:
            GuardrailExecutionResult with aggregated results
        """
        import time
        start_time = time.time()

        results = []
        warnings = []
        modifications = []

        for guardrail in self.get_all():
            if not guardrail.enabled:
                continue

            result = await guardrail.enforce(context)
            results.append(result)
            self._update_stats(guardrail.NAME, result)

            # Collect warnings
            if result.action == GuardrailAction.WARN:
                warnings.append(f"[{guardrail.NAME}] {result.message}")

            # Collect modifications
            if result.action == GuardrailAction.MODIFY and result.modified_content is not None:
                modifications.append({
                    "guardrail": guardrail.NAME,
                    "content": result.modified_content
                })
                # Update context with modified content if it's text
                if isinstance(result.modified_content, str):
                    context = context.with_text(result.modified_content)

            # Stop on BLOCK
            if result.action == GuardrailAction.BLOCK:
                return GuardrailExecutionResult(
                    passed=False,
                    blocked_by=guardrail.NAME,
                    block_reason=result.message,
                    results=results,
                    warnings=warnings,
                    modifications=modifications,
                    execution_time_ms=(time.time() - start_time) * 1000
                )

        return GuardrailExecutionResult(
            passed=True,
            results=results,
            warnings=warnings,
            modifications=modifications,
            execution_time_ms=(time.time() - start_time) * 1000
        )

    async def run_for_stage(
        self,
        stage: str,
        context: GuardrailContext
    ) -> GuardrailExecutionResult:
        """
        Run guardrails for a specific pipeline stage.

        Args:
            stage: Pipeline stage
            context: Guardrail context

        Returns:
            GuardrailExecutionResult
        """
        import time
        start_time = time.time()

        # Update context with stage
        context.stage = stage

        results = []
        warnings = []
        modifications = []

        for guardrail in self.get_for_stage(stage):
            if not guardrail.enabled:
                continue

            result = await guardrail.enforce(context)
            results.append(result)
            self._update_stats(guardrail.NAME, result)

            # Collect warnings
            if result.action == GuardrailAction.WARN:
                warnings.append(f"[{guardrail.NAME}] {result.message}")

            # Collect modifications
            if result.action == GuardrailAction.MODIFY and result.modified_content is not None:
                modifications.append({
                    "guardrail": guardrail.NAME,
                    "content": result.modified_content
                })
                if isinstance(result.modified_content, str):
                    context = context.with_text(result.modified_content)

            # Stop on BLOCK
            if result.action == GuardrailAction.BLOCK:
                return GuardrailExecutionResult(
                    passed=False,
                    blocked_by=guardrail.NAME,
                    block_reason=result.message,
                    results=results,
                    warnings=warnings,
                    modifications=modifications,
                    execution_time_ms=(time.time() - start_time) * 1000
                )

        return GuardrailExecutionResult(
            passed=True,
            results=results,
            warnings=warnings,
            modifications=modifications,
            execution_time_ms=(time.time() - start_time) * 1000
        )

    def _update_stats(self, name: str, result: GuardrailResult) -> None:
        """Update execution statistics."""
        if name not in self._execution_stats:
            self._execution_stats[name] = {
                "checks": 0, "blocks": 0, "warnings": 0, "modifications": 0
            }

        self._execution_stats[name]["checks"] += 1

        if result.action == GuardrailAction.BLOCK:
            self._execution_stats[name]["blocks"] += 1
        elif result.action == GuardrailAction.WARN:
            self._execution_stats[name]["warnings"] += 1
        elif result.action == GuardrailAction.MODIFY:
            self._execution_stats[name]["modifications"] += 1

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Get execution statistics for all guardrails."""
        return self._execution_stats.copy()

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of registered guardrails."""
        return {
            "total_guardrails": len(self._guardrails),
            "enabled": sum(1 for g in self._guardrails.values() if g.enabled),
            "disabled": sum(1 for g in self._guardrails.values() if not g.enabled),
            "guardrails": [
                {
                    "name": g.NAME,
                    "priority": g.PRIORITY,
                    "enabled": g.enabled,
                    "description": g.DESCRIPTION
                }
                for g in self.get_all()
            ],
            "stage_mapping": self.STAGE_GUARDRAILS,
            "stats": self._execution_stats
        }


def create_default_registry() -> GuardrailRegistry:
    """
    Create a registry with all default MedJournee guardrails.

    Returns:
        GuardrailRegistry with all guardrails registered
    """
    registry = GuardrailRegistry()

    # Register all guardrails
    registry.register(MedicalAdviceFilter())          # Priority 1
    registry.register(AudioDeletionEnforcer())        # Priority 2
    registry.register(TokenBudgetGuard())             # Priority 3
    registry.register(RateLimiter())                  # Priority 5
    registry.register(HallucinationDetector())        # Priority 10
    registry.register(SpeakerConfidenceGuard())       # Priority 15
    registry.register(PIIScrubber())                   # Priority 20 - wraps PIIDetector
    registry.register(FailsafeManager())              # Priority 100

    return registry


# Global registry instance
_registry: Optional[GuardrailRegistry] = None


def get_guardrail_registry() -> GuardrailRegistry:
    """Get or create the global guardrail registry."""
    global _registry
    if _registry is None:
        _registry = create_default_registry()
    return _registry


# Convenience functions
async def run_guardrails(context: GuardrailContext) -> GuardrailExecutionResult:
    """Run all guardrails on a context."""
    registry = get_guardrail_registry()
    return await registry.run_all(context)


async def run_stage_guardrails(
    stage: str,
    context: GuardrailContext
) -> GuardrailExecutionResult:
    """Run guardrails for a specific pipeline stage."""
    registry = get_guardrail_registry()
    return await registry.run_for_stage(stage, context)
