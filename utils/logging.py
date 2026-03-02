# utils/logging.py
"""
STRUCTURED LOGGING - Production-grade logging with correlation IDs

Features:
- Correlation IDs for request tracing
- Structured JSON output for production
- Stage-aware logging for pipeline debugging
- Latency tracking
- Error context preservation

Usage:
    from utils.logging import get_logger, LogContext

    # Create logger with correlation ID
    logger = get_logger("pipeline", correlation_id="session-123")

    # Log with context
    logger.info("Processing started", stage="diarization", segments=5)

    # Use context manager for automatic timing
    with LogContext(logger, "diarization") as ctx:
        # ... do work ...
        ctx.add_metadata(segments=5)
"""

import logging
import json
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar
from functools import wraps

# Context variable for correlation ID (thread-safe)
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def set_correlation_id(correlation_id: str):
    """Set correlation ID for current context."""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get correlation ID from current context."""
    return _correlation_id.get()


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return f"corr-{uuid.uuid4().hex[:12]}"


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.123Z",
        "level": "INFO",
        "logger": "pipeline",
        "message": "Processing started",
        "correlation_id": "corr-abc123",
        "stage": "diarization",
        "latency_ms": 1234.5,
        ...
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID
        correlation_id = get_correlation_id()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class StructuredLogger:
    """
    Wrapper for standard logger with structured output.

    Supports:
    - Correlation ID propagation
    - Extra fields in log messages
    - Stage-aware logging
    """

    def __init__(
        self,
        name: str,
        correlation_id: Optional[str] = None,
        use_json: bool = False
    ):
        self.logger = logging.getLogger(name)
        self.correlation_id = correlation_id
        self.default_fields: Dict[str, Any] = {}

        if not self.logger.handlers:
            handler = logging.StreamHandler()

            if use_json:
                handler.setFormatter(StructuredFormatter())
            else:
                handler.setFormatter(logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                ))

            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _log(self, level: int, message: str, **kwargs):
        """Internal logging with extra fields."""
        # Set correlation ID for this context
        if self.correlation_id:
            set_correlation_id(self.correlation_id)

        # Create log record with extra fields
        extra = {"extra_fields": {**self.default_fields, **kwargs}}

        # Format message with inline context for console
        context_parts = []
        for key, value in kwargs.items():
            if value is not None:
                context_parts.append(f"{key}={value}")

        if context_parts:
            formatted_message = f"{message} ({', '.join(context_parts)})"
        else:
            formatted_message = message

        self.logger.log(level, formatted_message, extra=extra)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def set_default_field(self, key: str, value: Any):
        """Set a field that will be included in all log messages."""
        self.default_fields[key] = value

    def with_stage(self, stage: str) -> "StructuredLogger":
        """Create a logger with stage context."""
        new_logger = StructuredLogger(
            self.logger.name,
            self.correlation_id,
            use_json=False
        )
        new_logger.default_fields = {**self.default_fields, "stage": stage}
        return new_logger


class LogContext:
    """
    Context manager for timed, staged logging.

    Usage:
        with LogContext(logger, "diarization") as ctx:
            # ... do work ...
            ctx.add_metadata(segments=5)
        # Automatically logs completion with duration
    """

    def __init__(self, logger: StructuredLogger, stage: str):
        self.logger = logger
        self.stage = stage
        self.start_time: Optional[float] = None
        self.metadata: Dict[str, Any] = {}

    def __enter__(self) -> "LogContext":
        self.start_time = time.time()
        self.logger.info(f"Starting {self.stage}", stage=self.stage)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000 if self.start_time else 0

        if exc_type:
            self.logger.error(
                f"Failed {self.stage}: {exc_val}",
                stage=self.stage,
                duration_ms=round(duration_ms, 2),
                error=str(exc_val),
                **self.metadata
            )
        else:
            self.logger.info(
                f"Completed {self.stage}",
                stage=self.stage,
                duration_ms=round(duration_ms, 2),
                **self.metadata
            )

        return False  # Don't suppress exceptions

    def add_metadata(self, **kwargs):
        """Add metadata to be included in completion log."""
        self.metadata.update(kwargs)


class PipelineLogger(StructuredLogger):
    """
    Specialized logger for pipeline execution.

    Provides:
    - Session-aware logging
    - Stage transitions
    - Quality score tracking
    - Retry tracking
    """

    def __init__(
        self,
        session_id: str,
        family_id: Optional[str] = None,
        use_json: bool = False
    ):
        super().__init__("medjournee.pipeline", session_id, use_json)
        self.session_id = session_id
        self.family_id = family_id
        self.set_default_field("session_id", session_id)
        if family_id:
            self.set_default_field("family_id", family_id)

    def stage_start(self, stage: str, **kwargs):
        """Log stage start."""
        self.info(f"[{stage.upper()}] Starting", stage=stage, **kwargs)

    def stage_complete(
        self,
        stage: str,
        quality_score: Optional[float] = None,
        duration_ms: Optional[float] = None,
        **kwargs
    ):
        """Log stage completion."""
        self.info(
            f"[{stage.upper()}] Completed",
            stage=stage,
            quality_score=quality_score,
            duration_ms=round(duration_ms, 2) if duration_ms else None,
            **kwargs
        )

    def stage_failed(
        self,
        stage: str,
        error: str,
        retry_count: int = 0,
        **kwargs
    ):
        """Log stage failure."""
        self.error(
            f"[{stage.upper()}] Failed: {error}",
            stage=stage,
            error=error,
            retry_count=retry_count,
            **kwargs
        )

    def quality_gate(
        self,
        stage: str,
        status: str,
        score: float,
        issues: Optional[list] = None
    ):
        """Log quality gate result."""
        level = logging.WARNING if status == "warning" else (
            logging.ERROR if status == "failed" else logging.INFO
        )
        self._log(
            level,
            f"[{stage.upper()}] Quality gate: {status}",
            stage=stage,
            quality_status=status,
            quality_score=score,
            quality_issues=issues
        )

    def retry(self, stage: str, attempt: int, max_retries: int, error: str):
        """Log retry attempt."""
        self.warning(
            f"[{stage.upper()}] Retry {attempt}/{max_retries}",
            stage=stage,
            retry_attempt=attempt,
            max_retries=max_retries,
            error=error
        )

    def self_correction(
        self,
        stage: str,
        original_score: float,
        corrected_score: float,
        improved: bool
    ):
        """Log self-correction result."""
        if improved:
            self.info(
                f"[{stage.upper()}] Self-correction improved: {original_score:.2f} -> {corrected_score:.2f}",
                stage=stage,
                original_score=original_score,
                corrected_score=corrected_score,
                improvement=corrected_score - original_score
            )
        else:
            self.warning(
                f"[{stage.upper()}] Self-correction no improvement",
                stage=stage,
                original_score=original_score,
                corrected_score=corrected_score
            )

    def pipeline_complete(
        self,
        success: bool,
        total_duration_ms: float,
        quality_scores: Dict[str, float],
        corrections_count: int = 0
    ):
        """Log pipeline completion."""
        level = logging.INFO if success else logging.ERROR
        self._log(
            level,
            f"Pipeline {'completed successfully' if success else 'failed'}",
            success=success,
            total_duration_ms=round(total_duration_ms, 2),
            quality_scores=quality_scores,
            corrections_count=corrections_count
        )


# Factory functions
def get_logger(
    name: str,
    correlation_id: Optional[str] = None,
    use_json: bool = False
) -> StructuredLogger:
    """Get a structured logger."""
    return StructuredLogger(name, correlation_id, use_json)


def get_pipeline_logger(
    session_id: str,
    family_id: Optional[str] = None,
    use_json: bool = False
) -> PipelineLogger:
    """Get a pipeline-specific logger."""
    return PipelineLogger(session_id, family_id, use_json)
