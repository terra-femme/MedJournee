# routes/costs.py
"""Cost tracking API routes — query API usage and costs per user."""

from fastapi import APIRouter
from typing import Optional
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()


def _get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    return create_client(url, key)


@router.get("/summary/{user_id}")
async def get_cost_summary(user_id: str):
    """
    Total cost breakdown for a user — all time and this month.
    Returns: total_usd, by_provider, by_operation, session_count, this_month_usd
    """
    try:
        sb = _get_supabase()

        # All-time records
        all_records = sb.table("api_costs") \
            .select("provider, operation, cost_usd, recorded_at, session_id") \
            .eq("user_id", user_id) \
            .order("recorded_at", desc=True) \
            .execute()

        rows = all_records.data or []

        # Aggregate
        total_usd = sum(r["cost_usd"] for r in rows)
        by_provider: dict = {}
        by_operation: dict = {}
        session_ids = set()

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        this_month_usd = 0.0

        for r in rows:
            p = r["provider"]
            o = r["operation"]
            c = r["cost_usd"]
            by_provider[p] = round(by_provider.get(p, 0) + c, 6)
            by_operation[o] = round(by_operation.get(o, 0) + c, 6)
            session_ids.add(r["session_id"])
            # Check if this month
            try:
                recorded = datetime.fromisoformat(r["recorded_at"].replace("Z", "+00:00"))
                if recorded.year == now.year and recorded.month == now.month:
                    this_month_usd += c
            except Exception:
                pass

        return {
            "success": True,
            "user_id": user_id,
            "total_usd": round(total_usd, 6),
            "this_month_usd": round(this_month_usd, 6),
            "session_count": len(session_ids),
            "by_provider": by_provider,
            "by_operation": by_operation,
            "pricing": {
                "openai_whisper_per_minute": 0.006,
                "openai_gpt4_input_per_1k_tokens": 0.03,
                "openai_gpt4_output_per_1k_tokens": 0.06,
                "assemblyai_diarization_per_minute": 0.12,
                "google_translate": 0.0
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/history/{user_id}")
async def get_cost_history(user_id: str, limit: int = 30):
    """
    Per-session cost history — last N sessions, ordered by date.
    Each session shows date, total cost, and per-provider breakdown.
    """
    try:
        sb = _get_supabase()
        rows = sb.table("api_costs") \
            .select("session_id, provider, operation, cost_usd, quantity, unit, recorded_at") \
            .eq("user_id", user_id) \
            .order("recorded_at", desc=True) \
            .limit(limit * 20) \
            .execute().data or []

        # Group by session_id
        sessions: dict = {}
        for r in rows:
            sid = r["session_id"]
            if sid not in sessions:
                sessions[sid] = {
                    "session_id": sid,
                    "date": r["recorded_at"][:10],
                    "total_usd": 0.0,
                    "by_provider": {},
                    "calls": []
                }
            sessions[sid]["total_usd"] += r["cost_usd"]
            p = r["provider"]
            sessions[sid]["by_provider"][p] = round(
                sessions[sid]["by_provider"].get(p, 0) + r["cost_usd"], 6
            )
            sessions[sid]["calls"].append({
                "operation": r["operation"],
                "quantity": r["quantity"],
                "unit": r["unit"],
                "cost_usd": r["cost_usd"]
            })

        session_list = sorted(
            sessions.values(),
            key=lambda s: s["date"],
            reverse=True
        )[:limit]

        for s in session_list:
            s["total_usd"] = round(s["total_usd"], 6)

        return {"success": True, "sessions": session_list}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/daily/{user_id}")
async def get_daily_costs(user_id: str, days: int = 30):
    """
    Daily cost totals for the last N days — for the bar chart.
    Returns array of { date, total_usd } objects.
    """
    try:
        from datetime import datetime, timedelta, timezone
        sb = _get_supabase()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        rows = sb.table("api_costs") \
            .select("cost_usd, recorded_at") \
            .eq("user_id", user_id) \
            .gte("recorded_at", since) \
            .order("recorded_at") \
            .execute().data or []

        daily: dict = {}
        for r in rows:
            date = r["recorded_at"][:10]
            daily[date] = round(daily.get(date, 0) + r["cost_usd"], 6)

        # Fill in zero-cost days
        result = []
        today = datetime.now(timezone.utc).date()
        for i in range(days):
            d = str(today - timedelta(days=days - 1 - i))
            result.append({"date": d, "total_usd": daily.get(d, 0)})

        return {"success": True, "daily": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
