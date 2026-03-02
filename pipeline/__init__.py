# pipeline/__init__.py
"""
MedJournee Pipeline Orchestrator

Production-grade multi-agent pipeline with:
- Quality gates at each stage
- Retry logic with exponential backoff
- Self-correction capabilities
- Full state management
"""

from pipeline.orchestrator import (
    MedJourneePipeline,
    get_pipeline,
    process_audio,
    instant_transcribe,
    RetryConfig,
)

__all__ = [
    "MedJourneePipeline",
    "get_pipeline",
    "process_audio",
    "instant_transcribe",
    "RetryConfig",
]
