"""
API cost logging and budget tracking for Startup Brain.
Logs calls to MongoDB cost_log collection.
"""

from datetime import datetime, timezone
from typing import Optional

# Anthropic pricing per million tokens (as of 2025)
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},  # $3/MTok in, $15/MTok out
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},    # $15/MTok in, $75/MTok out
}

# Fallback pricing for unknown models
DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


def _calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate cost in dollars for a given API call."""
    pricing = PRICING.get(model, DEFAULT_PRICING)
    cost_in = (tokens_in / 1_000_000) * pricing["input"]
    cost_out = (tokens_out / 1_000_000) * pricing["output"]
    return cost_in + cost_out


def log_api_call(model: str, tokens_in: int, tokens_out: int, task_type: str) -> Optional[str]:
    """
    Calculate cost and store in MongoDB cost_log collection.
    Returns inserted document id, or None if MongoDB unavailable.
    """
    from services.mongo_client import log_cost

    cost = _calculate_cost(model, tokens_in, tokens_out)
    doc = {
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "task_type": task_type,
        "timestamp": datetime.now(timezone.utc),
    }
    return log_cost(doc)


def get_monthly_cost(year: Optional[int] = None, month: Optional[int] = None) -> float:
    """
    Aggregate total cost from MongoDB for the specified month.
    Defaults to the current month.
    Returns cost in dollars.
    """
    from services.mongo_client import get_db

    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    db = get_db()
    if db is None:
        return 0.0

    try:
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        # Compute first day of next month
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        pipeline = [
            {"$match": {"created_at": {"$gte": start, "$lt": end}}},
            {"$group": {"_id": None, "total": {"$sum": "$cost_usd"}}},
        ]
        result = list(db["cost_log"].aggregate(pipeline))
        return result[0]["total"] if result else 0.0
    except Exception:
        return 0.0


def get_daily_breakdown(year: Optional[int] = None, month: Optional[int] = None) -> dict:
    """
    Returns dict of {date_str: cost_usd} for the specified month.
    Defaults to the current month.
    """
    from services.mongo_client import get_db

    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month

    db = get_db()
    if db is None:
        return {}

    try:
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        pipeline = [
            {"$match": {"created_at": {"$gte": start, "$lt": end}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                    },
                    "total": {"$sum": "$cost_usd"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        result = list(db["cost_log"].aggregate(pipeline))
        return {row["_id"]: round(row["total"], 4) for row in result}
    except Exception:
        return {}


def is_over_budget(threshold: float = 300.0) -> bool:
    """Returns True if this month's API cost exceeds the threshold (dollars)."""
    return get_monthly_cost() > threshold


def get_cost_summary() -> str:
    """
    Returns a formatted string for sidebar display.
    Example: "This month: $12.34 / $300 budget"
    """
    monthly = get_monthly_cost()
    status = "over budget" if monthly > 300.0 else "on track"
    return f"This month: ${monthly:.2f} / $300 budget ({status})"
