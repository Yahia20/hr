"""Per-category expiry thresholds (how many days out a document turns yellow /
red). Defaults match the original two-weeks / one-week rule for every category;
operators can widen them per category (e.g. warn 60/30 days ahead for iqamas,
which take longer to renew) from Settings — stored as JSON in app_settings, so
no redeploy is needed."""
import json
import logging

from .db import db
from .expiry import RED_DAYS, YELLOW_DAYS

logger = logging.getLogger("hr.doc_config")

CATEGORIES = ("iqama", "contract", "rent", "vehicle", "license")
K_THRESHOLDS = "doc_thresholds"

# SQL predicate for alert eligibility (dashboard badges + reminder digest): a
# document counts unless it's an employee document (iqama/contract) whose owner
# is no longer on the roster. Those orphans aren't shown on any page after the
# employee is deleted, so they must not keep inflating the counters or emails.
# The documents themselves are kept — this only affects the alert surfaces.
ALERT_ELIGIBLE_SQL = (
    "(category NOT IN ('iqama', 'contract') OR owner IN (SELECT name FROM employees))"
)

DEFAULT_THRESHOLDS = {c: {"yellow": YELLOW_DAYS, "red": RED_DAYS} for c in CATEGORIES}


def _defaults() -> dict:
    return {c: dict(DEFAULT_THRESHOLDS[c]) for c in CATEGORIES}


def load_thresholds(conn) -> dict:
    """Full {category: {yellow, red}} map: defaults with any stored overrides."""
    merged = _defaults()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (K_THRESHOLDS,)).fetchone()
    if row and row["value"]:
        try:
            overrides = json.loads(row["value"])
        except (ValueError, TypeError):
            logger.warning("Ignoring malformed %s setting", K_THRESHOLDS)
            overrides = {}
        for cat, v in (overrides or {}).items():
            if cat in merged and isinstance(v, dict):
                for key in ("yellow", "red"):
                    if key in v:
                        try:
                            merged[cat][key] = max(0, int(v[key]))
                        except (ValueError, TypeError):
                            pass
    # Keep red <= yellow so the bands can't invert.
    for cat in merged:
        merged[cat]["red"] = min(merged[cat]["red"], merged[cat]["yellow"])
    return merged


def thresholds_for(category: str, tmap: dict) -> tuple[int, int]:
    """(yellow_days, red_days) for a category, falling back to defaults."""
    t = tmap.get(category) or DEFAULT_THRESHOLDS.get(category) or {"yellow": YELLOW_DAYS, "red": RED_DAYS}
    return int(t["yellow"]), int(t["red"])


def save_thresholds(mapping: dict) -> dict:
    """Validate + persist the per-category thresholds, returning the stored map."""
    clean = _defaults()
    for cat in CATEGORIES:
        v = (mapping or {}).get(cat) or {}
        try:
            yellow = max(0, int(v.get("yellow", clean[cat]["yellow"])))
        except (ValueError, TypeError):
            yellow = clean[cat]["yellow"]
        try:
            red = max(0, int(v.get("red", clean[cat]["red"])))
        except (ValueError, TypeError):
            red = clean[cat]["red"]
        clean[cat] = {"yellow": yellow, "red": min(red, yellow)}
    with db() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (K_THRESHOLDS, json.dumps(clean)),
        )
    return clean


def get_thresholds() -> dict:
    with db() as conn:
        return load_thresholds(conn)
