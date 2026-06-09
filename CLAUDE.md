# HR Disciplinary System — Travel Gate KSA

## What this is
An HR disciplinary management system for Travel Gate KSA. It tracks employee violations, auto-calculates escalating penalties using a rules matrix, deducts days, freezes promotions, and generates reports.

## Tech stack
- **Backend**: FastAPI, Python — raw `sqlite3` (no ORM) via a `db()` context manager
- **Frontend**: React + Vite single-page app, bilingual (English/Arabic)
- **Database**: SQLite (`hr_system.db`); path overridable via `HR_DB_FILE` env var
- **Deployment**: Docker; target host is **Railway** (see `HANDOVER.md` § F). Not currently deployed.
- **Repo**: https://github.com/Yahia20/hr

## Project structure
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app assembly: CORS, lifespan, router mounting
│   ├── auth.py              # require_admin dependency (HTTP Basic)
│   ├── db.py                # SQLAlchemy engine/session, init_db()
│   ├── schemas.py           # Pydantic request/response models
│   ├── penalties.py         # penalty/escalation engine
│   └── routers/            # API routes split by domain
│       ├── employees.py
│       ├── violations.py
│       ├── stats.py
│       └── matrix.py
├── .env
├── Dockerfile
├── hr_system.db             # SQLite database
└── requirements.txt
frontend/                    # React + Vite single-page app
```
(A legacy `production/` tree with the older single-file frontend and a monolithic
`main.py` still exists in the repo but is superseded by the layout above.)

## Key business logic
- **17 incident types** across categories (Attendance, Conduct, Safety, etc.)
- **5 penalty levels**: Yellow → Orange → Red → Black → Investigation
- **Escalation engine**: repeat violations within a 30-day reset window escalate to the next penalty level (max 6 steps)
- **Penalties include**: warnings, day deductions, promotion freezes
- **Email notifications**: sent when violations are logged

## API structure
Routes are split into routers under `app/routers/`, all mounted at the `/api` prefix:
- `GET/POST /api/violations`, `DELETE /api/violations/{vid}` — list / log (auto-calculates penalty) / delete
- `GET /api/violations/{vid}/proof` — fetch a violation's base64 proof image on demand
- `GET /api/violations/preview`, `GET /api/violations/export` — report preview and export
- `GET/POST /api/employees`, `DELETE /api/employees/{name}` — list / add / delete
- `GET /api/stats/dashboard` — dashboard aggregates
- `GET /api/matrix` — rules matrix and penalty map (served from `penalties.py` in memory, not the DB)
- All `/api` routers are mounted behind `require_admin` (HTTP Basic); `/health` and `/api/auth/check` are the only unguarded endpoints

## Database tables
`init_db()` in `db.py` creates exactly two tables:
- `employees` — name (unique), email, department, manager_email
- `violations` — employee_name, category, incident, penalty_color, penalty_label, deduction_hours, deduction_days, freeze_months, comment, submitted_by, proof_image (base64), created_at

There is no `rules` or `users` table: the rules matrix lives in `penalties.py`, and admin auth is a single env-configured credential checked in `auth.py` (`HR_ADMIN_USERNAME` plus either `HR_ADMIN_PASSWORD_HASH` (bcrypt, preferred) or a strong `HR_ADMIN_PASSWORD`). There is **no default password**: if neither is set (or the password is a known default like `admin123`), the API fails closed with 503. Failed logins are rate-limited per IP (5 per 15 min).

## Known issues (being fixed)
- [x] CORS wildcard `*` — now locked to an allow-list via `CORS_ORIGINS` env var
- [x] No auth guards on API routes — all `/api` routers now require `require_admin`
- [x] Default `admin123` password — auth now fails closed; bcrypt hash supported; per-IP login lockout (see `SECURITY_AUDIT.md`)
- [ ] Hardcoded user "Amin" in frontend — no real login flow
- [ ] Proof images stored as base64 in DB — should use file storage
- [ ] Design System page visible in production nav — should be hidden
- [ ] Settings page is a stub — implement or remove

## Commands
```bash
# Run backend locally
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Docker
docker-compose up --build
```

## Conventions
- Backend uses raw `sqlite3` (no ORM); open connections via the `db()` context manager in `db.py`, which commits/rolls back automatically
- Penalty calculation logic and the rules matrix live in `penalties.py`
- Frontend is a React + Vite app (has a build step)
- All API responses are JSON
- Arabic/English toggle is client-side only
