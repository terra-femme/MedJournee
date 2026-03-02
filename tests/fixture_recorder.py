#!/usr/bin/env python3
"""
Audio Fixture Recorder for MedJournee Testing

Records audio from microphone and saves as test fixture.

Usage:
    python tests/fixture_recorder.py my_test_name --duration 15
    python tests/fixture_recorder.py arm_pain_english --duration 30

Requirements:
    pip install pyaudio
    # On Windows, may need: pip install pipwin && pipwin install pyaudio
"""

import argparse
import asyncio
import json
import sys
import wave
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests import FIXTURES_DIR, EXPECTED_DIR


def check_pyaudio():
    """Check if PyAudio is available"""
    try:
        import pyaudio
        return True
    except ImportError:
        return False


def check_ffmpeg():
    """Check if FFmpeg is available"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def record_audio_pyaudio(output_path: Path, duration: int) -> bool:
    """Record audio using PyAudio"""
    import pyaudio

    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000  # Whisper prefers 16kHz

    p = pyaudio.PyAudio()

    print(f"\nRecording for {duration} seconds...")
    print("Speak now!")
    print("-" * 40)

    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    frames = []
    for i in range(0, int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)
        # Show progress
        elapsed = i * CHUNK / RATE
        remaining = duration - elapsed
        if i % int(RATE / CHUNK) == 0:
            print(f"  {remaining:.0f} seconds remaining...")

    print("-" * 40)
    print("Recording complete!")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Save as WAV first
    wav_path = output_path.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))

    # Convert to WebM using FFmpeg if available
    if check_ffmpeg():
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(wav_path),
                "-c:a", "libopus",
                "-b:a", "64k",
                str(output_path)
            ], capture_output=True, check=True)
            wav_path.unlink()  # Remove temp WAV
            print(f"Saved as WebM: {output_path}")
            return True
        except subprocess.CalledProcessError:
            print(f"FFmpeg conversion failed, keeping WAV: {wav_path}")
            return True
    else:
        print(f"FFmpeg not found, saved as WAV: {wav_path}")
        return True


def record_audio_sounddevice(output_path: Path, duration: int) -> bool:
    """Record audio using sounddevice (alternative to PyAudio)"""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("sounddevice not available")
        return False

    RATE = 16000
    CHANNELS = 1

    print(f"\nRecording for {duration} seconds...")
    print("Speak now!")
    print("-" * 40)

    recording = sd.rec(
        int(duration * RATE),
        samplerate=RATE,
        channels=CHANNELS,
        dtype='int16'
    )
    sd.wait()

    print("-" * 40)
    print("Recording complete!")

    # Save as WAV
    wav_path = output_path.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(RATE)
        wf.writeframes(recording.tobytes())

    # Convert to WebM if FFmpeg available
    if check_ffmpeg():
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(wav_path),
                "-c:a", "libopus",
                "-b:a", "64k",
                str(output_path)
            ], capture_output=True, check=True)
            wav_path.unlink()
            print(f"Saved as WebM: {output_path}")
            return True
        except subprocess.CalledProcessError:
            pass

    print(f"Saved as WAV: {wav_path}")
    return True


def create_fixture_entry(
    name: str,
    filename: str,
    description: str,
    expected_language: str,
    expected_transcript: str,
    expected_keywords: list,
    max_wer: float = 0.3
) -> dict:
    """Create fixture config entry"""
    return {
        "audio_file": filename,
        "description": description,
        "expected_language": expected_language,
        "expected_transcript": expected_transcript,
        "expected_text_contains": expected_keywords,
        "expected_text_not_contains": ["subscribe", "like", "channel", "video", "dang ky", "kenh"],
        "min_confidence": 0.6,
        "max_wer": max_wer,
        "expected_speaker_count": 1,
        "category": "transcription",
        "recorded_at": datetime.now().isoformat()
    }


def update_fixtures_config(name: str, fixture_config: dict):
    """Update fixtures.json with new fixture"""
    config_path = EXPECTED_DIR / "fixtures.json"

    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {"fixtures": {}, "test_suites": {}}

    config["fixtures"][name] = fixture_config

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Updated fixtures.json with '{name}'")


async def record_fixture(name: str, duration: int = 15):
    """
    Interactive fixture recording.

    Steps:
    1. Record audio
    2. Run through pipeline for preview
    3. Prompt for expected values
    4. Save fixture config
    """
    print(f"\n{'=' * 60}")
    print(f" Recording New Fixture: {name}")
    print(f"{'=' * 60}")

    # Determine output path
    output_path = FIXTURES_DIR / f"{name}.webm"
    if output_path.exists():
        response = input(f"\nFixture '{name}' already exists. Overwrite? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    # Record audio
    print("\nPreparing to record...")

    if check_pyaudio():
        success = record_audio_pyaudio(output_path, duration)
    else:
        print("PyAudio not available. Trying sounddevice...")
        try:
            success = record_audio_sounddevice(output_path, duration)
        except Exception as e:
            print(f"Recording failed: {e}")
            print("\nTo record audio, install one of:")
            print("  pip install pyaudio")
            print("  pip install sounddevice")
            print("\nAlternatively, record audio externally and place in:")
            print(f"  {FIXTURES_DIR}/{name}.webm")
            return

    if not success:
        print("Recording failed.")
        return

    # Preview with pipeline
    print("\nRunning through pipeline for preview...")
    print("-" * 40)

    try:
        from agents.transcription_agent import TranscriptionAgent

        # Load recorded audio
        actual_path = output_path if output_path.exists() else output_path.with_suffix(".wav")
        with open(actual_path, "rb") as f:
            audio_content = f.read()

        # Create mock file
        class MockFile:
            def __init__(self, content):
                self.content = content
                self.content_type = "audio/webm" if str(actual_path).endswith(".webm") else "audio/wav"
            async def read(self):
                return self.content
            async def seek(self, pos):
                pass

        agent = TranscriptionAgent()
        result = await agent.transcribe(MockFile(audio_content))

        print(f"\nPipeline Result:")
        print(f"  Text: {result.text[:200]}..." if len(result.text) > 200 else f"  Text: {result.text}")
        print(f"  Language: {result.detected_language}")
        print(f"  Confidence: {result.confidence:.2f}")
        if result.was_filtered:
            print(f"  Filtered: {result.filter_reason}")

    except Exception as e:
        print(f"Preview failed: {e}")
        result = None

    # Get expected values from user
    print("\n" + "-" * 40)
    print("Enter expected values for this fixture:")
    print("-" * 40)

    description = input("\nDescription: ") or f"Test recording for {name}"

    default_lang = result.detected_language if result else "en"
    expected_lang = input(f"Expected language [{default_lang}]: ") or default_lang

    # IMPORTANT: Get the exact transcript (ground truth)
    print("\n** GROUND TRUTH TRANSCRIPT **")
    print("Enter EXACTLY what you said (this is used to measure accuracy):")
    default_transcript = result.text if result else ""
    if default_transcript:
        print(f"  Pipeline heard: '{default_transcript}'")
        use_pipeline = input("Use pipeline result as ground truth? [y/N]: ").lower() == 'y'
        if use_pipeline:
            expected_transcript = default_transcript
        else:
            expected_transcript = input("Enter exact transcript: ")
    else:
        expected_transcript = input("Enter exact transcript: ")

    # Extract keywords from transcript if not provided manually
    keywords_input = input("Expected keywords (comma-separated, or press Enter to auto-extract): ")
    if keywords_input.strip():
        expected_keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
    else:
        # Auto-extract meaningful words from transcript
        import re
        words = re.findall(r'\b[a-zA-Z]{4,}\b', expected_transcript.lower())
        # Remove common words
        stopwords = {'that', 'this', 'with', 'have', 'from', 'they', 'been', 'were', 'said', 'each', 'which', 'their', 'will', 'would', 'there', 'could', 'other', 'into', 'more', 'some', 'these', 'than', 'then', 'them', 'very', 'just', 'about', 'over', 'such', 'your', 'only'}
        expected_keywords = [w for w in set(words) if w not in stopwords][:6]
        print(f"  Auto-extracted keywords: {expected_keywords}")

    # Create and save fixture config
    filename = actual_path.name
    fixture_config = create_fixture_entry(
        name=name,
        filename=filename,
        description=description,
        expected_language=expected_lang,
        expected_transcript=expected_transcript,
        expected_keywords=expected_keywords
    )

    update_fixtures_config(name, fixture_config)

    print(f"\n{'=' * 60}")
    print(" Fixture Created Successfully!")
    print(f"{'=' * 60}")
    print(f"  Audio: {actual_path}")
    print(f"  Config: fixtures.json -> {name}")
    print(f"\nTest it with:")
    print(f"  python tests/test_pipeline.py --fixture {name}")
    print(f"  python tests/test_pipeline.py --isolate {name}")
    print()


async def main():
    parser = argparse.ArgumentParser(
        description="Record audio fixture for MedJournee testing"
    )
    parser.add_argument("name", help="Name for the fixture")
    parser.add_argument("--duration", "-d", type=int, default=15,
                       help="Recording duration in seconds (default: 15)")

    args = parser.parse_args()

    await record_fixture(args.name, args.duration)


if __name__ == "__main__":
    asyncio.run(main())
