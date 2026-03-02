# guardrails/pii_scrubber.py
"""
PII SCRUBBER GUARDRAIL

Priority: 20 (privacy compliance)

Wraps the existing PIIDetector to conform to the BaseGuardrail interface.
Detects and redacts Protected Health Information (PHI) for HIPAA compliance.

This is guardrail #6 in the MedJournee priority list.
The underlying PIIDetector (pii_detector.py) is kept unchanged.
"""

from typing import Optional, List, Any

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)
from guardrails.pii_detector import PIIDetector, PIIResult


class PIIScrubber(BaseGuardrail):
    """
    Guardrail wrapper for PII/PHI detection and redaction.

    Wraps the existing PIIDetector to provide the BaseGuardrail interface
    while reusing all the excellent PII detection logic.
    """

    NAME = "pii_scrubber"
    PRIORITY = 20  # Privacy compliance
    DESCRIPTION = "Detects and redacts PII/PHI for HIPAA compliance"

    def __init__(self, enabled: bool = True, strict_mode: bool = True, auto_redact: bool = True):
        """
        Initialize PII scrubber.

        Args:
            enabled: Whether this guardrail is active
            strict_mode: If True, more aggressive detection (recommended for HIPAA)
            auto_redact: If True, automatically redact PII in MODIFY action
        """
        super().__init__(enabled)
        self.detector = PIIDetector(strict_mode=strict_mode)
        self.auto_redact = auto_redact

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check text for PII/PHI.

        Args:
            context: Context with text to check

        Returns:
            GuardrailResult with PII detection results
        """
        if not context.text:
            return self._allow("No text to check")

        # Run PII detection
        result = await self.detector.detect(context.text)

        if not result.has_pii:
            return self._allow("No PII detected")

        # PII found - determine action
        pii_types = [p.value for p in result.pii_types_found]
        match_count = result.count

        if self.auto_redact:
            # Redact and return modified content
            redacted_text = await self.detector.redact(context.text)
            return self._modify(
                message=f"Found and redacted {match_count} PII instances",
                modified_content=redacted_text,
                pii_types=pii_types,
                match_count=match_count,
                risk_level=result.risk_level
            )
        else:
            # Just warn about PII
            return self._warn(
                message=f"Found {match_count} PII instances: {pii_types}",
                pii_types=pii_types,
                match_count=match_count,
                risk_level=result.risk_level
            )

    async def enforce(self, context: GuardrailContext) -> GuardrailResult:
        """
        Enforce PII scrubbing - always redact when PII is found.

        Args:
            context: Context with text to check

        Returns:
            GuardrailResult with redacted content if PII found
        """
        if not self.enabled:
            return self._allow("Guardrail disabled")

        # For enforce, always auto-redact
        original_auto_redact = self.auto_redact
        self.auto_redact = True

        try:
            return await self.check(context)
        finally:
            self.auto_redact = original_auto_redact

    async def scan_segments(self, segments: List[Any]) -> GuardrailResult:
        """
        Scan multiple segments for PII.

        Args:
            segments: List of segments with 'text' attribute

        Returns:
            GuardrailResult with aggregate PII findings
        """
        scan_result = await self.detector.scan_segments(segments)

        if scan_result.total_pii_found == 0:
            return self._allow(
                message=f"Scanned {scan_result.total_segments} segments, no PII found",
                segments_scanned=scan_result.total_segments
            )

        return self._warn(
            message=f"Found PII in {scan_result.segments_with_pii}/{scan_result.total_segments} segments",
            segments_with_pii=scan_result.segments_with_pii,
            total_segments=scan_result.total_segments,
            total_pii_found=scan_result.total_pii_found,
            pii_by_type=scan_result.pii_by_type,
            risk_level=scan_result.risk_level
        )

    async def redact_segments(self, segments: List[Any]) -> List[Any]:
        """
        Redact PII from all segments.

        Pass-through to PIIDetector.redact_segments.

        Args:
            segments: List of segments with 'text' attribute

        Returns:
            Segments with PII redacted
        """
        return await self.detector.redact_segments(segments)


# Convenience functions
async def detect_pii(text: str) -> PIIResult:
    """Quick PII detection."""
    detector = PIIDetector()
    return await detector.detect(text)


async def redact_pii(text: str) -> str:
    """Quick PII redaction."""
    detector = PIIDetector()
    return await detector.redact(text)


async def check_pii(text: str, session_id: str = "check") -> GuardrailResult:
    """Check text for PII using guardrail interface."""
    scrubber = PIIScrubber()
    context = GuardrailContext(session_id=session_id, text=text)
    return await scrubber.check(context)
