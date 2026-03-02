# guardrails/failsafe_manager.py
"""
FAILSAFE MANAGER GUARDRAIL

Priority: 100 (runs last - recovery)

Provides centralized fallback handling for pipeline failures.
Ensures users always get some useful output even when components fail.

Fallback levels (in order):
1. Retry - Attempt the operation again
2. Template - Use pre-built template with available data
3. Raw transcript - Return the raw transcript as-is
4. Error message - Graceful error with guidance

Extracted from agents/summarization_agent.py for centralized use.
"""

from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)


class FallbackLevel(str, Enum):
    """Fallback levels in order of preference"""
    RETRY = "retry"
    TEMPLATE = "template"
    RAW_TRANSCRIPT = "raw_transcript"
    ERROR_MESSAGE = "error_message"


@dataclass
class FallbackConfig:
    """Configuration for failsafe behavior"""
    max_retries: int = 2
    retry_delay_seconds: float = 1.0
    enable_template_fallback: bool = True
    enable_raw_fallback: bool = True


@dataclass
class FallbackResult:
    """Result of a fallback operation"""
    level: FallbackLevel
    success: bool
    data: Any = None
    error: Optional[str] = None
    attempts: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class FailsafeManager(BaseGuardrail):
    """
    Manages fallback behavior for pipeline failures.

    Ensures users always get useful output even when AI processing fails.
    This guardrail runs LAST to catch any unhandled failures.
    """

    NAME = "failsafe_manager"
    PRIORITY = 100  # Runs last
    DESCRIPTION = "Provides fallback handling for failures"

    # Template for basic journal entry fallback
    JOURNAL_TEMPLATE = {
        "visit_date": None,  # Filled dynamically
        "visit_type": "Medical Visit",
        "patient_name": None,
        "chief_complaint": "Medical consultation",
        "symptoms": [],
        "diagnoses": [],
        "treatments": [],
        "medications": [],
        "vital_signs": {},
        "follow_up_instructions": [],
        "next_appointments": [],
        "action_items": [],
        "patient_questions": [],
        "family_concerns": [],
        "family_summary": "",  # Filled with transcript preview
        "medical_terms": [],
        "processing_notes": ["Fallback entry - AI extraction failed"]
    }

    # User-friendly error messages
    ERROR_MESSAGES = {
        "transcription_failed": (
            "We couldn't process the audio recording. "
            "Please try recording again with clearer audio."
        ),
        "diarization_failed": (
            "We couldn't identify speakers in the recording. "
            "Your transcript is available but speaker labels may be inaccurate."
        ),
        "translation_failed": (
            "Translation service is temporarily unavailable. "
            "The original transcript is shown below."
        ),
        "summarization_failed": (
            "We couldn't generate a summary at this time. "
            "Your full transcript is preserved below."
        ),
        "general_error": (
            "Something went wrong processing your recording. "
            "Please try again or contact support if the issue persists."
        )
    }

    def __init__(
        self,
        enabled: bool = True,
        config: Optional[FallbackConfig] = None
    ):
        """
        Initialize failsafe manager.

        Args:
            enabled: Whether this guardrail is active
            config: Fallback configuration
        """
        super().__init__(enabled)
        self.config = config or FallbackConfig()

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check if failsafe intervention is needed.

        The failsafe manager doesn't "check" in the traditional sense -
        it's invoked when other operations fail.

        Args:
            context: Context with error information

        Returns:
            GuardrailResult - always ALLOW (we handle failures gracefully)
        """
        # If there's no error, nothing to do
        error = context.metadata.get("error")
        if not error:
            return self._allow("No error to handle")

        # Determine the stage that failed
        stage = context.stage or "unknown"
        error_type = f"{stage}_failed" if stage != "unknown" else "general_error"

        # Get user-friendly message
        user_message = self.ERROR_MESSAGES.get(
            error_type,
            self.ERROR_MESSAGES["general_error"]
        )

        return self._warn(
            message=f"Failsafe activated for {stage}: {error}",
            stage=stage,
            user_message=user_message,
            original_error=str(error)
        )

    async def create_fallback_journal(
        self,
        segments: List[Any],
        patient_name: Optional[str] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a fallback journal entry when AI processing fails.

        Args:
            segments: Available transcript segments
            patient_name: Optional patient name
            error: Error that caused the fallback

        Returns:
            Dict containing fallback journal entry
        """
        # Build transcript preview
        if segments:
            all_text = " ".join([
                getattr(s, 'text', str(s))
                for s in segments[:10]  # First 10 segments
            ])
            preview = all_text[:500] + "..." if len(all_text) > 500 else all_text
        else:
            preview = "No transcript available"

        # Create entry from template
        entry = self.JOURNAL_TEMPLATE.copy()
        entry["visit_date"] = datetime.now().strftime("%Y-%m-%d")
        entry["patient_name"] = patient_name
        entry["family_summary"] = (
            f"Medical visit with {len(segments) if segments else 0} conversation segments. "
            f"Full transcript: {preview}"
        )

        if error:
            entry["processing_notes"].append(f"Error: {error}")

        return entry

    async def execute_with_fallback(
        self,
        operation: Callable[..., Awaitable[Any]],
        fallback_data: Any,
        stage: str,
        *args,
        **kwargs
    ) -> FallbackResult:
        """
        Execute an operation with automatic fallback on failure.

        Args:
            operation: Async function to execute
            fallback_data: Data to use if operation fails
            stage: Name of the pipeline stage
            *args, **kwargs: Arguments for the operation

        Returns:
            FallbackResult with outcome
        """
        attempts = 0

        # Try the operation with retries
        for attempt in range(self.config.max_retries + 1):
            attempts += 1
            try:
                result = await operation(*args, **kwargs)

                # Check if result indicates success
                if hasattr(result, 'success') and not result.success:
                    error = getattr(result, 'error', 'Unknown error')
                    if attempt < self.config.max_retries:
                        continue  # Retry
                    else:
                        raise Exception(error)

                return FallbackResult(
                    level=FallbackLevel.RETRY if attempts > 1 else FallbackLevel.RETRY,
                    success=True,
                    data=result,
                    attempts=attempts
                )

            except Exception as e:
                if attempt < self.config.max_retries:
                    import asyncio
                    await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))
                    continue
                else:
                    # All retries exhausted
                    break

        # Retries failed - use fallback
        if self.config.enable_template_fallback and fallback_data is not None:
            return FallbackResult(
                level=FallbackLevel.TEMPLATE,
                success=True,
                data=fallback_data,
                error=f"{stage} failed after {attempts} attempts",
                attempts=attempts
            )

        # No fallback available
        return FallbackResult(
            level=FallbackLevel.ERROR_MESSAGE,
            success=False,
            error=self.ERROR_MESSAGES.get(f"{stage}_failed", self.ERROR_MESSAGES["general_error"]),
            attempts=attempts
        )

    def get_user_message(self, stage: str, error: Optional[str] = None) -> str:
        """
        Get a user-friendly error message for a failed stage.

        Args:
            stage: Pipeline stage that failed
            error: Optional technical error details

        Returns:
            User-friendly error message
        """
        error_key = f"{stage}_failed"
        return self.ERROR_MESSAGES.get(error_key, self.ERROR_MESSAGES["general_error"])

    async def handle_pipeline_failure(
        self,
        stage: str,
        error: str,
        partial_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle a pipeline failure gracefully.

        Args:
            stage: Stage where failure occurred
            error: Error message
            partial_results: Any partial results available

        Returns:
            Dict with graceful failure response
        """
        user_message = self.get_user_message(stage, error)

        response = {
            "success": False,
            "partial": True,
            "failed_stage": stage,
            "user_message": user_message,
            "partial_results": {},
            "fallback_used": True
        }

        # Include any successful partial results
        if "transcription" in partial_results:
            response["partial_results"]["transcription"] = partial_results["transcription"]

        if "diarization" in partial_results:
            response["partial_results"]["segments"] = partial_results["diarization"]

        if "translation" in partial_results:
            response["partial_results"]["translated_segments"] = partial_results["translation"]

        # Try to create a fallback summary if we have segments
        segments = partial_results.get("diarization", {}).get("segments", [])
        if segments and stage in ("summarization", "terminology"):
            response["partial_results"]["fallback_journal"] = await self.create_fallback_journal(
                segments=segments,
                patient_name=partial_results.get("patient_name"),
                error=error
            )

        return response


# Global instance
_failsafe: Optional[FailsafeManager] = None


def get_failsafe_manager() -> FailsafeManager:
    """Get or create the global failsafe manager."""
    global _failsafe
    if _failsafe is None:
        _failsafe = FailsafeManager()
    return _failsafe


# Convenience functions
async def create_fallback_journal(
    segments: List[Any],
    patient_name: Optional[str] = None
) -> Dict[str, Any]:
    """Create a fallback journal entry."""
    manager = get_failsafe_manager()
    return await manager.create_fallback_journal(segments, patient_name)


def get_error_message(stage: str) -> str:
    """Get user-friendly error message for a stage."""
    manager = get_failsafe_manager()
    return manager.get_user_message(stage)
