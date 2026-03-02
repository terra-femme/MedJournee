# telemetry/metrics.py
"""
PROMETHEUS METRICS

Production metrics for monitoring the MedJournee pipeline:
- API call counts and latencies
- Pipeline stage durations
- Quality scores
- Cost tracking
- Circuit breaker states
- Active sessions

These metrics can be scraped by Prometheus and visualized in Grafana.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List, Any
from enum import Enum
import time
import asyncio

# Try to import prometheus_client, fall back to stub if not available
try:
    from prometheus_client import Counter, Histogram, Gauge, Summary, Info
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Stub classes for when prometheus_client is not installed
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, amount=1): pass

    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def observe(self, amount): pass

    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def set(self, value): pass
        def inc(self, amount=1): pass
        def dec(self, amount=1): pass

    class Summary:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def observe(self, amount): pass

    class Info:
        def __init__(self, *args, **kwargs): pass
        def info(self, value): pass

    def generate_latest(registry=None): return b""
    CONTENT_TYPE_LATEST = "text/plain"


# =============================================================================
# METRIC DEFINITIONS
# =============================================================================

# Counters
api_calls_total = Counter(
    'medjournee_api_calls_total',
    'Total API calls by provider, operation, and status',
    ['provider', 'operation', 'status']
)

pipeline_runs_total = Counter(
    'medjournee_pipeline_runs_total',
    'Total pipeline runs by status',
    ['status']
)

errors_total = Counter(
    'medjournee_errors_total',
    'Total errors by type and stage',
    ['error_type', 'stage']
)

retries_total = Counter(
    'medjournee_retries_total',
    'Total retry attempts by stage',
    ['stage']
)

pii_detections_total = Counter(
    'medjournee_pii_detections_total',
    'Total PII detections by type',
    ['pii_type']
)

# Histograms
request_latency = Histogram(
    'medjournee_request_latency_seconds',
    'Request latency by endpoint',
    ['endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

stage_latency = Histogram(
    'medjournee_stage_latency_seconds',
    'Pipeline stage latency',
    ['stage'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

api_latency = Histogram(
    'medjournee_api_latency_seconds',
    'External API call latency',
    ['provider', 'operation'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Gauges
circuit_breaker_state = Gauge(
    'medjournee_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['service']
)

active_sessions = Gauge(
    'medjournee_active_sessions',
    'Number of currently active sessions'
)

active_requests = Gauge(
    'medjournee_active_requests',
    'Number of currently processing requests'
)

# Summaries for quality scores
quality_score = Summary(
    'medjournee_quality_score',
    'Quality scores by stage',
    ['stage']
)

# Cost tracking
cost_total = Counter(
    'medjournee_cost_usd_total',
    'Total API cost in USD',
    ['provider', 'operation']
)

# Application info
app_info = Info(
    'medjournee_app',
    'Application information'
)


# =============================================================================
# METRICS COLLECTOR CLASS
# =============================================================================

@dataclass
class MetricRecord:
    """Record of a single metric event"""
    name: str
    value: float
    labels: Dict[str, str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class MetricsCollector:
    """
    Centralized metrics collection for the MedJournee pipeline.

    Usage:
        collector = MetricsCollector()

        # Record API call
        collector.record_api_call("openai", "whisper", "success", latency_ms=1500)

        # Record stage completion
        collector.record_stage_completion("transcription", latency_ms=2000, quality_score=0.95)

        # Get metrics for Prometheus
        metrics_output = collector.get_prometheus_metrics()
    """

    def __init__(self):
        """Initialize metrics collector."""
        self._lock = asyncio.Lock()
        self._recent_metrics: List[MetricRecord] = []
        self._max_recent = 1000  # Keep last 1000 metrics in memory

        # Set application info
        if PROMETHEUS_AVAILABLE:
            app_info.info({
                'version': '2.0.0',
                'name': 'medjournee',
                'architecture': 'multi-agent-pipeline'
            })

    def record_api_call(
        self,
        provider: str,
        operation: str,
        status: str,
        latency_ms: float = 0.0
    ):
        """
        Record an external API call.

        Args:
            provider: API provider (openai, assemblyai, google)
            operation: Operation type (whisper, gpt4, diarization, translation)
            status: Call status (success, error, timeout)
            latency_ms: Call latency in milliseconds
        """
        api_calls_total.labels(
            provider=provider,
            operation=operation,
            status=status
        ).inc()

        if latency_ms > 0:
            api_latency.labels(
                provider=provider,
                operation=operation
            ).observe(latency_ms / 1000)  # Convert to seconds

        self._add_recent(MetricRecord(
            name="api_call",
            value=latency_ms,
            labels={"provider": provider, "operation": operation, "status": status}
        ))

    def record_stage_completion(
        self,
        stage: str,
        latency_ms: float,
        quality_score_value: float = None
    ):
        """
        Record pipeline stage completion.

        Args:
            stage: Stage name (transcription, diarization, translation, summarization)
            latency_ms: Stage processing time in milliseconds
            quality_score_value: Quality score (0.0-1.0) if available
        """
        stage_latency.labels(stage=stage).observe(latency_ms / 1000)

        if quality_score_value is not None:
            quality_score.labels(stage=stage).observe(quality_score_value)

        self._add_recent(MetricRecord(
            name="stage_completion",
            value=latency_ms,
            labels={
                "stage": stage,
                "quality_score": str(quality_score_value) if quality_score_value else "n/a"
            }
        ))

    def record_pipeline_run(self, status: str, duration_ms: float = 0.0):
        """
        Record a complete pipeline run.

        Args:
            status: Pipeline status (success, failed, partial)
            duration_ms: Total pipeline duration in milliseconds
        """
        pipeline_runs_total.labels(status=status).inc()

        self._add_recent(MetricRecord(
            name="pipeline_run",
            value=duration_ms,
            labels={"status": status}
        ))

    def record_error(self, error_type: str, stage: str):
        """
        Record an error.

        Args:
            error_type: Type of error (timeout, api_error, validation_error)
            stage: Stage where error occurred
        """
        errors_total.labels(error_type=error_type, stage=stage).inc()

    def record_retry(self, stage: str):
        """Record a retry attempt."""
        retries_total.labels(stage=stage).inc()

    def record_cost(self, provider: str, operation: str, cost_usd: float):
        """
        Record API cost.

        Args:
            provider: API provider
            operation: Operation type
            cost_usd: Cost in USD
        """
        # Use a multiplier to track fractional cents
        cost_total.labels(
            provider=provider,
            operation=operation
        ).inc(cost_usd)

        self._add_recent(MetricRecord(
            name="cost",
            value=cost_usd,
            labels={"provider": provider, "operation": operation}
        ))

    def record_pii_detection(self, pii_type: str, count: int = 1):
        """
        Record PII detection.

        Args:
            pii_type: Type of PII detected
            count: Number of instances detected
        """
        pii_detections_total.labels(pii_type=pii_type).inc(count)

    def record_request_latency(self, endpoint: str, latency_ms: float):
        """
        Record HTTP request latency.

        Args:
            endpoint: API endpoint path
            latency_ms: Request latency in milliseconds
        """
        request_latency.labels(endpoint=endpoint).observe(latency_ms / 1000)

    def set_circuit_breaker_state(self, service: str, state: str):
        """
        Set circuit breaker state.

        Args:
            service: Service name
            state: State (closed, open, half_open)
        """
        state_map = {"closed": 0, "open": 1, "half_open": 2}
        circuit_breaker_state.labels(service=service).set(state_map.get(state, 0))

    def set_active_sessions(self, count: int):
        """Set current active session count."""
        active_sessions.set(count)

    def increment_active_sessions(self):
        """Increment active session count."""
        active_sessions.inc()

    def decrement_active_sessions(self):
        """Decrement active session count."""
        active_sessions.dec()

    def increment_active_requests(self):
        """Increment active request count."""
        active_requests.inc()

    def decrement_active_requests(self):
        """Decrement active request count."""
        active_requests.dec()

    def get_prometheus_metrics(self) -> bytes:
        """
        Get metrics in Prometheus exposition format.

        Returns:
            Metrics as bytes for HTTP response
        """
        if PROMETHEUS_AVAILABLE:
            return generate_latest()
        return b"# Prometheus client not installed\n"

    def get_content_type(self) -> str:
        """Get content type for Prometheus metrics endpoint."""
        return CONTENT_TYPE_LATEST if PROMETHEUS_AVAILABLE else "text/plain"

    def get_recent_metrics(self, limit: int = 100) -> List[MetricRecord]:
        """Get recent metrics for debugging."""
        return self._recent_metrics[-limit:]

    def _add_recent(self, record: MetricRecord):
        """Add to recent metrics buffer."""
        self._recent_metrics.append(record)
        if len(self._recent_metrics) > self._max_recent:
            self._recent_metrics = self._recent_metrics[-self._max_recent:]


# =============================================================================
# GLOBAL INSTANCE AND CONVENIENCE FUNCTIONS
# =============================================================================

_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def record_api_call(
    provider: str,
    operation: str,
    status: str,
    latency_ms: float = 0.0
):
    """Convenience function to record API call."""
    get_metrics_collector().record_api_call(provider, operation, status, latency_ms)


def record_stage_completion(
    stage: str,
    latency_ms: float,
    quality_score_value: float = None
):
    """Convenience function to record stage completion."""
    get_metrics_collector().record_stage_completion(stage, latency_ms, quality_score_value)


def record_cost(provider: str, operation: str, cost_usd: float):
    """Convenience function to record cost."""
    get_metrics_collector().record_cost(provider, operation, cost_usd)
