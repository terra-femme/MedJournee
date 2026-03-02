# tools/base.py
"""
BASE TOOL CLASSES

Provides common infrastructure for all tool wrappers:
- ToolResult for standardized responses
- ToolError for error handling
- CircuitBreaker for fault tolerance
- Async timeout support
- Structured logging integration
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, TypeVar, Callable, Awaitable
from datetime import datetime
from contextlib import asynccontextmanager
from functools import wraps
import asyncio
import time


# =============================================================================
# TIMEOUT CONFIGURATION
# =============================================================================

class TimeoutConfig:
    """
    Timeout configuration for different operations.

    All values are in seconds.
    """
    # Transcription: Whisper API can be slow for long audio
    TRANSCRIPTION = 60.0

    # Diarization: AssemblyAI processing can take several minutes
    DIARIZATION = 300.0

    # Translation: Usually fast, but may have network delays
    TRANSLATION = 30.0

    # Summarization: GPT-4 can be slow for complex summaries
    SUMMARIZATION = 60.0

    # Terminology detection: Offline dictionary lookup
    TERMINOLOGY = 10.0

    # Default timeout for unspecified operations
    DEFAULT = 30.0

    # Maximum request timeout (for middleware)
    MAX_REQUEST = 300.0  # 5 minutes

    @classmethod
    def get(cls, operation: str) -> float:
        """Get timeout for an operation by name."""
        return getattr(cls, operation.upper(), cls.DEFAULT)


class TimeoutError(Exception):
    """Custom timeout error with operation context."""
    def __init__(self, operation: str, timeout_seconds: float, message: Optional[str] = None):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        msg = message or f"Operation '{operation}' timed out after {timeout_seconds}s"
        super().__init__(msg)


@asynccontextmanager
async def async_timeout(seconds: float, operation: str = "operation"):
    """
    Context manager for async timeouts.

    Usage:
        async with async_timeout(30.0, "transcription"):
            result = await some_slow_operation()

    Raises:
        TimeoutError: If operation exceeds timeout
    """
    try:
        async with asyncio.timeout(seconds):
            yield
    except asyncio.TimeoutError:
        raise TimeoutError(operation, seconds)


T = TypeVar('T')


async def with_timeout(
    coro: Awaitable[T],
    seconds: float,
    operation: str = "operation"
) -> T:
    """
    Execute a coroutine with a timeout.

    Usage:
        result = await with_timeout(
            some_slow_operation(),
            timeout=30.0,
            operation="transcription"
        )

    Args:
        coro: Coroutine to execute
        seconds: Timeout in seconds
        operation: Operation name for error messages

    Returns:
        Result of the coroutine

    Raises:
        TimeoutError: If operation exceeds timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(operation, seconds)


def timeout_decorator(seconds: float = None, operation: str = None):
    """
    Decorator to add timeout to async functions.

    Usage:
        @timeout_decorator(seconds=30.0, operation="transcription")
        async def transcribe(audio):
            ...

        # Or use TimeoutConfig:
        @timeout_decorator(operation="TRANSCRIPTION")
        async def transcribe(audio):
            ...  # Uses TimeoutConfig.TRANSCRIPTION
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            timeout_seconds = seconds
            if timeout_seconds is None:
                timeout_seconds = TimeoutConfig.get(operation or func.__name__)

            op_name = operation or func.__name__

            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(op_name, timeout_seconds)

        return wrapper
    return decorator


@dataclass
class ToolResult:
    """Standardized result from any tool call."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    tool_name: str = ""
    operation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "tool_name": self.tool_name,
            "operation": self.operation,
            "metadata": self.metadata
        }


class ToolError(Exception):
    """Custom exception for tool failures."""
    def __init__(self, message: str, tool_name: str, operation: str, recoverable: bool = True):
        super().__init__(message)
        self.tool_name = tool_name
        self.operation = operation
        self.recoverable = recoverable
        self.timestamp = datetime.now().isoformat()


class CircuitState:
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker pattern for external service calls.

    Prevents cascading failures by:
    - Tracking consecutive failures
    - Opening circuit after threshold reached
    - Auto-testing recovery after timeout

    Usage:
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        async def call_api():
            if not breaker.allow_request():
                raise ToolError("Circuit open", "api", "call", recoverable=True)

            try:
                result = await actual_api_call()
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1
    ):
        """
        Args:
            failure_threshold: Consecutive failures to open circuit
            recovery_timeout: Seconds before testing recovery
            half_open_max_calls: Calls allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        """Get current circuit state, checking for recovery timeout."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed."""
        state = self.state  # Triggers state check

        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        else:  # OPEN
            return False

    def record_success(self):
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._reset()
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0  # Reset consecutive failures

    def record_failure(self):
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._success_count = 0

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def _reset(self):
        """Reset to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0

    def get_status(self) -> Dict[str, Any]:
        """Get current breaker status."""
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": self._last_failure_time,
            "threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout
        }


class BaseTool:
    """
    Base class for all tools.

    Provides:
    - Circuit breaker integration
    - Latency tracking
    - Standardized error handling
    - Correlation ID propagation
    """

    TOOL_NAME = "base_tool"

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        correlation_id: Optional[str] = None
    ):
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.correlation_id = correlation_id

    def _start_timer(self) -> float:
        return time.time()

    def _end_timer(self, start: float) -> float:
        return (time.time() - start) * 1000  # Return ms

    def _check_circuit(self) -> bool:
        """Check if circuit allows request."""
        return self.circuit_breaker.allow_request()

    def _make_result(
        self,
        success: bool,
        data: Any = None,
        error: Optional[str] = None,
        operation: str = "",
        latency_ms: float = 0.0,
        **metadata
    ) -> ToolResult:
        """Create standardized result."""
        return ToolResult(
            success=success,
            data=data,
            error=error,
            latency_ms=latency_ms,
            tool_name=self.TOOL_NAME,
            operation=operation,
            metadata={
                "correlation_id": self.correlation_id,
                **metadata
            }
        )

    def _make_error(
        self,
        message: str,
        operation: str,
        recoverable: bool = True
    ) -> ToolError:
        """Create standardized error."""
        return ToolError(
            message=message,
            tool_name=self.TOOL_NAME,
            operation=operation,
            recoverable=recoverable
        )
