# tools/assemblyai_tool.py
"""
ASSEMBLYAI TOOL - Wrapper for AssemblyAI API calls

Wraps:
- Audio upload
- Transcription with speaker diarization
- Polling for completion

Features:
- Circuit breaker protection
- Timeout handling
- Structured responses
"""

import os
import asyncio
import time
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from tools.base import BaseTool, ToolResult, CircuitBreaker

load_dotenv()


class AssemblyAITool(BaseTool):
    """
    AssemblyAI API wrapper for speaker diarization.

    Usage:
        tool = AssemblyAITool()

        # Full diarization pipeline
        result = await tool.diarize(audio_bytes)
        if result.success:
            utterances = result.data["utterances"]
    """

    TOOL_NAME = "assemblyai"
    BASE_URL = "https://api.assemblyai.com/v2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        correlation_id: Optional[str] = None
    ):
        super().__init__(circuit_breaker, correlation_id)

        self.api_key = api_key or os.getenv("ASSEMBLYAI_API_KEY")
        if not self.api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found")

    async def upload_audio(self, audio_data: bytes) -> ToolResult:
        """
        Upload audio to AssemblyAI.

        Args:
            audio_data: Raw audio bytes

        Returns:
            ToolResult with upload_url
        """
        operation = "upload"
        start = self._start_timer()

        if not self._check_circuit():
            return self._make_result(
                success=False,
                error="Circuit breaker open - AssemblyAI service unavailable",
                operation=operation
            )

        try:
            headers = {
                "authorization": self.api_key,
                "content-type": "application/octet-stream"
            }

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.BASE_URL}/upload",
                    headers=headers,
                    data=audio_data,
                    timeout=60
                )
            )

            if response.status_code == 200:
                self.circuit_breaker.record_success()
                latency = self._end_timer(start)
                return self._make_result(
                    success=True,
                    data={"upload_url": response.json().get("upload_url")},
                    operation=operation,
                    latency_ms=latency
                )
            else:
                self.circuit_breaker.record_failure()
                latency = self._end_timer(start)
                return self._make_result(
                    success=False,
                    error=f"Upload failed: {response.status_code} - {response.text}",
                    operation=operation,
                    latency_ms=latency
                )

        except Exception as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)
            return self._make_result(
                success=False,
                error=f"Upload error: {str(e)}",
                operation=operation,
                latency_ms=latency
            )

    async def request_transcription(
        self,
        upload_url: str,
        speakers_expected: int = 2
    ) -> ToolResult:
        """
        Request transcription with speaker diarization.

        Args:
            upload_url: URL from upload_audio
            speakers_expected: Number of expected speakers

        Returns:
            ToolResult with transcript_id
        """
        operation = "request_transcription"
        start = self._start_timer()

        if not self._check_circuit():
            return self._make_result(
                success=False,
                error="Circuit breaker open - AssemblyAI service unavailable",
                operation=operation
            )

        try:
            headers = {
                "authorization": self.api_key,
                "content-type": "application/json"
            }

            data = {
                "audio_url": upload_url,
                "speaker_labels": True,
                "speakers_expected": speakers_expected,
                "punctuate": True,
                "format_text": True,
                "speech_model": "best"
            }

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.BASE_URL}/transcript",
                    headers=headers,
                    json=data,
                    timeout=30
                )
            )

            if response.status_code == 200:
                self.circuit_breaker.record_success()
                latency = self._end_timer(start)
                return self._make_result(
                    success=True,
                    data={"transcript_id": response.json().get("id")},
                    operation=operation,
                    latency_ms=latency
                )
            else:
                self.circuit_breaker.record_failure()
                latency = self._end_timer(start)
                return self._make_result(
                    success=False,
                    error=f"Transcription request failed: {response.status_code}",
                    operation=operation,
                    latency_ms=latency
                )

        except Exception as e:
            self.circuit_breaker.record_failure()
            latency = self._end_timer(start)
            return self._make_result(
                success=False,
                error=f"Request error: {str(e)}",
                operation=operation,
                latency_ms=latency
            )

    async def poll_for_completion(
        self,
        transcript_id: str,
        max_wait: int = 300,
        poll_interval: float = 2.0
    ) -> ToolResult:
        """
        Poll for transcription completion.

        Args:
            transcript_id: ID from request_transcription
            max_wait: Maximum wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            ToolResult with full transcript data
        """
        operation = "poll_completion"
        start = self._start_timer()

        headers = {"authorization": self.api_key}
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        f"{self.BASE_URL}/transcript/{transcript_id}",
                        headers=headers,
                        timeout=10
                    )
                )

                if response.status_code == 200:
                    result = response.json()
                    status = result.get("status")

                    if status == "completed":
                        self.circuit_breaker.record_success()
                        latency = self._end_timer(start)
                        return self._make_result(
                            success=True,
                            data=result,
                            operation=operation,
                            latency_ms=latency
                        )
                    elif status == "error":
                        self.circuit_breaker.record_failure()
                        latency = self._end_timer(start)
                        return self._make_result(
                            success=False,
                            error=f"Transcription error: {result.get('error')}",
                            operation=operation,
                            latency_ms=latency
                        )
                    else:
                        # Still processing
                        await asyncio.sleep(poll_interval)
                else:
                    self.circuit_breaker.record_failure()
                    latency = self._end_timer(start)
                    return self._make_result(
                        success=False,
                        error=f"Poll failed: {response.status_code}",
                        operation=operation,
                        latency_ms=latency
                    )

            except Exception as e:
                # Don't fail on single poll error, continue trying
                await asyncio.sleep(poll_interval)

        # Timeout
        latency = self._end_timer(start)
        return self._make_result(
            success=False,
            error=f"Transcription timed out after {max_wait}s",
            operation=operation,
            latency_ms=latency
        )

    async def diarize(
        self,
        audio_data: bytes,
        speakers_expected: int = 2,
        max_wait: int = 300
    ) -> ToolResult:
        """
        Full diarization pipeline: upload -> transcribe -> poll.

        Args:
            audio_data: Raw audio bytes
            speakers_expected: Number of expected speakers
            max_wait: Maximum wait time for completion

        Returns:
            ToolResult with utterances, text, words
        """
        operation = "diarize"
        start = self._start_timer()

        # Step 1: Upload
        upload_result = await self.upload_audio(audio_data)
        if not upload_result.success:
            return self._make_result(
                success=False,
                error=f"Upload failed: {upload_result.error}",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        upload_url = upload_result.data["upload_url"]

        # Step 2: Request transcription
        request_result = await self.request_transcription(upload_url, speakers_expected)
        if not request_result.success:
            return self._make_result(
                success=False,
                error=f"Request failed: {request_result.error}",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        transcript_id = request_result.data["transcript_id"]

        # Step 3: Poll for completion
        poll_result = await self.poll_for_completion(transcript_id, max_wait)
        if not poll_result.success:
            return self._make_result(
                success=False,
                error=f"Completion failed: {poll_result.error}",
                operation=operation,
                latency_ms=self._end_timer(start)
            )

        latency = self._end_timer(start)
        return self._make_result(
            success=True,
            data={
                "utterances": poll_result.data.get("utterances", []),
                "text": poll_result.data.get("text", ""),
                "words": poll_result.data.get("words", []),
                "audio_duration": poll_result.data.get("audio_duration", 0)
            },
            operation=operation,
            latency_ms=latency
        )


# Singleton instance
_tool: Optional[AssemblyAITool] = None


def get_assemblyai_tool(correlation_id: Optional[str] = None) -> AssemblyAITool:
    """Get or create the global AssemblyAI tool."""
    global _tool
    if _tool is None:
        _tool = AssemblyAITool()
    if correlation_id:
        _tool.correlation_id = correlation_id
    return _tool
