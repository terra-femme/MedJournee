# services/whisper_service.py
import openai
import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file
load_dotenv()

# Set your OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

async def transcribe_audio(file, source_language: Optional[str] = None, languages: Optional[list] = None):
    """
    Transcribe audio using OpenAI's Whisper API.

    Supports single-language forced decoding and multi-language auto-detect:
    - `source_language`: legacy single-language param (backward compat)
    - `languages`: list of expected languages.
        - len == 1 → force that language
        - len == 0 or 2+ → omit, Whisper auto-detects (handles code-switching)
    """
    try:
        # Read the uploaded file content
        audio_content = await file.read()

        # Reset file pointer so it can be read again if needed
        await file.seek(0)

        # Create a file tuple that OpenAI API expects
        # Format: (filename, file_content, content_type)
        file_tuple = (file.filename, audio_content, file.content_type)

        # Prepare API call parameters
        api_params = {
            "model": "whisper-1",
            "file": file_tuple,
            "response_format": "json"
        }

        # Determine language param:
        # 1. New `languages` list takes precedence
        # 2. Fall back to legacy `source_language`
        if languages:
            clean = [l for l in languages if l and l not in ("auto", "")]
            if len(clean) == 1:
                api_params["language"] = clean[0]
            # else: 0 or 2+ → omit for auto-detect
        elif source_language and source_language != "auto" and source_language != "":
            api_params["language"] = source_language

        # Make the API call to OpenAI Whisper
        response = openai.audio.transcriptions.create(**api_params)

        # Additional filtering for very short or suspicious responses
        transcribed_text = response.text.strip()

        # Try to get detected language (Whisper doesn't always provide this)
        detected_language = api_params.get("language") or "auto-detected"

        # Return the transcribed text
        return {
            "text": transcribed_text,
            "language": detected_language,
            "success": True
        }

    except Exception as e:
        print(f"Transcription error: {e}")
        return {
            "text": f"Error during transcription: {str(e)}",
            "language": "error",
            "success": False
        }

print("Updated Whisper service loaded with language specification")