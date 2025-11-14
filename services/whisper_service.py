# services/whisper_service.py
import openai
import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file
load_dotenv()

# Set your OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

async def transcribe_audio(file, source_language: Optional[str] = None):
    """
    Transcribe audio using OpenAI's Whisper API with optional language specification
    This avoids FFmpeg issues and is much faster than local processing
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
        
        # Only add language parameter if explicitly specified
        # This allows Whisper to auto-detect language when source_language is None
        if source_language and source_language != "auto" and source_language != "":
            api_params["language"] = source_language
        
        # Make the API call to OpenAI Whisper
        response = openai.audio.transcriptions.create(**api_params)
        
        # Additional filtering for very short or suspicious responses
        transcribed_text = response.text.strip()
        
        # Try to get detected language (Whisper doesn't always provide this)
        detected_language = source_language if source_language else "auto-detected"
        
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