# models/schemas.py
"""
MEDJOURNEE SCHEMAS - Single Source of Truth

Schema-Driven Design:
- Validate inputs at every stage
- Produce predictable outputs
- Avoid hallucination through strict formats
- Enable type-safe agent communication

All agents use these schemas for input/output contracts.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from enum import Enum
import uuid


# =============================================================================
# ENUMS - Explicit state values
# =============================================================================

class SpeakerRole(str, Enum):
    """Speaker roles in medical conversation"""
    HEALTHCARE_PROVIDER = "Healthcare Provider"
    PATIENT_FAMILY = "Patient/Family"
    UNKNOWN = "Unknown"


class TermSource(str, Enum):
    """Source of medical term definition"""
    UOFM_DICTIONARY = "UofM_Dictionary"
    GPT_GENERATED = "GPT_Generated"
    ABBREVIATION = "Abbreviation"


class PipelineStage(str, Enum):
    """Explicit pipeline stages for tracking"""
    INITIALIZED = "initialized"
    TRANSCRIPTION = "transcription"
    TRANSCRIPTION_VALIDATION = "transcription_validation"
    DIARIZATION = "diarization"
    DIARIZATION_VALIDATION = "diarization_validation"
    TRANSLATION = "translation"
    TRANSLATION_VALIDATION = "translation_validation"
    TERMINOLOGY = "terminology"
    SUMMARIZATION = "summarization"
    SUMMARIZATION_VALIDATION = "summarization_validation"
    SELF_CORRECTION = "self_correction"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationStatus(str, Enum):
    """Validation result status"""
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


# =============================================================================
# BASE RESULT CLASS - All agent outputs inherit from this
# =============================================================================

class AgentResult(BaseModel):
    """
    Base class for all agent outputs.
    Ensures every agent returns success status and optional error.
    """
    success: bool
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None

    class Config:
        extra = "allow"  # Allow additional fields in subclasses


# =============================================================================
# AGENT 1: TRANSCRIPTION SCHEMAS
# =============================================================================

class TranscriptionInput(BaseModel):
    """Input schema for transcription agent"""
    audio_content: bytes = Field(..., description="Raw audio bytes")
    content_type: str = Field(default="audio/webm", description="MIME type")
    filename: str = Field(default="audio.webm")

    class Config:
        arbitrary_types_allowed = True


class TranscriptionResult(AgentResult):
    """Output from Transcription Agent"""
    text: str = ""
    detected_language: str = "unknown"
    confidence: float = 0.0
    duration_seconds: float = 0.0
    was_filtered: bool = False  # True if hallucination was filtered
    filter_reason: Optional[str] = None

    @validator('confidence')
    def confidence_in_range(cls, v):
        return max(0.0, min(1.0, v))


# =============================================================================
# AGENT 2: DIARIZATION SCHEMAS
# =============================================================================

class SpeakerSegment(BaseModel):
    """A single speaker segment from diarization"""
    speaker: str = "SPEAKER_1"
    speaker_role: SpeakerRole = SpeakerRole.UNKNOWN
    text: str = ""
    detected_language: str = ""  # Language detected by transcription
    start_time: float = 0.0
    end_time: float = 0.0
    confidence: float = 0.0
    enrollment_match: bool = False
    enrolled_name: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class DiarizationResult(AgentResult):
    """Output from Diarization Agent"""
    segments: List[SpeakerSegment] = []
    total_speakers: int = 0
    total_duration: float = 0.0

    @property
    def provider_segments(self) -> List[SpeakerSegment]:
        return [s for s in self.segments if s.speaker_role == SpeakerRole.HEALTHCARE_PROVIDER]

    @property
    def patient_segments(self) -> List[SpeakerSegment]:
        return [s for s in self.segments if s.speaker_role == SpeakerRole.PATIENT_FAMILY]


# =============================================================================
# AGENT 3: TRANSLATION SCHEMAS
# =============================================================================

class TranslationResult(AgentResult):
    """Output from Translation Agent"""
    original_text: str = ""
    translated_text: str = ""
    source_language: str = "auto"
    target_language: str = ""


class TranslatedSegment(SpeakerSegment):
    """Speaker segment with translation added"""
    translation: str = ""
    translation_confidence: float = 0.0


class LanguageRoleResult(BaseModel):
    """Result of matching detected language to speaker role"""
    speaker_role: str  # "provider" | "family" | "unknown"
    translate_to: str  # target language code


# =============================================================================
# AGENT 4: TERMINOLOGY SCHEMAS
# =============================================================================

class MedicalTerm(BaseModel):
    """A medical term with plain language explanation"""
    term: str
    simple: str  # One-line simple explanation
    explanation: str  # Fuller explanation
    category: str = "general"
    source: TermSource = TermSource.UOFM_DICTIONARY
    confidence: float = 1.0


class TerminologyResult(AgentResult):
    """Output from Terminology Agent"""
    terms_found: List[MedicalTerm] = []
    terms_count: int = 0

    @validator('terms_count', always=True)
    def set_terms_count(cls, v, values):
        return len(values.get('terms_found', []))


# =============================================================================
# AGENT 5: SUMMARIZATION SCHEMAS
# =============================================================================

class Medication(BaseModel):
    """Medication details"""
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    instructions: Optional[str] = None


class Appointment(BaseModel):
    """Follow-up appointment"""
    type: str
    date: Optional[str] = None
    provider: Optional[str] = None
    location: Optional[str] = None


class JournalEntry(BaseModel):
    """The final structured journal entry"""
    # Metadata
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    visit_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Visit Information
    visit_type: str = "Medical Visit"
    provider_name: Optional[str] = None
    patient_name: Optional[str] = None

    # Chief Complaint & Symptoms
    chief_complaint: str = ""
    symptoms: List[str] = []

    # Clinical Details
    diagnoses: List[str] = []
    treatments: List[str] = []
    medications: List[Medication] = []
    vital_signs: Dict[str, str] = {}
    test_results: List[Dict[str, str]] = []

    # Follow-up
    follow_up_instructions: List[str] = []
    next_appointments: List[Appointment] = []
    action_items: List[str] = []

    # Family Section
    patient_questions: List[str] = []
    family_concerns: List[str] = []
    family_summary: str = ""

    # Medical Terms
    medical_terms: List[MedicalTerm] = []

    # Quality Metadata
    confidence_score: float = 0.5
    processing_notes: List[str] = []
    warnings: List[str] = []


class SummarizationResult(AgentResult):
    """Output from Summarization Agent"""
    journal_entry: Optional[JournalEntry] = None
    confidence_score: float = 0.0
    extraction_notes: List[str] = []


# =============================================================================
# VALIDATION SCHEMAS
# =============================================================================

class ValidationResult(BaseModel):
    """Result of validating an agent's output"""
    status: ValidationStatus
    score: float = Field(ge=0.0, le=1.0)
    issues: List[str] = []
    warnings: List[str] = []
    suggestions: List[str] = []

    @property
    def passed(self) -> bool:
        return self.status == ValidationStatus.PASSED

    @property
    def needs_correction(self) -> bool:
        return self.status == ValidationStatus.FAILED


class CorrectionRecord(BaseModel):
    """Record of a self-correction"""
    stage: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    original_score: float
    corrected_score: float
    issues_addressed: List[str]
    correction_method: str


# =============================================================================
# PIPELINE STATE - Full state management
# =============================================================================

class StageMetrics(BaseModel):
    """Metrics for a single pipeline stage"""
    stage: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    retry_count: int = 0
    quality_score: Optional[float] = None
    validation: Optional[ValidationResult] = None


class PipelineState(BaseModel):
    """
    Complete pipeline state tracking.

    State Management Principles:
    - Agents are STATELESS (pure functions)
    - Pipeline is STATEFUL (tracks everything)
    - State enables: debugging, resumption, auditing
    """
    # Identity
    session_id: str = Field(default_factory=lambda: f"session-{uuid.uuid4()}")
    family_id: str = ""
    user_id: str = ""
    patient_name: str = "Patient"
    target_language: str = "vi"

    # Configuration
    provider_spoken: str = "en"
    provider_translate_to: str = "vi"
    family_spoken: str = "vi"
    family_translate_to: str = "en"

    # Current Status
    current_stage: PipelineStage = PipelineStage.INITIALIZED
    is_complete: bool = False
    is_failed: bool = False

    # Agent Results (populated as pipeline progresses)
    transcription: Optional[TranscriptionResult] = None
    diarization: Optional[DiarizationResult] = None
    translated_segments: List[TranslatedSegment] = []
    terminology: Optional[TerminologyResult] = None
    summarization: Optional[SummarizationResult] = None

    # Metrics & Tracking
    stage_metrics: Dict[str, StageMetrics] = {}
    errors: List[str] = []
    warnings: List[str] = []
    corrections: List[CorrectionRecord] = []

    # Timing
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    total_duration_ms: Optional[float] = None

    # Methods for state management
    def start_stage(self, stage: str):
        """Record stage start"""
        self.current_stage = PipelineStage(stage)
        self.stage_metrics[stage] = StageMetrics(
            stage=stage,
            started_at=datetime.now().isoformat()
        )

    def complete_stage(self, stage: str, quality_score: Optional[float] = None):
        """Record stage completion"""
        if stage in self.stage_metrics:
            metrics = self.stage_metrics[stage]
            metrics.completed_at = datetime.now().isoformat()
            if metrics.started_at:
                start = datetime.fromisoformat(metrics.started_at)
                end = datetime.fromisoformat(metrics.completed_at)
                metrics.duration_ms = (end - start).total_seconds() * 1000
            if quality_score is not None:
                metrics.quality_score = quality_score

    def record_retry(self, stage: str):
        """Record a retry attempt"""
        if stage in self.stage_metrics:
            self.stage_metrics[stage].retry_count += 1

    def record_validation(self, stage: str, validation: ValidationResult):
        """Record validation result"""
        if stage in self.stage_metrics:
            self.stage_metrics[stage].validation = validation
            self.stage_metrics[stage].quality_score = validation.score

    def add_error(self, stage: str, error: str):
        """Add an error"""
        self.errors.append(f"[{stage}] {error}")

    def add_warning(self, stage: str, warning: str):
        """Add a warning"""
        self.warnings.append(f"[{stage}] {warning}")

    def add_correction(self, correction: CorrectionRecord):
        """Record a self-correction"""
        self.corrections.append(correction)

    def finalize(self, success: bool):
        """Finalize the pipeline state"""
        self.is_complete = True
        self.is_failed = not success
        self.completed_at = datetime.now().isoformat()
        self.current_stage = PipelineStage.COMPLETED if success else PipelineStage.FAILED

        if self.started_at and self.completed_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.total_duration_ms = (end - start).total_seconds() * 1000

    def is_successful(self) -> bool:
        """Check if pipeline completed successfully"""
        return (
            self.is_complete and
            not self.is_failed and
            self.summarization is not None and
            self.summarization.success
        )

    def get_quality_summary(self) -> Dict[str, float]:
        """Get quality scores for all stages"""
        return {
            stage: metrics.quality_score
            for stage, metrics in self.stage_metrics.items()
            if metrics.quality_score is not None
        }


# =============================================================================
# API RESPONSE SCHEMAS
# =============================================================================

class InstantTranscribeResponse(BaseModel):
    """Response for real-time transcription during recording"""
    success: bool
    has_speech: bool = False
    text: str = ""
    translation: str = ""
    detected_language: str = "unknown"
    speaker_role: SpeakerRole = SpeakerRole.UNKNOWN
    speaker_name: str = ""  # Enrolled speaker name if identified
    enrollment_confidence: float = 0.0  # Voice match confidence
    confidence: float = 0.0
    error: Optional[str] = None


class FinalizeSessionResponse(BaseModel):
    """Response for session finalization"""
    success: bool
    session_id: str
    journal_entry: Optional[JournalEntry] = None
    segments_processed: int = 0
    terms_detected: int = 0
    confidence_score: float = 0.0
    quality_scores: Dict[str, float] = {}
    corrections_made: int = 0
    warnings: List[str] = []
    errors: List[str] = []
    processing_time_ms: float = 0.0


# =============================================================================
# COST TRACKING SCHEMAS
# =============================================================================

class CostProvider(str, Enum):
    """API providers for cost tracking"""
    OPENAI = "openai"
    ASSEMBLYAI = "assemblyai"
    GOOGLE = "google"


class CostOperation(str, Enum):
    """Types of API operations"""
    WHISPER = "whisper"
    GPT4_INPUT = "gpt4_input"
    GPT4_OUTPUT = "gpt4_output"
    DIARIZATION = "diarization"
    TRANSLATION = "translation"


class CostRecord(BaseModel):
    """Record of a single API cost"""
    session_id: str
    provider: str  # CostProvider value
    operation: str  # CostOperation value
    quantity: float  # minutes or tokens
    unit: str  # "minutes", "tokens", "characters"
    cost_usd: float
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = {}


class SessionCostSummary(BaseModel):
    """Summary of costs for a session"""
    session_id: str
    total_cost_usd: float
    breakdown: Dict[str, float]  # operation -> cost
    provider_breakdown: Dict[str, float]  # provider -> cost
    budget_limit: Optional[float] = None
    budget_remaining: Optional[float] = None
    is_over_budget: bool = False


# =============================================================================
# GUARDRAILS SCHEMAS
# =============================================================================

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
    NAME = "name"


class PIIMatch(BaseModel):
    """A single PII match found in text"""
    pii_type: PIIType
    value: str
    start: int
    end: int
    confidence: float = 1.0


class PIIResult(BaseModel):
    """Result of PII detection on a single text"""
    has_pii: bool
    matches: List[PIIMatch] = []
    pii_types_found: List[PIIType] = []
    risk_level: str = "none"  # none, low, medium, high, critical


class PIIScanResult(BaseModel):
    """Result of scanning multiple segments"""
    total_segments: int
    segments_with_pii: int
    total_pii_found: int
    pii_by_type: Dict[str, int] = {}
    risk_level: str = "none"


class ContentRisk(str, Enum):
    """Types of content risks"""
    SELF_HARM = "self_harm"
    DANGEROUS_DOSAGE = "dangerous_dosage"
    EMERGENCY_INDICATOR = "emergency"
    NON_EVIDENCE_BASED = "non_evidence_based"
    INAPPROPRIATE_ADVICE = "inappropriate_advice"


class ContentFilterResult(BaseModel):
    """Result of content filtering"""
    is_safe: bool
    action: str = "allow"  # allow, warn, block, escalate
    risk_level: str = "none"  # none, low, medium, high, critical
    flags: List[Dict[str, Any]] = []
    recommendations: List[str] = []


class MedicationIssue(str, Enum):
    """Types of medication validation issues"""
    DOSAGE_TOO_HIGH = "dosage_too_high"
    DOSAGE_TOO_LOW = "dosage_too_low"
    INVALID_FREQUENCY = "invalid_frequency"
    POTENTIAL_INTERACTION = "potential_interaction"
    UNKNOWN_MEDICATION = "unknown_medication"


class MedicationValidationResult(BaseModel):
    """Result of medication validation"""
    is_valid: bool
    issues: List[Dict[str, Any]] = []
    medications_checked: int = 0
    warnings_count: int = 0
    errors_count: int = 0


# =============================================================================
# EVALUATION SCHEMAS
# =============================================================================

class EvalMetric(str, Enum):
    """Types of evaluation metrics"""
    TRANSCRIPTION_ACCURACY = "transcription_accuracy"
    KEYWORD_RECALL = "keyword_recall"
    TRANSLATION_QUALITY = "translation_quality"
    TERM_DETECTION_RECALL = "term_detection_recall"
    MEDICATION_ACCURACY = "medication_accuracy"
    SUMMARIZATION_COMPLETENESS = "summarization_completeness"


class EvalResult(BaseModel):
    """Result of evaluating a single aspect"""
    test_name: str
    metric: EvalMetric
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    expected: Any = None
    actual: Any = None
    errors: List[str] = []
    details: Dict[str, Any] = {}


class EvalReport(BaseModel):
    """Complete evaluation report for a test run"""
    test_name: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    passed: bool = False
    overall_score: float = Field(ge=0.0, le=1.0, default=0.0)
    results: List[EvalResult] = []
    summary: str = ""
    duration_ms: float = 0.0
