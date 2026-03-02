# telemetry/__init__.py
"""
MEDJOURNEE TELEMETRY MODULE

Production-grade observability including:
- Prometheus metrics for monitoring
- OpenTelemetry tracing for distributed tracing
- Custom metrics for medical translation pipeline
"""

from telemetry.metrics import (
    MetricsCollector,
    get_metrics_collector,
    record_api_call,
    record_stage_completion,
    record_cost,
)

from telemetry.tracing import (
    Tracer,
    get_tracer,
    trace_operation,
)

__all__ = [
    # Metrics
    "MetricsCollector",
    "get_metrics_collector",
    "record_api_call",
    "record_stage_completion",
    "record_cost",
    # Tracing
    "Tracer",
    "get_tracer",
    "trace_operation",
]
