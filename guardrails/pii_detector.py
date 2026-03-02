# guardrails/pii_detector.py
"""
PII/PHI DETECTOR - HIPAA Compliance

Detects and redacts Protected Health Information (PHI) and
Personally Identifiable Information (PII) in medical transcripts.

PHI Categories (HIPAA Safe Harbor):
1. Names
2. Geographic data smaller than state
3. Dates (except year) related to an individual
4. Phone numbers
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate/license numbers
12. Vehicle identifiers
13. Device identifiers
14. Web URLs
15. IP addresses
16. Biometric identifiers
17. Full-face photographs
18. Any other unique identifying number

This module focuses on text-based PHI detection.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class PIIType(str, Enum):
    """Types of PII/PHI that can be detected"""
    SSN = "ssn"
    PHONE = "phone"
    EMAIL = "email"
    DATE_OF_BIRTH = "dob"
    MEDICAL_RECORD_NUMBER = "mrn"
    HEALTH_PLAN_ID = "health_plan_id"
    ACCOUNT_NUMBER = "account_number"
    CREDIT_CARD = "credit_card"
    ADDRESS = "address"
    ZIP_CODE = "zip_code"
    IP_ADDRESS = "ip_address"
    DRIVER_LICENSE = "driver_license"
    PASSPORT = "passport"
    NAME = "name"


@dataclass
class PIIMatch:
    """A single PII match found in text"""
    pii_type: PIIType
    value: str
    start: int
    end: int
    confidence: float = 1.0

    @property
    def redacted(self) -> str:
        """Get redaction placeholder for this PII type"""
        return f"[{self.pii_type.value.upper()}_REDACTED]"


@dataclass
class PIIResult:
    """Result of PII detection on a single text"""
    has_pii: bool
    matches: List[PIIMatch] = field(default_factory=list)
    pii_types_found: List[PIIType] = field(default_factory=list)
    risk_level: str = "none"  # none, low, medium, high, critical

    @property
    def count(self) -> int:
        return len(self.matches)


@dataclass
class PIIScanResult:
    """Result of scanning multiple segments"""
    total_segments: int
    segments_with_pii: int
    total_pii_found: int
    pii_by_type: Dict[str, int] = field(default_factory=dict)
    risk_level: str = "none"
    segment_results: List[Tuple[int, PIIResult]] = field(default_factory=list)


class PIIDetector:
    """
    Detect and redact Protected Health Information (PHI).

    Usage:
        detector = PIIDetector()
        result = await detector.detect("Patient SSN: 123-45-6789")
        if result.has_pii:
            redacted = await detector.redact("Patient SSN: 123-45-6789")
            # Returns: "Patient SSN: [SSN_REDACTED]"
    """

    # Regex patterns for PHI/PII detection
    PATTERNS: Dict[PIIType, re.Pattern] = {
        # Social Security Number (XXX-XX-XXXX)
        PIIType.SSN: re.compile(
            r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'
        ),

        # Phone numbers (various formats)
        PIIType.PHONE: re.compile(
            r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
        ),

        # Email addresses
        PIIType.EMAIL: re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ),

        # Date of Birth patterns (MM/DD/YYYY, MM-DD-YYYY, etc.)
        PIIType.DATE_OF_BIRTH: re.compile(
            r'\b(?:DOB|date of birth|born|birthday|birthdate)[\s:]*'
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',
            re.IGNORECASE
        ),

        # Medical Record Number
        PIIType.MEDICAL_RECORD_NUMBER: re.compile(
            r'\b(?:MRN|medical record|record number|patient ID|chart number)'
            r'[\s:#]*([A-Z0-9]{4,})\b',
            re.IGNORECASE
        ),

        # Health Plan ID / Insurance ID
        PIIType.HEALTH_PLAN_ID: re.compile(
            r'\b(?:insurance|policy|member|subscriber|group)[\s]?'
            r'(?:ID|number|#)[\s:#]*([A-Z0-9]{6,})\b',
            re.IGNORECASE
        ),

        # Account numbers
        PIIType.ACCOUNT_NUMBER: re.compile(
            r'\b(?:account|acct)[\s]?(?:number|#|no)?[\s:#]*(\d{8,})\b',
            re.IGNORECASE
        ),

        # Credit card numbers (basic pattern)
        PIIType.CREDIT_CARD: re.compile(
            r'\b(?:4\d{3}|5[1-5]\d{2}|6(?:011|5\d{2})|3[47]\d{2})'
            r'[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
        ),

        # ZIP codes (5-digit or ZIP+4)
        PIIType.ZIP_CODE: re.compile(
            r'\b\d{5}(?:[-\s]\d{4})?\b'
        ),

        # IP addresses
        PIIType.IP_ADDRESS: re.compile(
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
            r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        ),

        # Driver's license (state-specific patterns would go here)
        PIIType.DRIVER_LICENSE: re.compile(
            r'\b(?:DL|driver\'?s?\s*license|license\s*#?)[\s:#]*'
            r'([A-Z0-9]{7,})\b',
            re.IGNORECASE
        ),
    }

    # Context keywords that indicate medical/health context
    MEDICAL_CONTEXT_KEYWORDS = [
        "patient", "doctor", "nurse", "hospital", "clinic", "medical",
        "health", "prescription", "medication", "diagnosis", "treatment",
        "insurance", "medicare", "medicaid", "appointment", "chart"
    ]

    # Keywords that increase PII likelihood
    PII_INDICATOR_KEYWORDS = {
        PIIType.SSN: ["ssn", "social security", "social-security"],
        PIIType.PHONE: ["phone", "call", "tel", "mobile", "cell", "contact"],
        PIIType.EMAIL: ["email", "e-mail", "mail"],
        PIIType.DATE_OF_BIRTH: ["dob", "birth", "born", "birthday", "age"],
        PIIType.MEDICAL_RECORD_NUMBER: ["mrn", "record", "chart", "patient id"],
        PIIType.HEALTH_PLAN_ID: ["insurance", "policy", "member id", "group"],
    }

    def __init__(self, strict_mode: bool = True):
        """
        Initialize PII detector.

        Args:
            strict_mode: If True, use stricter detection (more false positives
                        but fewer missed PHI). Recommended for HIPAA compliance.
        """
        self.strict_mode = strict_mode

    async def detect(self, text: str) -> PIIResult:
        """
        Detect PII/PHI in text.

        Args:
            text: Text to scan for PII

        Returns:
            PIIResult with all matches found
        """
        if not text or not text.strip():
            return PIIResult(has_pii=False)

        matches: List[PIIMatch] = []
        text_lower = text.lower()

        # Check each pattern
        for pii_type, pattern in self.PATTERNS.items():
            for match in pattern.finditer(text):
                # Calculate confidence based on context
                confidence = self._calculate_confidence(
                    pii_type, match.group(), text_lower, match.start()
                )

                # In strict mode, include all matches
                # In non-strict mode, require higher confidence
                if self.strict_mode or confidence >= 0.7:
                    matches.append(PIIMatch(
                        pii_type=pii_type,
                        value=match.group(),
                        start=match.start(),
                        end=match.end(),
                        confidence=confidence
                    ))

        # Deduplicate overlapping matches (keep highest confidence)
        matches = self._deduplicate_matches(matches)

        # Determine risk level
        risk_level = self._assess_risk_level(matches, text_lower)

        # Get unique PII types
        pii_types = list(set(m.pii_type for m in matches))

        return PIIResult(
            has_pii=len(matches) > 0,
            matches=matches,
            pii_types_found=pii_types,
            risk_level=risk_level
        )

    async def redact(self, text: str) -> str:
        """
        Redact all PII/PHI from text.

        Args:
            text: Text containing potential PII

        Returns:
            Text with PII replaced by [TYPE_REDACTED] placeholders
        """
        result = await self.detect(text)

        if not result.has_pii:
            return text

        # Sort matches by position (reverse order for safe replacement)
        sorted_matches = sorted(result.matches, key=lambda m: m.start, reverse=True)

        redacted_text = text
        for match in sorted_matches:
            redacted_text = (
                redacted_text[:match.start] +
                match.redacted +
                redacted_text[match.end:]
            )

        return redacted_text

    async def scan_segments(
        self,
        segments: List[any]
    ) -> PIIScanResult:
        """
        Scan multiple transcript segments for PII.

        Args:
            segments: List of segments with 'text' attribute

        Returns:
            PIIScanResult with aggregate statistics
        """
        segment_results: List[Tuple[int, PIIResult]] = []
        pii_by_type: Dict[str, int] = {}
        segments_with_pii = 0
        total_pii = 0

        for i, segment in enumerate(segments):
            text = getattr(segment, 'text', str(segment))
            result = await self.detect(text)

            if result.has_pii:
                segments_with_pii += 1
                total_pii += result.count
                segment_results.append((i, result))

                for pii_type in result.pii_types_found:
                    type_key = pii_type.value
                    pii_by_type[type_key] = pii_by_type.get(type_key, 0) + 1

        # Calculate overall risk level
        if total_pii == 0:
            risk_level = "none"
        elif PIIType.SSN.value in pii_by_type or PIIType.MEDICAL_RECORD_NUMBER.value in pii_by_type:
            risk_level = "critical"
        elif total_pii > 5 or PIIType.HEALTH_PLAN_ID.value in pii_by_type:
            risk_level = "high"
        elif total_pii > 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return PIIScanResult(
            total_segments=len(segments),
            segments_with_pii=segments_with_pii,
            total_pii_found=total_pii,
            pii_by_type=pii_by_type,
            risk_level=risk_level,
            segment_results=segment_results
        )

    async def redact_segments(
        self,
        segments: List[any]
    ) -> List[any]:
        """
        Redact PII from all segments.

        Args:
            segments: List of segments with 'text' attribute

        Returns:
            Segments with text redacted (creates copies, doesn't modify originals)
        """
        redacted = []

        for segment in segments:
            # Create a copy of the segment
            if hasattr(segment, 'model_copy'):
                # Pydantic model
                new_segment = segment.model_copy()
            elif hasattr(segment, 'copy'):
                new_segment = segment.copy()
            else:
                # Fallback: just use original and modify
                new_segment = segment

            # Redact text
            original_text = getattr(segment, 'text', str(segment))
            redacted_text = await self.redact(original_text)

            if hasattr(new_segment, 'text'):
                new_segment.text = redacted_text

            # Also redact translation if present
            if hasattr(segment, 'translation') and segment.translation:
                redacted_translation = await self.redact(segment.translation)
                new_segment.translation = redacted_translation

            redacted.append(new_segment)

        return redacted

    def _calculate_confidence(
        self,
        pii_type: PIIType,
        value: str,
        text_lower: str,
        position: int
    ) -> float:
        """Calculate confidence score for a potential PII match."""
        confidence = 0.5  # Base confidence

        # Check for indicator keywords nearby
        context_window = 50  # characters
        context_start = max(0, position - context_window)
        context = text_lower[context_start:position + len(value) + context_window]

        # Boost confidence if indicator keywords are present
        if pii_type in self.PII_INDICATOR_KEYWORDS:
            for keyword in self.PII_INDICATOR_KEYWORDS[pii_type]:
                if keyword in context:
                    confidence += 0.3
                    break

        # Boost if in medical context
        for keyword in self.MEDICAL_CONTEXT_KEYWORDS:
            if keyword in text_lower:
                confidence += 0.1
                break

        # Type-specific validation
        if pii_type == PIIType.SSN:
            # SSN should have 9 digits
            digits = re.sub(r'\D', '', value)
            if len(digits) == 9:
                confidence += 0.2
                # Check for invalid SSN patterns
                if digits.startswith('000') or digits.startswith('666'):
                    confidence -= 0.3

        elif pii_type == PIIType.PHONE:
            # Valid US phone numbers
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 10:
                confidence += 0.1

        elif pii_type == PIIType.CREDIT_CARD:
            # Luhn algorithm check would go here
            confidence += 0.1

        return min(1.0, max(0.0, confidence))

    def _deduplicate_matches(
        self,
        matches: List[PIIMatch]
    ) -> List[PIIMatch]:
        """Remove overlapping matches, keeping highest confidence."""
        if not matches:
            return matches

        # Sort by start position
        sorted_matches = sorted(matches, key=lambda m: (m.start, -m.confidence))

        result = []
        last_end = -1

        for match in sorted_matches:
            if match.start >= last_end:
                result.append(match)
                last_end = match.end
            elif match.confidence > result[-1].confidence:
                # Replace if higher confidence
                result[-1] = match
                last_end = match.end

        return result

    def _assess_risk_level(
        self,
        matches: List[PIIMatch],
        text_lower: str
    ) -> str:
        """Assess overall risk level based on PII found."""
        if not matches:
            return "none"

        # Critical: SSN or MRN in medical context
        has_ssn = any(m.pii_type == PIIType.SSN for m in matches)
        has_mrn = any(m.pii_type == PIIType.MEDICAL_RECORD_NUMBER for m in matches)
        in_medical_context = any(k in text_lower for k in self.MEDICAL_CONTEXT_KEYWORDS)

        if (has_ssn or has_mrn) and in_medical_context:
            return "critical"

        # High: Multiple PII types or sensitive types
        pii_types = set(m.pii_type for m in matches)
        sensitive_types = {PIIType.SSN, PIIType.MEDICAL_RECORD_NUMBER,
                         PIIType.HEALTH_PLAN_ID, PIIType.CREDIT_CARD}

        if len(pii_types) >= 3 or pii_types & sensitive_types:
            return "high"

        # Medium: Multiple matches or certain types
        if len(matches) >= 3 or PIIType.DATE_OF_BIRTH in pii_types:
            return "medium"

        # Low: Basic PII (phone, email)
        return "low"
