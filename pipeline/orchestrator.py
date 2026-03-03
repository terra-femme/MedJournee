# pipeline/orchestrator.py
"""
MEDJOURNEE PIPELINE ORCHESTRATOR - Production Implementation

This orchestrator implements ALL production-grade patterns:

1. MULTI-AGENT ORCHESTRATION
   - 5 independent agents coordinated in sequence
   - Each agent is stateless and testable

2. QUALITY GATES
   - Validate output at each stage
   - Explicit thresholds for acceptance

3. RETRY LOGIC
   - Automatic retry on transient failures
   - Exponential backoff

4. SELF-CORRECTION
   - Agents can critique and fix their output
   - Uses validation feedback

5. STATE MANAGEMENT
   - Full state tracking for debugging
   - Quality scores, retry counts, corrections

6. GRACEFUL DEGRADATION
   - Continue with warnings when possible
   - Partial results instead of total failure

7. ERROR HANDLING
   - Catch tool errors
   - Prevent infinite loops
   - Validate outputs

8. STRUCTURED LOGGING
   - Correlation IDs for request tracing
   - Stage-aware logging with latency tracking

9. PARALLEL EXECUTION
   - Independent stages run concurrently
   - Translation and terminology detection in parallel
"""

import asyncio
import uuid
import time
from datetime import datetime
from typing import Optional, List, Callable, Any, Tuple

from models.schemas import (
    PipelineState,
    PipelineStage,
    TranscriptionResult,
    DiarizationResult,
    TranslatedSegment,
    TerminologyResult,
    SummarizationResult,
    ValidationResult,
    ValidationStatus,
    CorrectionRecord,
    InstantTranscribeResponse,
    FinalizeSessionResponse,
    SpeakerRole,
    LanguageRoleResult,
)

from agents.transcription_agent import TranscriptionAgent
from agents.diarization_agent import DiarizationAgent
from agents.translation_agent import TranslationAgent
from agents.terminology_agent import TerminologyAgent
from agents.summarization_agent import SummarizationAgent

from validators.quality_gates import QualityGateValidator

# Import structured logging
try:
    from utils.logging import get_pipeline_logger, PipelineLogger
    STRUCTURED_LOGGING_AVAILABLE = True
except ImportError:
    STRUCTURED_LOGGING_AVAILABLE = False

# Import guardrails
try:
    from guardrails import (
        get_guardrail_registry,
        GuardrailRegistry,
        GuardrailContext,
        GuardrailExecutionResult,
        get_audio_deletion_enforcer,
        register_audio,
        verify_audio_deleted,
    )
    GUARDRAILS_AVAILABLE = True
except ImportError:
    GUARDRAILS_AVAILABLE = False

# Import cost tracking
try:
    from services.cost_tracking_service import get_cost_tracker, CostTracker
    COST_TRACKING_AVAILABLE = True
except ImportError:
    COST_TRACKING_AVAILABLE = False

# Import telemetry
try:
    from telemetry.metrics import get_metrics_collector, MetricsCollector
    from telemetry.tracing import get_tracer, Tracer
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False

# Import timeout utilities
try:
    from tools.base import TimeoutConfig, with_timeout, TimeoutError as ToolTimeoutError
    TIMEOUT_UTILS_AVAILABLE = True
except ImportError:
    TIMEOUT_UTILS_AVAILABLE = False


# =============================================================================
# RETRY CONFIGURATION
# =============================================================================

class RetryConfig:
    """Configuration for retry logic"""
    MAX_RETRIES = 3
    INITIAL_DELAY_SECONDS = 1.0
    EXPONENTIAL_BACKOFF = True
    MAX_DELAY_SECONDS = 10.0


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

class MedJourneePipeline:
    """
    Production-grade pipeline orchestrator.

    Implements all production patterns:
    - Multi-agent orchestration
    - Quality gates
    - Retry logic
    - Self-correction
    - State management
    - Graceful degradation
    - Structured logging with correlation IDs
    - Parallel execution for independent stages

    Usage:
        pipeline = MedJourneePipeline()
        state = await pipeline.process(audio_file, family_id="fam-001")

        if state.is_successful():
            journal = state.summarization.journal_entry
            print(journal.family_summary)

    Test Mode:
        pipeline = MedJourneePipeline(test_mode=True)
        state = await pipeline.process(audio_file, family_id="test")
        print(pipeline.test_metrics)  # Detailed stage metrics for testing
    """

    def __init__(
        self,
        enable_guardrails: bool = True,
        enable_cost_tracking: bool = True,
        test_mode: bool = False
    ):
        """
        Initialize all agents, validators, and production components.

        Args:
            enable_guardrails: Enable HIPAA guardrails (default: True)
            enable_cost_tracking: Enable API cost tracking (default: True)
            test_mode: Enable detailed metrics collection for testing (default: False)
        """
        # Test mode for detailed metrics collection
        self.test_mode = test_mode
        self.test_metrics: dict = {}  # Stores detailed metrics when test_mode=True

        # Agents (stateless) - enable test mode on transcription agent if pipeline is in test mode
        self.transcription_agent = TranscriptionAgent(test_mode=test_mode)
        self.diarization_agent = DiarizationAgent()
        self.translation_agent = TranslationAgent()
        self.terminology_agent = TerminologyAgent()
        self.summarization_agent = SummarizationAgent()

        # Validator (quality gates)
        self.validator = QualityGateValidator()

        # Guardrails (HIPAA compliance + MedJournee-specific)
        self.enable_guardrails = enable_guardrails and GUARDRAILS_AVAILABLE
        if self.enable_guardrails:
            self.guardrail_registry = get_guardrail_registry()
            self.audio_deletion_enforcer = get_audio_deletion_enforcer()
        else:
            self.guardrail_registry = None
            self.audio_deletion_enforcer = None

        # Cost tracking
        self.enable_cost_tracking = enable_cost_tracking and COST_TRACKING_AVAILABLE
        if self.enable_cost_tracking:
            self.cost_tracker = get_cost_tracker()
        else:
            self.cost_tracker = None

        # Telemetry
        if TELEMETRY_AVAILABLE:
            self.metrics = get_metrics_collector()
            self.tracer = get_tracer()
        else:
            self.metrics = None
            self.tracer = None

    def get_test_metrics(self) -> dict:
        """Get collected test metrics (only available when test_mode=True)"""
        return self.test_metrics

    def clear_test_metrics(self):
        """Clear test metrics for new test run"""
        self.test_metrics = {}
        if hasattr(self.transcription_agent, 'clear_test_log'):
            self.transcription_agent.clear_test_log()

    def _get_logger(self, session_id: str, family_id: Optional[str] = None) -> Optional["PipelineLogger"]:
        """Get structured logger for session."""
        if STRUCTURED_LOGGING_AVAILABLE:
            return get_pipeline_logger(session_id, family_id)
        return None

    def _log(self, logger: Optional["PipelineLogger"], level: str, message: str, **kwargs):
        """Log message if logger available, otherwise print."""
        if logger:
            getattr(logger, level)(message, **kwargs)
        else:
            context = ", ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
            print(f"[Pipeline] {message}" + (f" ({context})" if context else ""))

    async def process(
        self,
        audio_file,
        family_id: str,
        target_language: str = "vi",
        patient_name: str = "Patient",
        session_id: Optional[str] = None,
        provider_spoken: str = "en",
        provider_translate_to: str = "vi",
        family_spoken: str = "vi",
        family_translate_to: str = "en",
    ) -> PipelineState:
        """
        Process audio through the full pipeline.

        Pipeline stages:
        1. Diarization (speaker separation + transcription)
        2. Translation + Terminology (PARALLEL - these are independent!)
        3. Summarization (journal generation)
        4. Self-correction (if quality is low)
        """
        # Initialize state
        state = PipelineState(
            session_id=session_id or f"session-{uuid.uuid4()}",
            family_id=family_id,
            patient_name=patient_name,
            target_language=target_language,
            provider_spoken=provider_spoken,
            provider_translate_to=provider_translate_to,
            family_spoken=family_spoken,
            family_translate_to=family_translate_to,
        )

        # Initialize logger with correlation ID
        logger = self._get_logger(state.session_id, family_id)

        self._log(logger, "info", f"Starting session {state.session_id}",
                  session_id=state.session_id, family_id=family_id, patient=patient_name)

        try:
            # =================================================================
            # PRE-PIPELINE GUARDRAILS (Rate limit + Budget check)
            # =================================================================
            if self.enable_guardrails and self.guardrail_registry:
                guardrail_context = GuardrailContext(
                    session_id=state.session_id,
                    family_id=family_id,
                    user_id=family_id,  # Use family_id as user for rate limiting
                    stage="pre_pipeline"
                )
                pre_result = await self.guardrail_registry.run_for_stage("pre_pipeline", guardrail_context)

                if not pre_result.passed:
                    state.add_error("pre_pipeline", f"Guardrail blocked: {pre_result.block_reason}")
                    state.finalize(success=False)
                    self._log(logger, "warning", f"Pre-pipeline guardrail blocked: {pre_result.blocked_by}")
                    return state

                if pre_result.warnings:
                    for warning in pre_result.warnings:
                        state.add_warning("guardrails", warning)

                # Register audio file for deletion tracking
                if self.audio_deletion_enforcer and hasattr(audio_file, 'filename'):
                    audio_path = getattr(audio_file, 'file', getattr(audio_file, 'filename', None))
                    if audio_path:
                        await register_audio(state.session_id, str(audio_path))

            # =================================================================
            # STAGE 1: DIARIZATION
            # =================================================================
            state.start_stage(PipelineStage.DIARIZATION.value)
            if logger:
                logger.stage_start("diarization")
            else:
                print(f"[Pipeline] Stage 1: Diarization")

            diarization_start = time.time()
            state.diarization = await self._execute_with_retry(
                func=lambda: self.diarization_agent.diarize(audio_file, family_id),
                stage="diarization",
                state=state,
                logger=logger
            )
            diarization_duration = (time.time() - diarization_start) * 1000

            # Quality gate
            diarization_validation = self.validator.validate_diarization(state.diarization)
            state.record_validation(PipelineStage.DIARIZATION.value, diarization_validation)
            state.complete_stage(PipelineStage.DIARIZATION.value, diarization_validation.score)

            if logger:
                logger.quality_gate("diarization", diarization_validation.status.value,
                                   diarization_validation.score, diarization_validation.issues)
                logger.stage_complete("diarization", diarization_validation.score, diarization_duration,
                                     segments=len(state.diarization.segments) if state.diarization else 0)
            else:
                print(f"[Pipeline] Diarization: {len(state.diarization.segments) if state.diarization else 0} segments, quality={diarization_validation.score:.2f}")

            if diarization_validation.status == ValidationStatus.FAILED:
                state.add_error("diarization", f"Quality gate failed: {diarization_validation.issues}")
                state.finalize(success=False)
                return state

            if not state.diarization or not state.diarization.segments:
                state.add_error("diarization", "No speech segments detected")
                state.finalize(success=False)
                return state

            # =================================================================
            # STAGE 2 & 3: TRANSLATION + TERMINOLOGY (PARALLEL)
            # =================================================================
            # These stages are independent - run them concurrently!
            self._log(logger, "info", "Starting parallel execution: Translation + Terminology")

            state.start_stage(PipelineStage.TRANSLATION.value)
            parallel_start = time.time()

            # Prepare text for terminology detection
            all_text = " ".join([s.text for s in state.diarization.segments])

            # Run translation and terminology in parallel
            translation_task = self._execute_with_retry(
                func=lambda: self.translation_agent.translate_segments(
                    state.diarization.segments,
                    provider_spoken,
                    provider_translate_to,
                    family_spoken,
                    family_translate_to
                ),
                stage="translation",
                state=state,
                logger=logger
            )

            terminology_task = self.terminology_agent.detect_and_explain(all_text)

            # Wait for both to complete
            state.translated_segments, state.terminology = await asyncio.gather(
                translation_task,
                terminology_task
            )

            parallel_duration = (time.time() - parallel_start) * 1000

            # Start terminology stage tracking (retroactively)
            state.start_stage(PipelineStage.TERMINOLOGY.value)
            state.complete_stage(PipelineStage.TERMINOLOGY.value, 1.0)

            # Handle translation failure - use original segments without translation
            if not state.translated_segments:
                state.add_warning("translation", "Translation failed, using original segments")
                state.translated_segments = [
                    TranslatedSegment(
                        speaker=s.speaker,
                        speaker_role=s.speaker_role,
                        text=s.text,
                        detected_language=getattr(s, 'detected_language', ''),
                        start_time=s.start_time,
                        end_time=s.end_time,
                        confidence=s.confidence,
                        translation=""
                    )
                    for s in state.diarization.segments
                ]

            # Quality gate for translation
            translation_validation = self.validator.validate_translation(
                state.diarization.segments,
                state.translated_segments
            )
            state.record_validation(PipelineStage.TRANSLATION.value, translation_validation)
            state.complete_stage(PipelineStage.TRANSLATION.value, translation_validation.score)

            if logger:
                logger.quality_gate("translation", translation_validation.status.value,
                                   translation_validation.score, translation_validation.issues)
                logger.stage_complete("translation+terminology", translation_validation.score, parallel_duration,
                                     segments=len(state.translated_segments),
                                     terms=state.terminology.terms_count if state.terminology else 0)
            else:
                print(f"[Pipeline] Parallel complete: {len(state.translated_segments)} translated segments, {state.terminology.terms_count if state.terminology else 0} terms")

            if translation_validation.status == ValidationStatus.FAILED:
                state.add_warning("translation", f"Quality gate warning: {translation_validation.issues}")
                # Continue with warnings - graceful degradation

            # =================================================================
            # STAGE 4: SUMMARIZATION
            # =================================================================
            state.start_stage(PipelineStage.SUMMARIZATION.value)
            if logger:
                logger.stage_start("summarization")
            else:
                print(f"[Pipeline] Stage 4: Summarization")

            summarization_start = time.time()
            state.summarization = await self._execute_with_retry(
                func=lambda: self.summarization_agent.summarize(
                    state.translated_segments,
                    patient_name,
                    state.terminology.terms_found if state.terminology else None
                ),
                stage="summarization",
                state=state,
                logger=logger
            )
            summarization_duration = (time.time() - summarization_start) * 1000

            # Quality gate
            summarization_validation = self.validator.validate_summarization(state.summarization)
            state.record_validation(PipelineStage.SUMMARIZATION.value, summarization_validation)
            state.complete_stage(PipelineStage.SUMMARIZATION.value, summarization_validation.score)

            if logger:
                logger.quality_gate("summarization", summarization_validation.status.value,
                                   summarization_validation.score, summarization_validation.issues)
                logger.stage_complete("summarization", summarization_validation.score, summarization_duration)
            else:
                print(f"[Pipeline] Summarization: quality={summarization_validation.score:.2f}")

            # =================================================================
            # GUARDRAILS CHECK (before self-correction)
            # =================================================================
            if self.enable_guardrails and self.guardrail_registry and state.summarization and state.summarization.journal_entry:
                guardrails_start = time.time()

                # Run summarization stage guardrails (Medical Advice Filter + PII Scrubber)
                guardrail_context = GuardrailContext(
                    session_id=state.session_id,
                    family_id=family_id,
                    stage="summarization",
                    text=state.summarization.journal_entry.family_summary
                )

                summary_guardrail_result = await self.guardrail_registry.run_for_stage(
                    "summarization", guardrail_context
                )

                # Apply any modifications (e.g., PII redaction, disclaimers)
                if summary_guardrail_result.modifications:
                    for mod in summary_guardrail_result.modifications:
                        if isinstance(mod.get("content"), str):
                            state.summarization.journal_entry.family_summary = mod["content"]

                # Record warnings
                for warning in summary_guardrail_result.warnings:
                    state.add_warning("guardrails", warning)

                # Handle blocks (shouldn't happen at summary stage, but be safe)
                if not summary_guardrail_result.passed:
                    state.add_warning("guardrails", f"Content blocked by {summary_guardrail_result.blocked_by}")

                guardrails_duration = (time.time() - guardrails_start) * 1000
                self._log(logger, "info", f"Guardrails check: {guardrails_duration:.0f}ms",
                          passed=summary_guardrail_result.passed,
                          warnings=len(summary_guardrail_result.warnings))

            # =================================================================
            # STAGE 5: SELF-CORRECTION (if quality is low)
            # =================================================================
            if summarization_validation.status == ValidationStatus.FAILED:
                state.start_stage(PipelineStage.SELF_CORRECTION.value)
                if logger:
                    logger.stage_start("self_correction")
                else:
                    print(f"[Pipeline] Stage 5: Self-correction")

                original_score = summarization_validation.score
                correction_start = time.time()

                # Ask agent to self-correct
                corrected = await self.summarization_agent.self_correct(
                    original_result=state.summarization,
                    segments=state.translated_segments,
                    issues=summarization_validation.issues
                )

                correction_duration = (time.time() - correction_start) * 1000

                # Re-validate
                corrected_validation = self.validator.validate_summarization(corrected)

                # Keep correction if it improved
                improved = corrected_validation.score > original_score
                if improved:
                    state.summarization = corrected
                    state.add_correction(CorrectionRecord(
                        stage="summarization",
                        original_score=original_score,
                        corrected_score=corrected_validation.score,
                        issues_addressed=summarization_validation.issues,
                        correction_method="self_correction"
                    ))
                    state.record_validation(PipelineStage.SELF_CORRECTION.value, corrected_validation)

                if logger:
                    logger.self_correction("summarization", original_score,
                                          corrected_validation.score, improved)
                    logger.stage_complete("self_correction", corrected_validation.score, correction_duration)
                else:
                    if improved:
                        print(f"[Pipeline] Self-correction: improved from {original_score:.2f} to {corrected_validation.score:.2f}")
                    else:
                        print(f"[Pipeline] Self-correction: no improvement")

                state.complete_stage(PipelineStage.SELF_CORRECTION.value, corrected_validation.score)

            # =================================================================
            # POST-PIPELINE GUARDRAILS (Audio deletion enforcement)
            # =================================================================
            if self.enable_guardrails and self.guardrail_registry:
                post_context = GuardrailContext(
                    session_id=state.session_id,
                    family_id=family_id,
                    stage="post_pipeline"
                )
                post_result = await self.guardrail_registry.run_for_stage("post_pipeline", post_context)

                for warning in post_result.warnings:
                    state.add_warning("guardrails", warning)

                if not post_result.passed:
                    self._log(logger, "warning", f"Post-pipeline guardrail issue: {post_result.block_reason}")

            # =================================================================
            # COMPLETE
            # =================================================================
            state.finalize(success=True)

            quality_summary = state.get_quality_summary()

            # Collect test metrics if in test mode
            if self.test_mode:
                self.test_metrics = {
                    "session_id": state.session_id,
                    "success": True,
                    "total_duration_ms": state.total_duration_ms,
                    "quality_scores": quality_summary,
                    "stage_metrics": {
                        name: {
                            "duration_ms": m.duration_ms,
                            "quality_score": m.quality_score,
                            "retry_count": m.retry_count,
                        }
                        for name, m in state.stage_metrics.items()
                    },
                    "transcription_log": self.transcription_agent.get_test_log() if hasattr(self.transcription_agent, 'get_test_log') else [],
                    "corrections": len(state.corrections),
                    "warnings": state.warnings,
                    "errors": state.errors,
                }

            # Record telemetry
            if self.metrics:
                self.metrics.record_pipeline_run("success", state.total_duration_ms or 0)
                for stage_name, score in quality_summary.items():
                    metrics = state.stage_metrics.get(stage_name)
                    if metrics:
                        self.metrics.record_stage_completion(
                            stage_name,
                            metrics.duration_ms or 0,
                            score
                        )

            if logger:
                logger.pipeline_complete(
                    success=True,
                    total_duration_ms=state.total_duration_ms or 0,
                    quality_scores=quality_summary,
                    corrections_count=len(state.corrections)
                )
            else:
                print(f"[Pipeline] Completed. Quality scores: {quality_summary}")
                print(f"[Pipeline] Total time: {state.total_duration_ms:.0f}ms")
                if state.corrections:
                    print(f"[Pipeline] Corrections made: {len(state.corrections)}")

            return state

        except Exception as e:
            import traceback
            state.add_error(state.current_stage.value, str(e))
            state.finalize(success=False)

            # Record failure telemetry
            if self.metrics:
                self.metrics.record_pipeline_run("failed", state.total_duration_ms or 0)
                self.metrics.record_error("pipeline_error", state.current_stage.value)

            if logger:
                logger.error(f"Pipeline failed: {e}",
                            stage=state.current_stage.value,
                            error=str(e))
            else:
                print(f"[Pipeline] Failed: {e}")
                print(traceback.format_exc())

            # Still enforce audio deletion even on failure
            if self.enable_guardrails and self.guardrail_registry:
                try:
                    post_context = GuardrailContext(
                        session_id=state.session_id,
                        family_id=family_id,
                        stage="post_pipeline"
                    )
                    await self.guardrail_registry.run_for_stage("post_pipeline", post_context)
                except Exception:
                    pass  # Best effort cleanup

            return state

    async def _execute_with_retry(
        self,
        func: Callable,
        stage: str,
        state: PipelineState,
        max_retries: int = RetryConfig.MAX_RETRIES,
        logger: Optional["PipelineLogger"] = None
    ) -> Any:
        """
        Execute function with automatic retry on failure.

        Implements:
        - Exponential backoff
        - Retry counting
        - Structured logging
        """
        last_error = None
        delay = RetryConfig.INITIAL_DELAY_SECONDS

        for attempt in range(max_retries):
            try:
                result = await func()

                # Check if result indicates failure
                if hasattr(result, 'success') and not result.success:
                    error_msg = getattr(result, 'error', 'Unknown error')
                    raise Exception(error_msg)

                return result

            except Exception as e:
                last_error = e
                state.record_retry(stage)

                if attempt < max_retries - 1:
                    if logger:
                        logger.retry(stage, attempt + 1, max_retries, str(e))
                    else:
                        print(f"[Retry] {stage} attempt {attempt + 1} failed: {e}")
                        print(f"[Retry] Waiting {delay:.1f}s before retry...")

                    await asyncio.sleep(delay)

                    # Exponential backoff
                    if RetryConfig.EXPONENTIAL_BACKOFF:
                        delay = min(delay * 2, RetryConfig.MAX_DELAY_SECONDS)
                else:
                    if logger:
                        logger.stage_failed(stage, str(e), retry_count=max_retries)
                    else:
                        print(f"[Retry] {stage} failed after {max_retries} attempts: {e}")

        # All retries exhausted - return failure result
        state.add_error(stage, f"Failed after {max_retries} retries: {last_error}")

        # Return appropriate failure result based on stage
        if stage == "diarization":
            return DiarizationResult(success=False, error=str(last_error))
        elif stage == "summarization":
            return SummarizationResult(success=False, error=str(last_error))
        elif stage == "translation":
            return []  # Return empty list for translation failures
        else:
            return None

    async def instant_transcribe(
        self,
        audio_file,
        provider_spoken: str = "en",
        provider_translate_to: str = "vi",
        family_spoken: str = "vi",
        family_translate_to: str = "en",
        family_id: str = ""
    ) -> InstantTranscribeResponse:
        """
        Fast transcription + translation for real-time display.

        Use this during recording for instant feedback.
        Does NOT do diarization or summarization.
        If family_id provided, attempts speaker identification.
        """
        try:
            # Save audio position for potential voice identification
            await audio_file.seek(0)

            # Quick transcription
            transcription = await self.transcription_agent.transcribe(audio_file)

            if not transcription.success or not transcription.text:
                return InstantTranscribeResponse(
                    success=True,
                    has_speech=False,
                    detected_language=transcription.detected_language
                )

            # Determine translation target based on detected language only
            # (we never assume role from language — multiple people may be in the room)
            detected = transcription.detected_language.lower() if transcription.detected_language else "unknown"

            if detected.startswith(family_spoken[:2]):
                target = family_translate_to
            else:
                target = provider_translate_to

            # All unidentified speakers are UNKNOWN until enrollment matching names them
            speaker_role = SpeakerRole.UNKNOWN

            # Try to identify enrolled speaker if family_id provided
            speaker_name = ""
            enrollment_confidence = 0.0
            if family_id:
                try:
                    from services.voice_enrollment_service import voice_enrollment_service
                    await audio_file.seek(0)
                    matched_name, confidence = await voice_enrollment_service.identify_enrolled_speaker(
                        audio_file, family_id
                    )
                    if matched_name and confidence >= 0.60:
                        speaker_name = matched_name
                        enrollment_confidence = confidence
                        speaker_role = SpeakerRole.PATIENT_FAMILY
                        print(f"[InstantTranscribe] Matched enrolled speaker: {matched_name} ({confidence:.2f})")
                except Exception as e:
                    print(f"Speaker identification error (non-fatal): {e}")

            # Quick translation
            translation = await self.translation_agent.translate(
                transcription.text,
                target,
                detected
            )

            return InstantTranscribeResponse(
                success=True,
                has_speech=True,
                text=transcription.text,
                translation=translation.translated_text if translation.success else "",
                detected_language=transcription.detected_language,
                speaker_role=speaker_role,
                speaker_name=speaker_name,
                enrollment_confidence=enrollment_confidence,
                confidence=transcription.confidence
            )

        except Exception as e:
            return InstantTranscribeResponse(
                success=False,
                has_speech=False,
                error=str(e)
            )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_pipeline: Optional[MedJourneePipeline] = None


def get_pipeline() -> MedJourneePipeline:
    """Get or create the global pipeline instance"""
    global _pipeline
    if _pipeline is None:
        _pipeline = MedJourneePipeline()
    return _pipeline


async def process_audio(
    audio_file,
    family_id: str,
    **kwargs
) -> PipelineState:
    """Convenience function to process audio"""
    pipeline = get_pipeline()
    return await pipeline.process(audio_file, family_id, **kwargs)


async def instant_transcribe(
    audio_file,
    **kwargs
) -> InstantTranscribeResponse:
    """Convenience function for instant transcription"""
    pipeline = get_pipeline()
    return await pipeline.instant_transcribe(audio_file, **kwargs)
