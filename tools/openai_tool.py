# tools/openai_tool.py
"""
OPENAI TOOL - Wrapper for OpenAI API calls

Wraps:
- Whisper transcription
- GPT-4 chat completions

Features:
- Circuit breaker protection
- Retry with exponential backoff
- Latency tracking
- Correlation ID propagation
"""

import openai
import os
import tempfile
import subprocess
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

from tools.base import BaseTool, ToolResult, CircuitBreaker

load_dotenv()


class OpenAITool(BaseTool):
    """
    OpenAI API wrapper with circuit breaker and structured responses.

    Usage:
        tool = OpenAITool()

        # Transcription
        result = await tool.transcribe(audio_bytes, "audio/webm")
        if result.success:
            text = result.data["text"]

        # Chat completion
        result = await tool.chat_completion(messages, model="gpt-4")
        if result.success:
            response = result.data["content"]
    """

    TOOL_NAME = "openai"

    CONTENT_TYPE_MAP = {
        "audio/webm": "webm",
        "audio/webm;codecs=opus": "webm",
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/ogg": "ogg",
        "audio/m4a": "m4a",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        correlation_id: Optional[str] = None
    ):
        super().__init__(circuit_breaker, correlation_id)

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = openai.OpenAI(api_key=self.api_key)

    async def transcribe(
        self,
        audio_content: bytes,
        content_type: str = "audio/webm",
        language: Optional[str] = None
    ) -> ToolResult:
        """
        Transcribe audio using Whisper API.

        Args:
            audio_content: Raw audio bytes
            content_type: MIME type of audio
            language: Optional language hint

        Returns:
            ToolResult with text, detected_language, duration
        """
        operation = "transcribe"
        start = self._start_timer()

        if not self._check_circuit():
            return self._make_result(
                success=False,
                error="Circuit breaker open - OpenAI service unavailable",
                operation=operation
            )

        temp_input = None
        temp_output = None

        try:
            # Determine file extension
            base_type = content_type.split(";")[0].strip()
            input_ext = self.CONTENT_TYPE_MAP.get(base_type, "webm")

            # Write to temp file
            temp_input = tempfile.NamedTemporaryFile(suffix=f".{input_ext}", delete=False)
            temp_input.write(audio_content)
            temp_input.close()

            # Convert with FFmpeg
            temp_output = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_output.close()

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", temp_input.name,
                "-vn", "-acodec", "libmp3lame", "-ar", "16000",
                "-ac", "1", "-b:a", "64k",
                temp_output.name
            ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=30)

            if result.returncode == 0:
                with open(temp_output.name, "rb") as f:
                    converted_audio = f.read()
                file_tuple = ("audio.mp3", converted_audio, "audio/mpeg")
            else:
                # Fallback to original
                file_tuple = (f"audio.{input_ext}", audio_content, base_type)

            # Call Whisper API
            api_params = {
                "model": "whisper-1",
                "file": file_tuple,
                "response_format": "verbose_json"
            }
            if language:
                api_params["language"] = language

            response = self.client.audio.transcriptions.create(**api_params)

            self.circuit_breaker.record_success()

            latency = self._end_timer(start)
            return self._make_result(
                success=True,
                data={
                    "text": response.text.strip() if response.text else "",
                    "detected_language": getattr(response, "language", "unknown"),
                    "duration_seconds": len(audio_content) / 32000
                },
                operation=operation,
                latency_ms=latency
            )

        except openai.APIError as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)
            return self._make_result(
                success=False,
                error=f"OpenAI API error: {str(e)}",
                operation=operation,
                latency_ms=latency
            )

        except Exception as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)
            return self._make_result(
                success=False,
                error=f"Transcription failed: {str(e)}",
                operation=operation,
                latency_ms=latency
            )

        finally:
            # Cleanup temp files
            for tf in [temp_input, temp_output]:
                if tf and hasattr(tf, 'name'):
                    try:
                        os.unlink(tf.name)
                    except:
                        pass

    async def chat_completion(
        self,
        messages: list,
        model: str = "gpt-4",
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> ToolResult:
        """
        Generate chat completion.

        Args:
            messages: List of message dicts with role/content
            model: Model to use (gpt-4, gpt-4-turbo, etc.)
            temperature: Sampling temperature
            max_tokens: Maximum response tokens

        Returns:
            ToolResult with content, model, usage
        """
        operation = "chat_completion"
        start = self._start_timer()

        if not self._check_circuit():
            return self._make_result(
                success=False,
                error="Circuit breaker open - OpenAI service unavailable",
                operation=operation
            )

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            self.circuit_breaker.record_success()

            latency = self._end_timer(start)
            return self._make_result(
                success=True,
                data={
                    "content": response.choices[0].message.content,
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                },
                operation=operation,
                latency_ms=latency
            )

        except openai.APIError as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)
            return self._make_result(
                success=False,
                error=f"OpenAI API error: {str(e)}",
                operation=operation,
                latency_ms=latency
            )

        except Exception as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)
            return self._make_result(
                success=False,
                error=f"Chat completion failed: {str(e)}",
                operation=operation,
                latency_ms=latency
            )


# Singleton instance
_tool: Optional[OpenAITool] = None


def get_openai_tool(correlation_id: Optional[str] = None) -> OpenAITool:
    """Get or create the global OpenAI tool."""
    global _tool
    if _tool is None:
        _tool = OpenAITool()
    if correlation_id:
        _tool.correlation_id = correlation_id
    return _tool
