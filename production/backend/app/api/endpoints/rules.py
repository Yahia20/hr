from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
from ...db.session import get_db
from ...models.rule import Rule
from ...schemas.rule import RuleCreate, RuleResponse
from ...api.deps import get_current_user

router = APIRouter()


@router.get("/")
def get_all_rules(db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    rules = db.query(Rule).all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "incident": r.incident,
            "reset_days": r.reset_days,
            "escalation": json.loads(r.escalation_json),
        }
        for r in rules
    ]


@router.put("/{rule_id}")
def update_rule(
    rule_id: int,
    rule: RuleCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    db_rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db_rule.reset_days = rule.reset_days
    db_rule.escalation_json = json.dumps(rule.escalation)
    db.commit()
    db.refresh(db_rule)
    return {"id": db_rule.id, "message": "Rule updated"}


@router.post("/")
def create_rule(rule: RuleCreate, db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    db_rule = Rule(
        category=rule.category,
        incident=rule.incident,
        description=rule.description,
        hr_note=rule.hr_note,
        reset_days=rule.reset_days,
        escalation_json=json.dumps(rule.escalation),
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return {"id": db_rule.id, "message": "Rule created"}
