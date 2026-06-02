import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from ..models.violation import Violation

PENALTY_MAP = {
    "Yellow":        {"deduction_days": 0.0, "freeze_months": 0, "label": "Performance Notice"},
    "Orange":        {"deduction_days": 0.5, "freeze_months": 0, "label": "Performance Flag — 0.5 Day Deduction"},
    "Red":           {"deduction_days": 2.0, "freeze_months": 0, "label": "Performance Alert — 2 Days Deduction"},
    "Black":         {"deduction_days": 4.0, "freeze_months": 3, "label": "Performance Warning — 4 Days + 3 Month Freeze"},
    "Investigation": {"deduction_days": 0.0, "freeze_months": 0, "label": "Suspended — Investigation"},
}

# Fallback — used only when the rules table has no row for the given incident.
RULES_MATRIX = {
    "Late Arrival":    {"reset_days": 30,  "esc": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]},
    "No-Show":         {"reset_days": 90,  "esc": ["Red", "Red", "Black", "Investigation"]},
    "Exceed Breaks":   {"reset_days": 30,  "esc": ["Yellow", "Yellow", "Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]},
    "Early Leave":     {"reset_days": 180, "esc": ["Black", "Investigation"]},
    "Abusive Words":   {"reset_days": 180, "esc": ["Black", "Investigation"]},
    "Physical Harm":   {"reset_days": 180, "esc": ["Investigation"]},
    "Sleeping on Job": {"reset_days": 180, "esc": ["Black", "Investigation"]},
    "Unprofessional":  {"reset_days": 180, "esc": ["Black", "Investigation"]},
    "Company Assets":  {"reset_days": 180, "esc": ["Investigation"]},
    "Routing Calls":   {"reset_days": 180, "esc": ["Black", "Investigation"]},
    "Aux Abuse":       {"reset_days": 30,  "esc": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]},
    "Mobile Phone":    {"reset_days": 30,  "esc": ["Red", "Black", "Investigation"]},
    "Food & Beverage": {"reset_days": 30,  "esc": ["Orange", "Red", "Black", "Investigation"]},
    "Business Process":{"reset_days": 30,  "esc": ["Orange", "Red", "Black", "Investigation"]},
    "Cyber Security":  {"reset_days": 30,  "esc": ["Red", "Black", "Investigation"]},
    "Harassment":      {"reset_days": 180, "esc": ["Investigation"]},
    "Theft":           {"reset_days": 180, "esc": ["Investigation"]},
}


def calculate_next_penalty(db: Session, employee_name: str, category: str, incident: str) -> str:
    from ..models.rule import Rule

    # DB rule takes priority so Settings-page edits apply immediately.
    db_rule = db.query(Rule).filter(Rule.incident == incident).first()
    if db_rule:
        rule = {"reset_days": db_rule.reset_days, "esc": json.loads(db_rule.escalation_json)}
    else:
        rule = RULES_MATRIX.get(
            incident,
            {"reset_days": 30, "esc": ["Yellow", "Orange", "Red", "Black", "Investigation"]},
        )

    cutoff_date = datetime.utcnow() - timedelta(days=rule["reset_days"])
    past_count = (
        db.query(Violation)
        .filter(
            Violation.employee_name == employee_name,
            Violation.incident == incident,
            Violation.created_at >= cutoff_date,
        )
        .count()
    )

    esc_list = rule["esc"]
    if past_count >= len(esc_list):
        return esc_list[-1]
    return esc_list[past_count]


def build_penalty_label(penalty_color: str, applied_days: float) -> str:
    base = PENALTY_MAP.get(penalty_color, PENALTY_MAP["Yellow"])
    if applied_days != base["deduction_days"] and penalty_color != "Investigation":
        return f"{penalty_color} Card — {applied_days} Days Deduction (Override)"
    return base["label"]
