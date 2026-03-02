# guardrails/rate_limiter.py
"""
RATE LIMITER GUARDRAIL

Priority: 5 (cost control)

Implements sliding window rate limiting for:
- Per-user request limits (10/min, 100/hour, 500/day)
- Per-session limits (3 concurrent, 30 min audio/session)

Protects against:
- API cost overruns
- Abuse
- DDoS-like patterns
"""

import time
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
)


@dataclass
class RateLimitConfig:
    """Configuration for rate limits"""
    # Request limits
    requests_per_minute: int = 10
    requests_per_hour: int = 100
    requests_per_day: int = 500

    # Session limits
    max_concurrent_sessions: int = 3
    max_audio_minutes_per_session: float = 30.0
    max_audio_minutes_per_day: float = 120.0

    # Cooldown after hitting limit (seconds)
    cooldown_seconds: float = 60.0


@dataclass
class UserRateState:
    """Rate limiting state for a user"""
    user_id: str
    request_timestamps: List[float] = field(default_factory=list)
    active_sessions: Dict[str, float] = field(default_factory=dict)  # session_id -> start_time
    audio_minutes_today: float = 0.0
    last_reset_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    blocked_until: Optional[float] = None


class RateLimiter(BaseGuardrail):
    """
    Sliding window rate limiter for MedJournee.

    Tracks requests per user and enforces limits to prevent
    abuse and control costs.
    """

    NAME = "rate_limiter"
    PRIORITY = 5  # Cost control
    DESCRIPTION = "Rate limits requests per user/session"

    def __init__(
        self,
        enabled: bool = True,
        config: Optional[RateLimitConfig] = None
    ):
        """
        Initialize rate limiter.

        Args:
            enabled: Whether this guardrail is active
            config: Rate limit configuration
        """
        super().__init__(enabled)
        self.config = config or RateLimitConfig()

        # User states: user_id -> UserRateState
        self._user_states: Dict[str, UserRateState] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check if request is within rate limits.

        Args:
            context: Context with user_id and session_id

        Returns:
            GuardrailResult - BLOCK if over limit, ALLOW otherwise
        """
        user_id = context.user_id or context.family_id or "anonymous"
        session_id = context.session_id

        async with self._lock:
            # Get or create user state
            state = self._get_or_create_state(user_id)

            # Reset daily counters if new day
            self._check_daily_reset(state)

            # Check if user is in cooldown
            if state.blocked_until and time.time() < state.blocked_until:
                remaining = int(state.blocked_until - time.time())
                return self._block(
                    message=f"Rate limit cooldown: {remaining}s remaining",
                    retry_after=remaining,
                    limit_type="cooldown"
                )

            # Check request rate limits
            now = time.time()
            rate_result = self._check_request_rate(state, now)
            if rate_result:
                return rate_result

            # Check concurrent sessions
            session_result = self._check_concurrent_sessions(state, session_id)
            if session_result:
                return session_result

            # Check audio limits if provided
            audio_minutes = context.metadata.get("audio_minutes", 0)
            if audio_minutes > 0:
                audio_result = self._check_audio_limits(state, audio_minutes)
                if audio_result:
                    return audio_result

            # All checks passed - record this request
            state.request_timestamps.append(now)

            return self._allow(
                message="Within rate limits",
                requests_minute=self._count_requests_in_window(state, 60),
                requests_hour=self._count_requests_in_window(state, 3600),
                requests_day=self._count_requests_in_window(state, 86400)
            )

    async def record_audio_usage(
        self,
        user_id: str,
        session_id: str,
        audio_minutes: float
    ) -> GuardrailResult:
        """
        Record audio usage for a user.

        Args:
            user_id: User identifier
            session_id: Session identifier
            audio_minutes: Minutes of audio processed

        Returns:
            GuardrailResult indicating if usage is allowed
        """
        async with self._lock:
            state = self._get_or_create_state(user_id)
            self._check_daily_reset(state)

            # Check session audio limit
            session_audio = state.active_sessions.get(session_id, 0)
            total_session = session_audio + audio_minutes

            if total_session > self.config.max_audio_minutes_per_session:
                return self._block(
                    message=f"Session audio limit exceeded: {total_session:.1f}/{self.config.max_audio_minutes_per_session}min",
                    limit_type="session_audio",
                    current=total_session,
                    max=self.config.max_audio_minutes_per_session
                )

            # Check daily audio limit
            total_daily = state.audio_minutes_today + audio_minutes
            if total_daily > self.config.max_audio_minutes_per_day:
                return self._block(
                    message=f"Daily audio limit exceeded: {total_daily:.1f}/{self.config.max_audio_minutes_per_day}min",
                    limit_type="daily_audio",
                    current=total_daily,
                    max=self.config.max_audio_minutes_per_day
                )

            # Record usage
            state.active_sessions[session_id] = total_session
            state.audio_minutes_today += audio_minutes

            return self._allow(
                message="Audio usage recorded",
                session_audio=total_session,
                daily_audio=state.audio_minutes_today
            )

    async def start_session(self, user_id: str, session_id: str) -> GuardrailResult:
        """
        Register a new session for a user.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            GuardrailResult indicating if session is allowed
        """
        async with self._lock:
            state = self._get_or_create_state(user_id)

            # Check concurrent sessions
            active_count = len(state.active_sessions)
            if active_count >= self.config.max_concurrent_sessions:
                return self._block(
                    message=f"Max concurrent sessions reached: {active_count}/{self.config.max_concurrent_sessions}",
                    limit_type="concurrent_sessions",
                    current=active_count,
                    max=self.config.max_concurrent_sessions
                )

            # Register session
            state.active_sessions[session_id] = 0  # 0 audio minutes initially

            return self._allow(
                message="Session started",
                active_sessions=active_count + 1
            )

    async def end_session(self, user_id: str, session_id: str) -> None:
        """
        End a session for a user.

        Args:
            user_id: User identifier
            session_id: Session identifier
        """
        async with self._lock:
            state = self._get_or_create_state(user_id)
            state.active_sessions.pop(session_id, None)

    def _get_or_create_state(self, user_id: str) -> UserRateState:
        """Get or create user rate state."""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserRateState(user_id=user_id)
        return self._user_states[user_id]

    def _check_daily_reset(self, state: UserRateState) -> None:
        """Reset daily counters if new day."""
        today = datetime.now().strftime("%Y-%m-%d")
        if state.last_reset_date != today:
            state.request_timestamps = []
            state.audio_minutes_today = 0.0
            state.last_reset_date = today
            state.blocked_until = None

    def _check_request_rate(self, state: UserRateState, now: float) -> Optional[GuardrailResult]:
        """Check request rate limits."""
        # Clean old timestamps (keep last 24h)
        cutoff = now - 86400
        state.request_timestamps = [t for t in state.request_timestamps if t > cutoff]

        # Check per-minute limit
        requests_minute = self._count_requests_in_window(state, 60)
        if requests_minute >= self.config.requests_per_minute:
            state.blocked_until = now + self.config.cooldown_seconds
            return self._block(
                message=f"Rate limit exceeded: {requests_minute}/{self.config.requests_per_minute} per minute",
                limit_type="per_minute",
                current=requests_minute,
                max=self.config.requests_per_minute,
                retry_after=int(self.config.cooldown_seconds)
            )

        # Check per-hour limit
        requests_hour = self._count_requests_in_window(state, 3600)
        if requests_hour >= self.config.requests_per_hour:
            state.blocked_until = now + self.config.cooldown_seconds * 5
            return self._block(
                message=f"Rate limit exceeded: {requests_hour}/{self.config.requests_per_hour} per hour",
                limit_type="per_hour",
                current=requests_hour,
                max=self.config.requests_per_hour,
                retry_after=int(self.config.cooldown_seconds * 5)
            )

        # Check per-day limit
        requests_day = self._count_requests_in_window(state, 86400)
        if requests_day >= self.config.requests_per_day:
            # Block until midnight
            return self._block(
                message=f"Daily rate limit exceeded: {requests_day}/{self.config.requests_per_day}",
                limit_type="per_day",
                current=requests_day,
                max=self.config.requests_per_day
            )

        return None

    def _check_concurrent_sessions(
        self,
        state: UserRateState,
        session_id: str
    ) -> Optional[GuardrailResult]:
        """Check concurrent session limits."""
        # If this is a new session, check limit
        if session_id not in state.active_sessions:
            if len(state.active_sessions) >= self.config.max_concurrent_sessions:
                return self._block(
                    message=f"Max concurrent sessions: {len(state.active_sessions)}/{self.config.max_concurrent_sessions}",
                    limit_type="concurrent_sessions",
                    current=len(state.active_sessions),
                    max=self.config.max_concurrent_sessions
                )

        return None

    def _check_audio_limits(
        self,
        state: UserRateState,
        audio_minutes: float
    ) -> Optional[GuardrailResult]:
        """Check audio processing limits."""
        total_daily = state.audio_minutes_today + audio_minutes
        if total_daily > self.config.max_audio_minutes_per_day:
            return self._block(
                message=f"Daily audio limit: {total_daily:.1f}/{self.config.max_audio_minutes_per_day}min",
                limit_type="daily_audio",
                current=total_daily,
                max=self.config.max_audio_minutes_per_day
            )

        return None

    def _count_requests_in_window(self, state: UserRateState, window_seconds: int) -> int:
        """Count requests within a time window."""
        cutoff = time.time() - window_seconds
        return sum(1 for t in state.request_timestamps if t > cutoff)

    async def get_user_status(self, user_id: str) -> Dict:
        """Get rate limit status for a user."""
        async with self._lock:
            if user_id not in self._user_states:
                return {"user_id": user_id, "status": "no_activity"}

            state = self._user_states[user_id]
            now = time.time()

            return {
                "user_id": user_id,
                "requests_minute": self._count_requests_in_window(state, 60),
                "requests_hour": self._count_requests_in_window(state, 3600),
                "requests_day": self._count_requests_in_window(state, 86400),
                "active_sessions": len(state.active_sessions),
                "audio_minutes_today": state.audio_minutes_today,
                "blocked_until": state.blocked_until,
                "is_blocked": state.blocked_until and now < state.blocked_until,
                "limits": {
                    "per_minute": self.config.requests_per_minute,
                    "per_hour": self.config.requests_per_hour,
                    "per_day": self.config.requests_per_day,
                    "concurrent_sessions": self.config.max_concurrent_sessions,
                    "audio_per_session": self.config.max_audio_minutes_per_session,
                    "audio_per_day": self.config.max_audio_minutes_per_day,
                }
            }


# Global instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# Convenience functions
async def check_rate_limit(user_id: str, session_id: str) -> GuardrailResult:
    """Check if a request is within rate limits."""
    limiter = get_rate_limiter()
    context = GuardrailContext(session_id=session_id, user_id=user_id)
    return await limiter.check(context)
