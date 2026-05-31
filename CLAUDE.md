# HR Disciplinary System — Travel Gate KSA

## What this is
An HR disciplinary management system for Travel Gate KSA. It tracks employee violations, auto-calculates escalating penalties using a rules matrix, deducts days, freezes promotions, and generates reports.

## Tech stack
- **Backend**: FastAPI + SQLite (`hr_system.db`), Python
- **Frontend**: Single HTML file (~2410 lines), bilingual (English/Arabic)
- **Database**: SQLite (PostgreSQL-ready via `DATABASE_URL` env var)
- **Deployment**: Google Cloud Run, Docker
- **Repo**: https://github.com/Yahia20/hr
- **Live URL**: https://hr-frontend-618314275727.europe-west1.run.app/

## Project structure
```
production/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py          # FastAPI app, all API routes, lifespan startup
│   ├── backend/              # DB models, penalty engine
│   ├── tests/
│   ├── .env
│   ├── Dockerfile
│   ├── hr_system.db          # SQLite database
│   └── requirements.txt
├── docker/
└── frontend/                 # Single HTML file with CSS/JS
```

## Key business logic
- **17 incident types** across categories (Attendance, Conduct, Safety, etc.)
- **5 penalty levels**: Yellow → Orange → Red → Black → Investigation
- **Escalation engine**: repeat violations within a 30-day reset window escalate to the next penalty level (max 6 steps)
- **Penalties include**: warnings, day deductions, promotion freezes
- **Email notifications**: sent when violations are logged

## API structure
- `POST /api/violations` — log a new violation (auto-calculates penalty)
- `GET /api/violations` — list all violations
- `GET /api/employees` — list employees
- `POST /api/employees` — add employee
- `GET /api/rules` — get the rules matrix (seeded from penalty.py on startup)
- Auth routes exist but are not yet enforced on data endpoints

## Database tables
- `employees` — name, email, department, manager_email
- `violations` — employee_id, incident_type, category, penalty_level, deduction_days, comments, proof (base64), timestamps
- `rules` — category, incident_type, escalation ladder
- `users` — auth table (exists but not enforced)

## Known issues (being fixed)
- [ ] CORS wildcard `*` — should be locked to frontend URL
- [ ] No auth guards on API routes — anyone with the URL can read/write data
- [ ] Hardcoded user "Amin" in frontend — no real login flow
- [ ] Proof images stored as base64 in DB — should use file storage
- [ ] Design System page visible in production nav — should be hidden
- [ ] Settings page is a stub — implement or remove

## Commands
```bash
# Run backend locally
cd production/backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Docker
docker-compose up --build
```

## Conventions
- Backend uses SQLAlchemy ORM with declarative base from `db/base.py`
- Penalty calculation logic lives in `penalty.py`
- Frontend is vanilla JS — no framework, no build step
- All API responses are JSON
- Arabic/English toggle is client-side only
