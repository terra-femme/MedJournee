# telemetry/tracing.py
"""
DISTRIBUTED TRACING

OpenTelemetry-based tracing for the MedJournee pipeline.
Enables distributed tracing across:
- HTTP requests
- Pipeline stages
- External API calls
- Database operations

Traces can be exported to Jaeger, Zipkin, or other OpenTelemetry-compatible backends.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any, List
from contextlib import asynccontextmanager
from functools import wraps
import uuid
import time
import asyncio

# Try to import OpenTelemetry, fall back to stub if not available
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, SpanKind
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


# =============================================================================
# SPAN DATA STRUCTURE (for both OTel and fallback)
# =============================================================================

@dataclass
class SpanData:
    """Data structure representing a trace span."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    service_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "ok"  # ok, error
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def finish(self, status: str = "ok"):
        """Finish the span."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status

    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attributes or {}
        })

    def set_attribute(self, key: str, value: Any):
        """Set a span attribute."""
        self.attributes[key] = value


# =============================================================================
# FALLBACK TRACER (when OpenTelemetry is not available)
# =============================================================================

class FallbackSpan:
    """Simple span implementation when OTel is not available."""

    def __init__(self, operation_name: str, trace_id: str, parent_span_id: str = None):
        self.data = SpanData(
            trace_id=trace_id,
            span_id=str(uuid.uuid4())[:8],
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name="medjournee",
            start_time=time.time()
        )

    def set_attribute(self, key: str, value: Any):
        self.data.set_attribute(key, value)

    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        self.data.add_event(name, attributes)

    def set_status(self, status: str):
        self.data.status = status

    def end(self):
        self.data.finish()


class FallbackTracer:
    """Simple tracer implementation when OTel is not available."""

    def __init__(self, service_name: str = "medjournee"):
        self.service_name = service_name
        self._current_trace_id: Optional[str] = None
        self._current_span: Optional[FallbackSpan] = None
        self._spans: List[SpanData] = []

    def start_span(
        self,
        operation_name: str,
        parent_span: FallbackSpan = None
    ) -> FallbackSpan:
        """Start a new span."""
        trace_id = self._current_trace_id or str(uuid.uuid4())[:16]
        parent_id = parent_span.data.span_id if parent_span else None

        span = FallbackSpan(operation_name, trace_id, parent_id)
        span.data.service_name = self.service_name

        if self._current_trace_id is None:
            self._current_trace_id = trace_id

        return span

    def end_span(self, span: FallbackSpan, status: str = "ok"):
        """End a span and store it."""
        span.data.finish(status)
        self._spans.append(span.data)

    def get_recent_spans(self, limit: int = 100) -> List[SpanData]:
        """Get recent spans."""
        return self._spans[-limit:]

    def clear_context(self):
        """Clear the current trace context."""
        self._current_trace_id = None
        self._current_span = None


# =============================================================================
# MAIN TRACER CLASS
# =============================================================================

class Tracer:
    """
    Distributed tracing for the MedJournee pipeline.

    Supports OpenTelemetry when available, falls back to simple
    in-memory tracing when not.

    Usage:
        tracer = Tracer()

        # Manual span management
        span = tracer.start_span("transcription")
        try:
            result = await do_transcription()
            span.set_attribute("audio_duration", 60.0)
        except Exception as e:
            span.set_status("error")
            span.set_attribute("error.message", str(e))
        finally:
            tracer.end_span(span)

        # Or use context manager
        async with tracer.span("translation") as span:
            span.set_attribute("source_lang", "en")
            span.set_attribute("target_lang", "vi")
            result = await do_translation()
    """

    def __init__(
        self,
        service_name: str = "medjournee",
        enable_otel: bool = True
    ):
        """
        Initialize tracer.

        Args:
            service_name: Name of the service for spans
            enable_otel: Whether to use OpenTelemetry (if available)
        """
        self.service_name = service_name
        self.use_otel = enable_otel and OPENTELEMETRY_AVAILABLE
        self._fallback_tracer = FallbackTracer(service_name)

        if self.use_otel:
            self._setup_otel()

    def _setup_otel(self):
        """Setup OpenTelemetry tracer."""
        if not OPENTELEMETRY_AVAILABLE:
            return

        # Create resource with service info
        resource = Resource.create({
            "service.name": self.service_name,
            "service.version": "2.0.0",
        })

        # Set up tracer provider
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        self._otel_tracer = trace.get_tracer(self.service_name)

    def start_span(
        self,
        operation_name: str,
        attributes: Dict[str, Any] = None,
        parent_span: Any = None
    ) -> Any:
        """
        Start a new span.

        Args:
            operation_name: Name of the operation
            attributes: Initial attributes
            parent_span: Parent span (optional)

        Returns:
            Span object (OTel span or FallbackSpan)
        """
        if self.use_otel:
            span = self._otel_tracer.start_span(
                operation_name,
                kind=SpanKind.INTERNAL
            )
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            return span
        else:
            span = self._fallback_tracer.start_span(operation_name, parent_span)
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            return span

    def end_span(self, span: Any, status: str = "ok"):
        """
        End a span.

        Args:
            span: Span to end
            status: Final status (ok, error)
        """
        if self.use_otel:
            if status == "error":
                span.set_status(Status(StatusCode.ERROR))
            else:
                span.set_status(Status(StatusCode.OK))
            span.end()
        else:
            self._fallback_tracer.end_span(span, status)

    @asynccontextmanager
    async def span(
        self,
        operation_name: str,
        attributes: Dict[str, Any] = None
    ):
        """
        Context manager for spans.

        Usage:
            async with tracer.span("my_operation") as span:
                span.set_attribute("key", "value")
                await do_work()
        """
        span = self.start_span(operation_name, attributes)
        status = "ok"
        try:
            yield span
        except Exception as e:
            status = "error"
            if self.use_otel:
                span.record_exception(e)
            else:
                span.set_attribute("error.message", str(e))
                span.set_attribute("error.type", type(e).__name__)
            raise
        finally:
            self.end_span(span, status)

    def trace_function(self, operation_name: str = None):
        """
        Decorator to trace a function.

        Usage:
            @tracer.trace_function("my_operation")
            async def my_function():
                ...
        """
        def decorator(func):
            op_name = operation_name or func.__name__

            @wraps(func)
            async def wrapper(*args, **kwargs):
                async with self.span(op_name) as span:
                    span.set_attribute("function", func.__name__)
                    return await func(*args, **kwargs)

            return wrapper
        return decorator

    def get_recent_spans(self, limit: int = 100) -> List[SpanData]:
        """Get recent spans (fallback tracer only)."""
        if not self.use_otel:
            return self._fallback_tracer.get_recent_spans(limit)
        return []

    def inject_context(self, carrier: Dict[str, str]):
        """
        Inject trace context into a carrier (for distributed tracing).

        Args:
            carrier: Dictionary to inject context into (e.g., HTTP headers)
        """
        if self.use_otel:
            from opentelemetry.propagate import inject
            inject(carrier)
        else:
            if self._fallback_tracer._current_trace_id:
                carrier["X-Trace-ID"] = self._fallback_tracer._current_trace_id

    def extract_context(self, carrier: Dict[str, str]):
        """
        Extract trace context from a carrier.

        Args:
            carrier: Dictionary containing context (e.g., HTTP headers)
        """
        if self.use_otel:
            from opentelemetry.propagate import extract
            return extract(carrier)
        else:
            trace_id = carrier.get("X-Trace-ID")
            if trace_id:
                self._fallback_tracer._current_trace_id = trace_id


# =============================================================================
# GLOBAL INSTANCE AND CONVENIENCE FUNCTIONS
# =============================================================================

_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Get or create the global tracer."""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


def trace_operation(operation_name: str = None):
    """
    Decorator to trace an async operation.

    Usage:
        @trace_operation("transcription")
        async def transcribe(audio):
            ...
    """
    def decorator(func):
        op_name = operation_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            async with tracer.span(op_name) as span:
                span.set_attribute("function", func.__name__)
                return await func(*args, **kwargs)

        return wrapper
    return decorator
