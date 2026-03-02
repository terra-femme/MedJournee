# guardrails/base.py
"""
BASE GUARDRAIL INTERFACE

Provides the common interface for all MedJournee guardrails:
- GuardrailAction: Actions a guardrail can take
- GuardrailResult: Standardized result from any guardrail
- BaseGuardrail: Abstract base class for all guardrails

Priority levels (lower = runs first):
1-10: Legal/Compliance (Medical Advice Filter)
11-20: Privacy (Audio Deletion, PII)
21-50: Data Quality (Hallucination, Speaker Confidence)
51-100: Cost Control (Rate Limiter, Token Budget)
100+: Recovery (Failsafe Manager)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
from enum import Enum
from datetime import datetime


class GuardrailAction(str, Enum):
    """Actions a guardrail can take"""
    ALLOW = "allow"       # Let the content through unchanged
    WARN = "warn"         # Allow but flag for attention
    BLOCK = "block"       # Stop processing entirely
    MODIFY = "modify"     # Transform the content


@dataclass
class GuardrailResult:
    """Standardized result from any guardrail check"""
    guardrail_name: str
    passed: bool
    action: GuardrailAction
    message: Optional[str] = None
    modified_content: Optional[Any] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def should_block(self) -> bool:
        """Check if this result indicates processing should stop"""
        return self.action == GuardrailAction.BLOCK

    @property
    def should_modify(self) -> bool:
        """Check if this result includes modified content"""
        return self.action == GuardrailAction.MODIFY and self.modified_content is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            "guardrail": self.guardrail_name,
            "passed": self.passed,
            "action": self.action.value,
            "message": self.message,
            "has_modifications": self.modified_content is not None,
            "details": self.details,
            "timestamp": self.timestamp
        }


@dataclass
class GuardrailContext:
    """Context passed to guardrails for checking"""
    session_id: str
    user_id: Optional[str] = None
    family_id: Optional[str] = None
    stage: Optional[str] = None  # Current pipeline stage
    text: Optional[str] = None
    audio_files: List[str] = field(default_factory=list)
    segments: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_text(self, text: str) -> "GuardrailContext":
        """Create new context with updated text"""
        return GuardrailContext(
            session_id=self.session_id,
            user_id=self.user_id,
            family_id=self.family_id,
            stage=self.stage,
            text=text,
            audio_files=self.audio_files,
            segments=self.segments,
            metadata=self.metadata
        )


class BaseGuardrail(ABC):
    """
    Abstract base class for all MedJournee guardrails.

    Each guardrail must implement:
    - NAME: Unique identifier for the guardrail
    - PRIORITY: Execution order (lower = first)
    - check(): Async method to evaluate content
    - enforce(): Async method to apply the guardrail

    Usage:
        class MyGuardrail(BaseGuardrail):
            NAME = "my_guardrail"
            PRIORITY = 50

            async def check(self, context: GuardrailContext) -> GuardrailResult:
                # Evaluate content
                return GuardrailResult(...)

            async def enforce(self, context: GuardrailContext) -> GuardrailResult:
                # Apply guardrail logic
                return await self.check(context)
    """

    NAME: str = "base_guardrail"
    PRIORITY: int = 50  # Default middle priority
    DESCRIPTION: str = "Base guardrail"

    def __init__(self, enabled: bool = True):
        """
        Initialize guardrail.

        Args:
            enabled: Whether this guardrail is active
        """
        self.enabled = enabled
        self._check_count = 0
        self._block_count = 0
        self._modify_count = 0

    @abstractmethod
    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check content against this guardrail.

        Args:
            context: GuardrailContext with content to check

        Returns:
            GuardrailResult indicating action to take
        """
        pass

    async def enforce(self, context: GuardrailContext) -> GuardrailResult:
        """
        Enforce this guardrail (check + apply modifications).

        Default implementation just calls check().
        Override for guardrails that need additional enforcement logic.

        Args:
            context: GuardrailContext with content to check

        Returns:
            GuardrailResult with any modifications applied
        """
        if not self.enabled:
            return GuardrailResult(
                guardrail_name=self.NAME,
                passed=True,
                action=GuardrailAction.ALLOW,
                message="Guardrail disabled"
            )

        self._check_count += 1
        result = await self.check(context)

        if result.action == GuardrailAction.BLOCK:
            self._block_count += 1
        elif result.action == GuardrailAction.MODIFY:
            self._modify_count += 1

        return result

    def _allow(self, message: Optional[str] = None, **details) -> GuardrailResult:
        """Helper to create ALLOW result"""
        return GuardrailResult(
            guardrail_name=self.NAME,
            passed=True,
            action=GuardrailAction.ALLOW,
            message=message,
            details=details
        )

    def _warn(self, message: str, **details) -> GuardrailResult:
        """Helper to create WARN result"""
        return GuardrailResult(
            guardrail_name=self.NAME,
            passed=True,  # Warnings still pass
            action=GuardrailAction.WARN,
            message=message,
            details=details
        )

    def _block(self, message: str, **details) -> GuardrailResult:
        """Helper to create BLOCK result"""
        return GuardrailResult(
            guardrail_name=self.NAME,
            passed=False,
            action=GuardrailAction.BLOCK,
            message=message,
            details=details
        )

    def _modify(self, message: str, modified_content: Any, **details) -> GuardrailResult:
        """Helper to create MODIFY result"""
        return GuardrailResult(
            guardrail_name=self.NAME,
            passed=True,
            action=GuardrailAction.MODIFY,
            message=message,
            modified_content=modified_content,
            details=details
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get guardrail statistics"""
        return {
            "name": self.NAME,
            "priority": self.PRIORITY,
            "enabled": self.enabled,
            "checks": self._check_count,
            "blocks": self._block_count,
            "modifications": self._modify_count
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.NAME}, priority={self.PRIORITY}, enabled={self.enabled})>"
