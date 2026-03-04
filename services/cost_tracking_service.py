# services/cost_tracking_service.py
"""
COST TRACKING SERVICE

Track and manage API costs per session for:
- OpenAI Whisper (transcription)
- OpenAI GPT-4 (summarization)
- AssemblyAI (diarization)

Features:
- Per-session cost tracking
- Budget enforcement
- Cost breakdown by provider/operation
- Historical cost analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import asyncio


class Provider(str, Enum):
    """API providers"""
    OPENAI = "openai"
    ASSEMBLYAI = "assemblyai"
    GOOGLE = "google"


class Operation(str, Enum):
    """Types of API operations"""
    WHISPER = "whisper"
    GPT4_INPUT = "gpt4_input"
    GPT4_OUTPUT = "gpt4_output"
    DIARIZATION = "diarization"
    TRANSLATION = "translation"  # Google Translate is free


@dataclass
class CostRecord:
    """Record of a single API cost"""
    session_id: str
    provider: Provider
    operation: Operation
    quantity: float  # minutes or tokens
    unit: str  # "minutes", "tokens", "characters"
    cost_usd: float
    user_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


@dataclass
class SessionCostSummary:
    """Summary of costs for a session"""
    session_id: str
    total_cost_usd: float
    breakdown: Dict[str, float]  # operation -> cost
    provider_breakdown: Dict[str, float]  # provider -> cost
    records: List[CostRecord]
    budget_limit: Optional[float] = None
    budget_remaining: Optional[float] = None
    is_over_budget: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class CostTracker:
    """
    Track API costs per session.

    Pricing (as of 2024):
    - OpenAI Whisper: $0.006 per minute
    - OpenAI GPT-4 Turbo: $0.01/1K input, $0.03/1K output
    - OpenAI GPT-4: $0.03/1K input, $0.06/1K output
    - AssemblyAI Diarization: ~$0.12 per minute (includes transcription)

    Usage:
        tracker = CostTracker()

        # Record costs
        await tracker.record_whisper_call("session-123", audio_minutes=5.0)
        await tracker.record_gpt4_call("session-123", input_tokens=1000, output_tokens=500)

        # Get summary
        summary = await tracker.get_session_cost("session-123")
        print(f"Total cost: ${summary.total_cost_usd:.4f}")

        # Check budget
        can_proceed = await tracker.check_budget("session-123", budget_limit=1.0)
    """

    # Pricing constants (USD)
    PRICING = {
        # OpenAI pricing
        "openai_whisper": 0.006,           # per minute
        "openai_gpt4_input": 0.03,         # per 1K tokens (GPT-4)
        "openai_gpt4_output": 0.06,        # per 1K tokens (GPT-4)
        "openai_gpt4_turbo_input": 0.01,   # per 1K tokens (GPT-4 Turbo)
        "openai_gpt4_turbo_output": 0.03,  # per 1K tokens (GPT-4 Turbo)

        # AssemblyAI pricing
        "assemblyai_diarization": 0.12,    # per minute (includes transcription)
        "assemblyai_transcription": 0.00023,  # per second (~$0.01384/minute)

        # Google Translate (FREE via deep-translator library)
        "google_translate": 0.0,
    }

    def __init__(self, use_gpt4_turbo: bool = True):
        """
        Initialize cost tracker.

        Args:
            use_gpt4_turbo: If True, use GPT-4 Turbo pricing (cheaper)
        """
        self.use_gpt4_turbo = use_gpt4_turbo
        self._session_costs: Dict[str, List[CostRecord]] = {}
        self._session_budgets: Dict[str, float] = {}
        self._lock = asyncio.Lock()

        # Supabase for persistence
        import os
        from supabase import create_client
        from dotenv import load_dotenv
        load_dotenv()
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        self._supabase = create_client(supabase_url, supabase_key) if supabase_url else None

    async def record_whisper_call(
        self,
        session_id: str,
        audio_minutes: float,
        audio_seconds: Optional[float] = None,
        user_id: str = ""
    ) -> CostRecord:
        """
        Record an OpenAI Whisper API call.

        Args:
            session_id: Session identifier
            audio_minutes: Duration of audio in minutes
            audio_seconds: Alternative: duration in seconds

        Returns:
            CostRecord for this call
        """
        if audio_seconds is not None:
            audio_minutes = audio_seconds / 60.0

        cost = audio_minutes * self.PRICING["openai_whisper"]

        record = CostRecord(
            session_id=session_id,
            provider=Provider.OPENAI,
            operation=Operation.WHISPER,
            quantity=audio_minutes,
            unit="minutes",
            cost_usd=cost,
            user_id=user_id,
            metadata={"audio_seconds": audio_minutes * 60}
        )

        await self._add_record(record)
        return record

    async def record_gpt4_call(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        model: str = "gpt-4",
        user_id: str = ""
    ) -> CostRecord:
        """
        Record an OpenAI GPT-4 API call.

        Args:
            session_id: Session identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name (gpt-4, gpt-4-turbo, etc.)

        Returns:
            CostRecord for this call
        """
        # Determine pricing based on model
        is_turbo = "turbo" in model.lower() or self.use_gpt4_turbo

        if is_turbo:
            input_price = self.PRICING["openai_gpt4_turbo_input"]
            output_price = self.PRICING["openai_gpt4_turbo_output"]
        else:
            input_price = self.PRICING["openai_gpt4_input"]
            output_price = self.PRICING["openai_gpt4_output"]

        # Calculate cost (pricing is per 1K tokens)
        input_cost = (input_tokens / 1000) * input_price
        output_cost = (output_tokens / 1000) * output_price
        total_cost = input_cost + output_cost

        # Create two records for detailed tracking
        records = []

        # Input tokens record
        input_record = CostRecord(
            session_id=session_id,
            provider=Provider.OPENAI,
            operation=Operation.GPT4_INPUT,
            quantity=input_tokens,
            unit="tokens",
            cost_usd=input_cost,
            user_id=user_id,
            metadata={"model": model, "is_turbo": is_turbo}
        )
        await self._add_record(input_record)
        records.append(input_record)

        # Output tokens record
        output_record = CostRecord(
            session_id=session_id,
            provider=Provider.OPENAI,
            operation=Operation.GPT4_OUTPUT,
            quantity=output_tokens,
            unit="tokens",
            cost_usd=output_cost,
            user_id=user_id,
            metadata={"model": model, "is_turbo": is_turbo}
        )
        await self._add_record(output_record)
        records.append(output_record)

        # Return combined record for convenience
        return CostRecord(
            session_id=session_id,
            provider=Provider.OPENAI,
            operation=Operation.GPT4_INPUT,  # Primary operation
            quantity=input_tokens + output_tokens,
            unit="tokens",
            cost_usd=total_cost,
            metadata={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost": input_cost,
                "output_cost": output_cost
            }
        )

    async def record_assemblyai_call(
        self,
        session_id: str,
        audio_minutes: float,
        audio_seconds: Optional[float] = None,
        with_diarization: bool = True,
        user_id: str = ""
    ) -> CostRecord:
        """
        Record an AssemblyAI API call.

        Args:
            session_id: Session identifier
            audio_minutes: Duration of audio in minutes
            audio_seconds: Alternative: duration in seconds
            with_diarization: Whether diarization was enabled

        Returns:
            CostRecord for this call
        """
        if audio_seconds is not None:
            audio_minutes = audio_seconds / 60.0

        # Diarization costs more than basic transcription
        if with_diarization:
            cost = audio_minutes * self.PRICING["assemblyai_diarization"]
            operation = Operation.DIARIZATION
        else:
            cost = audio_minutes * (self.PRICING["assemblyai_transcription"] * 60)
            operation = Operation.WHISPER

        record = CostRecord(
            session_id=session_id,
            provider=Provider.ASSEMBLYAI,
            operation=operation,
            quantity=audio_minutes,
            unit="minutes",
            cost_usd=cost,
            user_id=user_id,
            metadata={
                "with_diarization": with_diarization,
                "audio_seconds": audio_minutes * 60
            }
        )

        await self._add_record(record)
        return record

    async def record_translation_call(
        self,
        session_id: str,
        character_count: int
    ) -> CostRecord:
        """
        Record a translation API call.

        Note: Using deep-translator with Google Translate is FREE.

        Args:
            session_id: Session identifier
            character_count: Number of characters translated

        Returns:
            CostRecord for this call
        """
        record = CostRecord(
            session_id=session_id,
            provider=Provider.GOOGLE,
            operation=Operation.TRANSLATION,
            quantity=character_count,
            unit="characters",
            cost_usd=0.0,  # Free via deep-translator
            metadata={"note": "Free via deep-translator library"}
        )

        await self._add_record(record)
        return record

    async def get_session_cost(self, session_id: str) -> SessionCostSummary:
        """
        Get cost summary for a session.

        Args:
            session_id: Session identifier

        Returns:
            SessionCostSummary with breakdown
        """
        async with self._lock:
            records = self._session_costs.get(session_id, [])

        # Calculate breakdown by operation
        breakdown: Dict[str, float] = {}
        provider_breakdown: Dict[str, float] = {}
        total_cost = 0.0

        for record in records:
            op_key = record.operation.value
            breakdown[op_key] = breakdown.get(op_key, 0) + record.cost_usd

            prov_key = record.provider.value
            provider_breakdown[prov_key] = provider_breakdown.get(prov_key, 0) + record.cost_usd

            total_cost += record.cost_usd

        # Check budget
        budget = self._session_budgets.get(session_id)
        budget_remaining = budget - total_cost if budget else None
        is_over_budget = budget_remaining < 0 if budget_remaining is not None else False

        return SessionCostSummary(
            session_id=session_id,
            total_cost_usd=total_cost,
            breakdown=breakdown,
            provider_breakdown=provider_breakdown,
            records=records,
            budget_limit=budget,
            budget_remaining=budget_remaining,
            is_over_budget=is_over_budget
        )

    async def check_budget(
        self,
        session_id: str,
        budget_limit: float
    ) -> bool:
        """
        Check if session is within budget.

        Args:
            session_id: Session identifier
            budget_limit: Maximum allowed cost in USD

        Returns:
            True if within budget, False if over
        """
        # Store budget limit for future checks
        self._session_budgets[session_id] = budget_limit

        summary = await self.get_session_cost(session_id)
        return not summary.is_over_budget

    async def set_budget(self, session_id: str, budget_limit: float):
        """
        Set budget limit for a session.

        Args:
            session_id: Session identifier
            budget_limit: Maximum allowed cost in USD
        """
        self._session_budgets[session_id] = budget_limit

    async def get_total_cost(self) -> float:
        """Get total cost across all sessions."""
        total = 0.0
        async with self._lock:
            for records in self._session_costs.values():
                total += sum(r.cost_usd for r in records)
        return total

    async def get_cost_by_provider(self) -> Dict[str, float]:
        """Get total cost breakdown by provider."""
        breakdown: Dict[str, float] = {}
        async with self._lock:
            for records in self._session_costs.values():
                for record in records:
                    key = record.provider.value
                    breakdown[key] = breakdown.get(key, 0) + record.cost_usd
        return breakdown

    async def clear_session(self, session_id: str):
        """Clear cost records for a session."""
        async with self._lock:
            if session_id in self._session_costs:
                del self._session_costs[session_id]
            if session_id in self._session_budgets:
                del self._session_budgets[session_id]

    async def _add_record(self, record: CostRecord):
        """Add a cost record — in-memory + Supabase (best-effort)."""
        async with self._lock:
            if record.session_id not in self._session_costs:
                self._session_costs[record.session_id] = []
            self._session_costs[record.session_id].append(record)

        # Persist to Supabase (non-blocking, best-effort)
        if self._supabase:
            try:
                self._supabase.table("api_costs").insert({
                    "session_id": record.session_id,
                    "user_id": record.user_id,
                    "provider": record.provider.value,
                    "operation": record.operation.value,
                    "quantity": record.quantity,
                    "unit": record.unit,
                    "cost_usd": record.cost_usd,
                    "metadata": record.metadata
                }).execute()
            except Exception as e:
                print(f"[CostTracker] Supabase persist failed (non-fatal): {e}")


# Global instance
_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get or create the global cost tracker instance."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker


# Convenience functions
async def record_whisper_cost(session_id: str, audio_minutes: float, user_id: str = "") -> CostRecord:
    """Record Whisper API cost."""
    return await get_cost_tracker().record_whisper_call(session_id, audio_minutes, user_id=user_id)


async def record_gpt4_cost(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    user_id: str = ""
) -> CostRecord:
    """Record GPT-4 API cost."""
    return await get_cost_tracker().record_gpt4_call(session_id, input_tokens, output_tokens, user_id=user_id)


async def record_assemblyai_cost(
    session_id: str,
    audio_minutes: float,
    with_diarization: bool = True,
    user_id: str = ""
) -> CostRecord:
    """Record AssemblyAI API cost."""
    return await get_cost_tracker().record_assemblyai_call(
        session_id, audio_minutes, with_diarization=with_diarization, user_id=user_id
    )


async def get_session_cost_summary(session_id: str) -> SessionCostSummary:
    """Get cost summary for a session."""
    return await get_cost_tracker().get_session_cost(session_id)
