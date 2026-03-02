# guardrails/token_budget_guard.py
"""
TOKEN BUDGET GUARD

Priority: 3 (cost control - runs early)

Enforces budget limits before expensive operations.
Wraps cost_tracking_service.py for pre-operation budget checks.

Features:
- Pre-check budget before expensive operations
- Configurable per-session and daily limits
- Graceful handling when budget exceeded
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
)


@dataclass
class BudgetConfig:
    """Configuration for budget limits"""
    session_budget_usd: float = 2.0      # Max $2 per session
    daily_budget_usd: float = 50.0       # Max $50 per day
    warn_at_percent: float = 80.0        # Warn at 80% of budget


class TokenBudgetGuard(BaseGuardrail):
    """
    Guard that enforces cost budgets before expensive operations.

    This guard should run BEFORE any API calls to prevent
    going over budget.
    """

    NAME = "token_budget_guard"
    PRIORITY = 3  # Early - cost control
    DESCRIPTION = "Enforces budget limits before expensive operations"

    # Estimated costs for pre-checking
    ESTIMATED_COSTS = {
        "transcription": 0.01,       # ~1 minute of audio
        "diarization": 0.12,         # ~1 minute with AssemblyAI
        "summarization": 0.05,       # ~1K tokens GPT-4
        "translation": 0.00,         # Free (Google Translate)
        "terminology": 0.00,         # Local lookup
    }

    def __init__(
        self,
        enabled: bool = True,
        config: Optional[BudgetConfig] = None
    ):
        """
        Initialize token budget guard.

        Args:
            enabled: Whether this guardrail is active
            config: Budget configuration
        """
        super().__init__(enabled)
        self.config = config or BudgetConfig()

        # Try to import cost tracker
        try:
            from services.cost_tracking_service import get_cost_tracker
            self._cost_tracker = get_cost_tracker()
        except ImportError:
            self._cost_tracker = None

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check if budget allows the operation.

        Args:
            context: Context with session_id and operation

        Returns:
            GuardrailResult - BLOCK if over budget, ALLOW otherwise
        """
        if not self._cost_tracker:
            return self._allow("Cost tracking not available")

        session_id = context.session_id
        operation = context.stage or "unknown"

        # Get current session cost
        try:
            session_summary = await self._cost_tracker.get_session_cost(session_id)
            current_cost = session_summary.total_cost_usd
        except Exception:
            current_cost = 0.0

        # Get estimated cost for this operation
        estimated_cost = self.ESTIMATED_COSTS.get(operation, 0.05)

        # Check if already provided in metadata
        if "estimated_cost" in context.metadata:
            estimated_cost = context.metadata["estimated_cost"]

        projected_cost = current_cost + estimated_cost

        # Check session budget
        if projected_cost > self.config.session_budget_usd:
            return self._block(
                message=f"Session budget would be exceeded: ${projected_cost:.4f} > ${self.config.session_budget_usd}",
                current_cost=current_cost,
                estimated_cost=estimated_cost,
                projected_cost=projected_cost,
                budget=self.config.session_budget_usd,
                limit_type="session"
            )

        # Check daily budget
        try:
            daily_cost = await self._cost_tracker.get_total_cost()
        except Exception:
            daily_cost = 0.0

        daily_projected = daily_cost + estimated_cost
        if daily_projected > self.config.daily_budget_usd:
            return self._block(
                message=f"Daily budget would be exceeded: ${daily_projected:.4f} > ${self.config.daily_budget_usd}",
                current_daily_cost=daily_cost,
                estimated_cost=estimated_cost,
                projected_cost=daily_projected,
                budget=self.config.daily_budget_usd,
                limit_type="daily"
            )

        # Check warning threshold
        session_percent = (projected_cost / self.config.session_budget_usd) * 100
        if session_percent >= self.config.warn_at_percent:
            return self._warn(
                message=f"Session at {session_percent:.0f}% of budget",
                current_cost=current_cost,
                estimated_cost=estimated_cost,
                projected_cost=projected_cost,
                budget=self.config.session_budget_usd,
                percent_used=session_percent
            )

        return self._allow(
            message=f"Within budget: ${projected_cost:.4f} / ${self.config.session_budget_usd}",
            current_cost=current_cost,
            estimated_cost=estimated_cost,
            projected_cost=projected_cost,
            budget=self.config.session_budget_usd,
            percent_used=session_percent
        )

    async def check_operation_budget(
        self,
        session_id: str,
        operation: str,
        estimated_cost: Optional[float] = None
    ) -> GuardrailResult:
        """
        Convenience method to check budget for a specific operation.

        Args:
            session_id: Session identifier
            operation: Operation name (transcription, summarization, etc.)
            estimated_cost: Optional override for estimated cost

        Returns:
            GuardrailResult indicating if operation is allowed
        """
        context = GuardrailContext(
            session_id=session_id,
            stage=operation,
            metadata={"estimated_cost": estimated_cost} if estimated_cost else {}
        )
        return await self.check(context)

    async def record_cost(
        self,
        session_id: str,
        operation: str,
        actual_cost: float
    ) -> None:
        """
        Record actual cost after an operation completes.

        This is a pass-through to the cost tracker for convenience.

        Args:
            session_id: Session identifier
            operation: Operation that was performed
            actual_cost: Actual cost incurred
        """
        if not self._cost_tracker:
            return

        # Use appropriate recording method based on operation
        if operation == "transcription":
            # Estimate audio minutes from cost
            audio_minutes = actual_cost / 0.006  # Whisper pricing
            await self._cost_tracker.record_whisper_call(session_id, audio_minutes)
        elif operation == "diarization":
            audio_minutes = actual_cost / 0.12  # AssemblyAI pricing
            await self._cost_tracker.record_assemblyai_call(session_id, audio_minutes)
        elif operation == "summarization":
            # Estimate tokens from cost (GPT-4 Turbo output pricing)
            tokens = int(actual_cost / 0.00003)  # Rough estimate
            await self._cost_tracker.record_gpt4_call(session_id, tokens // 2, tokens // 2)

    async def get_budget_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get current budget status for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dict with budget status
        """
        if not self._cost_tracker:
            return {
                "available": True,
                "message": "Cost tracking not available",
                "session_cost": 0.0,
                "session_budget": self.config.session_budget_usd,
                "daily_cost": 0.0,
                "daily_budget": self.config.daily_budget_usd
            }

        try:
            session_summary = await self._cost_tracker.get_session_cost(session_id)
            session_cost = session_summary.total_cost_usd
        except Exception:
            session_cost = 0.0

        try:
            daily_cost = await self._cost_tracker.get_total_cost()
        except Exception:
            daily_cost = 0.0

        session_remaining = self.config.session_budget_usd - session_cost
        daily_remaining = self.config.daily_budget_usd - daily_cost

        return {
            "session_cost": round(session_cost, 4),
            "session_budget": self.config.session_budget_usd,
            "session_remaining": round(session_remaining, 4),
            "session_percent": round((session_cost / self.config.session_budget_usd) * 100, 1),
            "daily_cost": round(daily_cost, 4),
            "daily_budget": self.config.daily_budget_usd,
            "daily_remaining": round(daily_remaining, 4),
            "daily_percent": round((daily_cost / self.config.daily_budget_usd) * 100, 1),
            "can_proceed": session_remaining > 0 and daily_remaining > 0
        }


# Global instance
_guard: Optional[TokenBudgetGuard] = None


def get_token_budget_guard() -> TokenBudgetGuard:
    """Get or create the global token budget guard."""
    global _guard
    if _guard is None:
        _guard = TokenBudgetGuard()
    return _guard


# Convenience functions
async def check_budget(session_id: str, operation: str) -> GuardrailResult:
    """Check if budget allows an operation."""
    guard = get_token_budget_guard()
    return await guard.check_operation_budget(session_id, operation)


async def get_budget_status(session_id: str) -> Dict[str, Any]:
    """Get current budget status."""
    guard = get_token_budget_guard()
    return await guard.get_budget_status(session_id)
