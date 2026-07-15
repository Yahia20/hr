# HR Disciplinary System — Travel Gate KSA

## What this is
An HR disciplinary management system for Travel Gate KSA. It tracks employee violations, auto-calculates escalating penalties using a rules matrix, deducts days, freezes promotions, and generates reports.

## Tech stack
- **Backend**: FastAPI, Python — raw `sqlite3` (no ORM) via a `db()` context manager
- **Frontend**: React + Vite single-page app, bilingual (English/Arabic)
- **Database**: SQLite (`hr_system.db`); path overridable via `HR_DB_FILE` env var (point at a mounted volume in production)
- **Deployment**: Docker → **Railway** (see the "Production deployment" section below and `backend/.env.example`).
- **Repo**: https://github.com/Yahia20/hr

## Project structure
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app assembly: CORS, lifespan, router mounting
│   ├── auth.py              # sessions, bcrypt, CSRF, roles, lockout
│   ├── emailer.py           # SMTP helper (password-reset mail)
│   ├── db.py                # SQLAlchemy engine/session, init_db()
│   ├── schemas.py           # Pydantic request/response models
│   ├── penalties.py         # penalty/escalation engine
│   └── routers/            # API routes split by domain
│       ├── auth.py          # login/logout/me, forgot/reset, user management
│       ├── permissions.py   # early-leave permissions (استئذان) + attachments
│       ├── documents.py     # expiry-tracked documents (iqama/contract/rent/vehicle/license)
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
- `GET /api/violations/{vid}/proof` — fetch a violation's base64 proof image on demand (HR staff; the Reports table shows it in a modal and the PDF export embeds it under each row)
- `GET /api/violations/preview`, `GET /api/violations/export` — report preview and export
- `GET/POST /api/employees`, `DELETE /api/employees/{name}` — list / add / delete
- `GET /api/stats/dashboard` — dashboard aggregates
- `GET /api/matrix` — rules matrix and penalty map (served from `penalties.py` in memory, not the DB)
- `POST /api/auth/login|logout`, `GET /api/auth/me`, `POST /api/auth/forgot|reset` — cookie-session auth
- `GET/POST /api/auth/users`, `DELETE /api/auth/users/{id}` — user management (HR Manager only)
- `GET/POST /api/permissions`, `DELETE /api/permissions/{id}`, `GET /api/permissions/{id}/attachment` — early-leave permissions (استئذان): per-employee monthly quota (default 2, `PERMISSION_MONTHLY_QUOTA`); list/create for HR staff, delete + attachment view for HR Manager only
- `GET/POST /api/documents`, `PATCH/DELETE /api/documents/{id}`, `GET /api/documents/{id}/attachment`, `GET /api/documents/expiring` — expiry-tracked documents. `/expiring` returns everything that's yellow/red/expired (most urgent first) with counts + per-scope totals; it powers the dashboard "documents needing attention" widget and the red sidebar badges on the two document nav pages. One generic model backs five categories (`iqama`, `contract`, `rent`, `vehicle`, `license`), each with a start/end date + optional base64 attachment. The traffic-light `status` (green / yellow / red / expired) and `days_left` are computed from `end_date` at read time in `documents.py` (thresholds: ≤7 days red, ≤14 yellow, else green). `iqama`/`contract`/`rent` are one-per-owner "slots" (a partial unique index on `(owner, category)`; renew via PATCH, duplicate POST → 409 `slot_exists`); `vehicle`/`license` are open lists. List/create/renew for HR staff; delete + attachment view for HR Manager only. Frontend: two nav pages — **Employee Documents** (per-employee iqama + contract) and **Company Documents** (rents / vehicles / licenses tabs).
- Auth is an httpOnly `hr_session` cookie + `X-CSRF-Token` header on mutations (double-submit `hr_csrf` cookie). Every endpoint declares role requirements via `require_user`/`require_role` from `auth.py`; `/health` and the login/forgot/reset endpoints are the only unguarded ones.
- Roles: `hr_manager` (everything), `hr_officer` (log/manage, no deletes or user admin), `dept_head` (read-only, own department), `employee` (own violations only)

## Database tables
`init_db()` in `db.py` creates seven tables:
- `employees` — name (unique), email, department, manager_email
- `violations` — employee_name, category, incident, penalty_color, penalty_label, deduction_hours, deduction_days, freeze_months, comment, submitted_by, proof_image (base64), created_at
- `users` — email (unique), name, role (hr_manager/hr_officer/dept_head/employee), department, bcrypt password_hash, is_active, lockout columns
- `sessions` — SHA-256 of the session cookie token, user_id, csrf_token, expires_at
- `password_resets` — SHA-256 of the reset token, user_id, expires_at, used
- `permissions` — early-leave permissions (استئذان): employee_name, permission_date, month_key (drives the monthly quota), note, attachment (base64, HR-manager only), created_by, created_at
- `documents` — expiry-tracked paperwork: category (iqama/contract/rent/vehicle/license), owner (employee name or asset key), title, start_date, end_date, note, attachment (base64, HR-manager only), created_by, created_at. Partial unique index on `(owner, category)` for the slot categories (iqama/contract/rent); status/days_left are derived from end_date, not stored

The attendance feature (clock in/out, geofencing, office networks, WebAuthn fingerprints) was removed; `init_db()` drops its old tables (`attendance`, `office_locations`, `office_networks`, `webauthn_credentials`, `webauthn_challenges`) from existing databases.

There is no `rules` table: the rules matrix lives in `penalties.py`. The first HR Manager account is seeded from `HR_BOOTSTRAP_ADMIN_EMAIL` / `HR_BOOTSTRAP_ADMIN_PASSWORD` when the `users` table is empty. Failed logins are rate-limited per IP and per account (5 per 15 min each). Other env vars: `COOKIE_SECURE` (set `true` in prod), `APP_BASE_URL` (reset links), `SMTP_HOST/PORT/USER/PASSWORD/FROM`, `CORS_ORIGINS`, `HR_DB_FILE`, `PERMISSION_MONTHLY_QUOTA` (default `2`).

## Production deployment (Railway, Docker)
The `Dockerfile` builds the SPA and serves it from the FastAPI app (same origin). `railway.json` sets the healthcheck to `/health`. Full env reference is in `backend/.env.example`. Checklist before going live:
1. **Mount a Volume** and set `HR_DB_FILE` to a path on it (e.g. `/data/hr_system.db`) — SQLite otherwise lives in the ephemeral container and is wiped on every redeploy. `db.py` creates the parent dir automatically.
2. Set `COOKIE_SECURE=true`, `APP_BASE_URL=https://<host>` (drives reset links), and `HR_BOOTSTRAP_ADMIN_EMAIL` / `HR_BOOTSTRAP_ADMIN_PASSWORD`.
3. The container runs uvicorn with `--proxy-headers --forwarded-allow-ips='*'` so `request.client.host` is the real client IP behind Railway's edge (correct per-IP login lockout and HTTPS/HSTS detection). Without it, all clients share the proxy IP and one burst of failed logins would lock everyone out.
4. On boot, `_check_production_config()` logs loud warnings for missing/weak prod config (insecure cookies, unset `APP_BASE_URL`/`HR_DB_FILE`). These are warnings, not hard failures.

Not yet hardened (recommendations, low priority): container runs as root (non-root user deferred due to Railway volume-permission interaction); backend deps use `>=` ranges rather than pinned versions; the repo root still holds legacy files (`main.py`, `production/`, `*.xlsx`, `HR_Report.html`) that are excluded from the image via `.dockerignore`.

## Known issues (being fixed)
- [x] CORS wildcard `*` — now locked to an allow-list via `CORS_ORIGINS` env var
- [x] No auth guards on API routes — all `/api` routers now require `require_admin`
- [x] Default `admin123` password — auth now fails closed; bcrypt hash supported; per-IP login lockout (see `SECURITY_AUDIT.md`)
- [x] Hardcoded user "Amin" in frontend — real login flow with per-user accounts, roles, cookie sessions (Phase 2)
- [ ] Proof images stored as base64 in DB — should use file storage
- [ ] Design System page visible in production nav — should be hidden
- [ ] Settings page is a stub — implement or remove

## Commands
```bash
# Run backend locally
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Backend tests (pytest)
cd backend
pip install -r requirements-dev.txt
python -m pytest -q

# Docker
docker-compose up --build
```

## Conventions
- Backend uses raw `sqlite3` (no ORM); open connections via the `db()` context manager in `db.py`, which commits/rolls back automatically
- Penalty calculation logic and the rules matrix live in `penalties.py`
- Frontend is a React + Vite app (has a build step)
- All API responses are JSON
- Arabic/English toggle is client-side only
