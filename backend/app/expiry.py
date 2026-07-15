"""Shared expiry / traffic-light logic for tracked documents.

Kept in its own module so the API router (routers/documents.py) and the reminder
engine (reminders.py) compute status identically — one source of truth."""
from datetime import date, datetime
from typing import Optional

# Default thresholds (days remaining until end_date):
#   > yellow_days           -> green
#   red_days+1..yellow_days -> yellow  (within two weeks by default)
#   0..red_days             -> red     (within one week by default)
#   past end_date           -> expired
# Per-category overrides live in doc_config.py (editable in Settings).
YELLOW_DAYS = 14
RED_DAYS = 7

# Statuses that need a human to act (green = fine, unknown = unparseable date).
ATTENTION_STATUSES = ("expired", "red", "yellow")


def today() -> date:
    return datetime.now().date()


def compute_status(
    end_date: str,
    yellow_days: int = YELLOW_DAYS,
    red_days: int = RED_DAYS,
    ref: Optional[date] = None,
) -> dict:
    """Traffic-light status + signed days remaining, derived from end_date and the
    (optionally per-category) yellow/red thresholds."""
    ref = ref or today()
    try:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"status": "unknown", "days_left": None}
    days = (end - ref).days
    if days < 0:
        status = "expired"
    elif days <= red_days:
        status = "red"
    elif days <= yellow_days:
        status = "yellow"
    else:
        status = "green"
    return {"status": status, "days_left": days}
