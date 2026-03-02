# tests/__init__.py
"""
Automated Audio Testing Framework for MedJournee

This package provides:
- Audio fixture management (pre-recorded test samples)
- Pipeline testing (transcription, diarization, translation)
- API isolation testing (compare direct Whisper vs pipeline)
- Regression detection
- Detailed logging and reports
"""

from pathlib import Path

# Test directories
TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "audio_fixtures"
EXPECTED_DIR = TESTS_DIR / "expected_outputs"
REPORTS_DIR = TESTS_DIR / "reports"

# Ensure directories exist
FIXTURES_DIR.mkdir(exist_ok=True)
EXPECTED_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
