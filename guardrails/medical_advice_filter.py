# guardrails/medical_advice_filter.py
"""
MEDICAL ADVICE FILTER GUARDRAIL

Priority: 1 (highest - legal liability protection)

Prevents AI from giving medical advice while allowing:
- Transcribed doctor quotes: "[Provider]: Take 500mg of aspirin"
- Factual medical information from the conversation
- Patient education materials from healthcare providers

Blocks patterns like:
- "You should take..."
- "I recommend..."
- "Your diagnosis is..."

This guardrail protects against legal liability by ensuring
MedJournee never gives medical advice - it only translates
and summarizes what healthcare providers said.
"""

import re
from typing import Optional, List, Tuple

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)


class MedicalAdviceFilter(BaseGuardrail):
    """
    Filter that prevents AI-generated medical advice.

    This is MedJournee's most critical guardrail for legal protection.
    We translate medical conversations - we do NOT provide medical advice.
    """

    NAME = "medical_advice_filter"
    PRIORITY = 1  # Highest priority - legal liability
    DESCRIPTION = "Prevents AI from giving medical advice"

    # Patterns that indicate AI is giving advice (BLOCK these)
    ADVICE_PATTERNS = [
        # Direct recommendations
        (r'\b(?:you\s+should|i\s+recommend|i\s+suggest|i\s+advise)\s+(?:that\s+)?(?:you\s+)?(?:take|start|stop|try|consider|use|avoid)', "direct_recommendation"),
        (r'\b(?:my\s+advice|my\s+recommendation)\s+(?:is|would\s+be)', "explicit_advice"),

        # Diagnosis claims
        (r'\b(?:your|the)\s+diagnosis\s+(?:is|appears?\s+to\s+be|seems?\s+to\s+be)', "diagnosis_claim"),
        (r'\byou\s+(?:have|appear\s+to\s+have|seem\s+to\s+have|might\s+have|probably\s+have)\s+\w+', "condition_claim"),

        # Treatment directives
        (r'\b(?:you\s+need\s+to|you\s+must|you\s+have\s+to)\s+(?:take|start|stop|see|get)', "treatment_directive"),
        (r'\btake\s+\d+\s*(?:mg|ml|pills?|tablets?|capsules?)\s+(?:of\s+)?\w+\s+(?:daily|twice|three|every)', "dosage_directive"),

        # Prognosis claims
        (r'\byou\s+will\s+(?:recover|get\s+better|improve|heal)', "prognosis_claim"),
        (r'\bthis\s+(?:will|should)\s+(?:cure|fix|resolve|heal)', "cure_claim"),
    ]

    # Patterns that indicate quoted provider speech (ALLOW these)
    PROVIDER_QUOTE_PATTERNS = [
        r'\[(?:Provider|Doctor|Physician|Nurse|SPEAKER_1|Healthcare\s+Provider)\]:\s*',
        r'(?:The\s+)?(?:doctor|provider|physician|nurse)\s+said\s+(?:that\s+)?["\']',
        r'(?:According\s+to|As\s+(?:stated|mentioned)\s+by)\s+(?:the\s+)?(?:doctor|provider|physician)',
        r'(?:Dr\.|Doctor)\s+\w+\s+(?:said|stated|mentioned|recommended|prescribed)',
    ]

    # Disclaimer to add to AI-generated summaries
    DISCLAIMER = (
        "\n\n---\n"
        "This summary is for informational purposes only and does not constitute "
        "medical advice. Always consult with your healthcare provider for medical decisions."
    )

    # Short disclaimer for inline use
    SHORT_DISCLAIMER = "[Note: Consult your healthcare provider for medical advice]"

    def __init__(self, enabled: bool = True, add_disclaimer: bool = True):
        """
        Initialize medical advice filter.

        Args:
            enabled: Whether this guardrail is active
            add_disclaimer: Whether to add disclaimer to summaries
        """
        super().__init__(enabled)
        self.add_disclaimer = add_disclaimer

        # Compile patterns
        self._advice_patterns = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in self.ADVICE_PATTERNS
        ]
        self._provider_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.PROVIDER_QUOTE_PATTERNS
        ]

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check text for inappropriate medical advice.

        Args:
            context: Context with text to check

        Returns:
            GuardrailResult indicating action to take
        """
        if not context.text:
            return self._allow("No text to check")

        text = context.text

        # Check for advice patterns
        advice_matches = self._find_advice_patterns(text)

        if not advice_matches:
            # No advice found - check if we should add disclaimer
            if self.add_disclaimer and self._is_ai_summary(context):
                return self._modify(
                    message="Adding medical disclaimer to AI summary",
                    modified_content=text + self.DISCLAIMER,
                    is_summary=True
                )
            return self._allow("No medical advice detected")

        # Found potential advice - check if it's quoted provider speech
        filtered_matches = []
        for match, pattern_name, matched_text in advice_matches:
            if not self._is_provider_quote(text, match.start()):
                filtered_matches.append((match, pattern_name, matched_text))

        if not filtered_matches:
            return self._allow(
                "Medical advice found but attributed to provider",
                provider_quotes=len(advice_matches)
            )

        # We have unattributed medical advice - this is a problem
        return self._block(
            message=f"AI-generated medical advice detected: {filtered_matches[0][1]}",
            advice_type=filtered_matches[0][1],
            matched_text=filtered_matches[0][2],
            match_count=len(filtered_matches)
        )

    async def enforce(self, context: GuardrailContext) -> GuardrailResult:
        """
        Enforce medical advice filter with optional modification.

        For BLOCK results, we can optionally modify the content instead
        of blocking entirely, by adding warnings inline.
        """
        result = await self.check(context)

        # If blocked and we have the option to modify instead
        if result.action == GuardrailAction.BLOCK and context.metadata.get("allow_modification", False):
            # Replace advice with warning
            modified_text = self._redact_advice(context.text)
            return self._modify(
                message="Medical advice redacted",
                modified_content=modified_text,
                original_action="block",
                redacted_count=1
            )

        return result

    def _find_advice_patterns(self, text: str) -> List[Tuple[re.Match, str, str]]:
        """Find all advice pattern matches in text."""
        matches = []
        for pattern, name in self._advice_patterns:
            for match in pattern.finditer(text):
                matches.append((match, name, match.group()))
        return matches

    def _is_provider_quote(self, text: str, position: int) -> bool:
        """
        Check if the text at position is within a provider quote.

        Looks backwards from position to find provider attribution.
        """
        # Look at the 200 characters before this position
        context_start = max(0, position - 200)
        context = text[context_start:position]

        # Check for provider quote patterns
        for pattern in self._provider_patterns:
            if pattern.search(context):
                return True

        # Also check for bracket notation
        # Find the most recent opening bracket
        last_bracket = context.rfind('[')
        if last_bracket >= 0:
            bracket_content = context[last_bracket:]
            if re.search(r'\[(?:Provider|Doctor|SPEAKER_1)', bracket_content, re.IGNORECASE):
                return True

        return False

    def _is_ai_summary(self, context: GuardrailContext) -> bool:
        """Check if this content is an AI-generated summary."""
        return context.stage in ("summarization", "summary", "journal_entry")

    def _redact_advice(self, text: str) -> str:
        """Replace medical advice with warning text."""
        result = text
        for pattern, name in self._advice_patterns:
            result = pattern.sub(
                f"{self.SHORT_DISCLAIMER} [Content modified for safety]",
                result
            )
        return result


# Convenience function
async def check_medical_advice(text: str, session_id: str = "unknown") -> GuardrailResult:
    """
    Quick check if text contains inappropriate medical advice.

    Args:
        text: Text to check
        session_id: Session identifier

    Returns:
        GuardrailResult
    """
    filter = MedicalAdviceFilter()
    context = GuardrailContext(session_id=session_id, text=text)
    return await filter.check(context)
