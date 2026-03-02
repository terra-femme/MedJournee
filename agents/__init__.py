# agents/__init__.py
"""
MedJournee Agent Pipeline

5 independent agents for processing medical conversations:
1. TranscriptionAgent - Audio to text (Whisper)
2. DiarizationAgent - Speaker identification (AssemblyAI)
3. TranslationAgent - Bidirectional translation (deep-translator)
4. TerminologyAgent - Medical term detection (UofM Dictionary)
5. SummarizationAgent - Journal generation (GPT-4)
"""

from agents.transcription_agent import TranscriptionAgent
from agents.diarization_agent import DiarizationAgent
from agents.translation_agent import TranslationAgent
from agents.terminology_agent import TerminologyAgent
from agents.summarization_agent import SummarizationAgent

__all__ = [
    "TranscriptionAgent",
    "DiarizationAgent",
    "TranslationAgent",
    "TerminologyAgent",
    "SummarizationAgent",
]
