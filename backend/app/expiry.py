"""Shared expiry / traffic-light logic for tracked documents.

Kept in its own module so the API router (routers/documents.py) and the reminder
engine (reminders.py) compute status identically — one source of truth."""
from datetime import date, datetime
from typing import Optional

# Days remaining until end_date:
#   > YELLOW_DAYS       -> green
#   RED_DAYS+1..YELLOW  -> yellow  (within two weeks)
#   0..RED_DAYS         -> red     (within one week)
#   past end_date       -> expired
RED_DAYS = 7
YELLOW_DAYS = 14

# Statuses that need a human to act (green = fine, unknown = unparseable date).
ATTENTION_STATUSES = ("expired", "red", "yellow")


def today() -> date:
    return datetime.now().date()


def compute_status(end_date: str, ref: Optional[date] = None) -> dict:
    """Traffic-light status + signed days remaining, derived from end_date."""
    ref = ref or today()
    try:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"status": "unknown", "days_left": None}
    days = (end - ref).days
    if days < 0:
        status = "expired"
    elif days <= RED_DAYS:
        status = "red"
    elif days <= YELLOW_DAYS:
        status = "yellow"
    else:
        status = "green"
    return {"status": status, "days_left": days}
