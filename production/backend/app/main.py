from contextlib import asynccontextmanager
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db.session import engine, SessionLocal
from .db.base import Base
from .api.endpoints import auth, employees, violations, rules, settings, reports


# Mirrors RULES_MATRIX in utils/penalty.py plus the category grouping from the frontend.
# Kept here so startup seeding stays self-contained; penalty.py remains the authoritative
# runtime source for escalation logic.
_SETTINGS_SEED = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": "465",
    "smtp_user": "",
    "smtp_password": "",
    "notify_violation": "true",
    "notify_escalation": "true",
    "notify_freeze": "true",
}


def _seed_settings() -> None:
    from .models.setting import AppSetting
    db = SessionLocal()
    try:
        existing = {r.key for r in db.query(AppSetting.key).all()}
        for key, value in _SETTINGS_SEED.items():
            if key not in existing:
                db.add(AppSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()


_RULE_SEED = [
    ("Attendance",        "Late Arrival",     30,  ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]),
    ("Attendance",        "No-Show",          90,  ["Red", "Red", "Black", "Investigation"]),
    ("Attendance",        "Exceed Breaks",    30,  ["Yellow", "Yellow", "Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]),
    ("Attendance",        "Early Leave",      180, ["Black", "Investigation"]),
    ("Personal Attitude", "Abusive Words",    180, ["Black", "Investigation"]),
    ("Personal Attitude", "Physical Harm",    180, ["Investigation"]),
    ("Personal Attitude", "Sleeping on Job",  180, ["Black", "Investigation"]),
    ("Personal Attitude", "Unprofessional",   180, ["Black", "Investigation"]),
    ("Abusing",           "Company Assets",   180, ["Investigation"]),
    ("Abusing",           "Routing Calls",    180, ["Black", "Investigation"]),
    ("Abusing",           "Aux Abuse",        30,  ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"]),
    ("Policy Violations", "Mobile Phone",     30,  ["Red", "Black", "Investigation"]),
    ("Policy Violations", "Food & Beverage",  30,  ["Orange", "Red", "Black", "Investigation"]),
    ("Policy Violations", "Business Process", 30,  ["Orange", "Red", "Black", "Investigation"]),
    ("Policy Violations", "Cyber Security",   30,  ["Red", "Black", "Investigation"]),
    ("Policy Violations", "Harassment",       180, ["Investigation"]),
    ("Policy Violations", "Theft",            180, ["Investigation"]),
]


def _seed_rules() -> None:
    from .models.rule import Rule
    db = SessionLocal()
    try:
        existing = {row[0] for row in db.query(Rule.incident).all()}
        for category, incident, reset_days, esc in _RULE_SEED:
            if incident not in existing:
                db.add(Rule(
                    category=category,
                    incident=incident,
                    reset_days=reset_days,
                    escalation_json=json.dumps(esc),
                ))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _seed_rules()
    _seed_settings()
    yield


app = FastAPI(
    title="Travel Gate KSA HR Disciplinary System",
    version="2.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tg-hr-frontend.fly.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/api/auth",       tags=["auth"])
app.include_router(employees.router,  prefix="/api/employees",  tags=["employees"])
app.include_router(violations.router, prefix="/api/violations", tags=["violations"])
app.include_router(rules.router,      prefix="/api/rules",      tags=["rules"])
app.include_router(settings.router,   prefix="/api/settings",   tags=["settings"])
app.include_router(reports.router,    prefix="/api/reports",    tags=["reports"])


@app.get("/")
def root():
    return {"message": "✅ Travel Gate HR System API is Running!"}
