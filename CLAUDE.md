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
│       ├── attendance.py    # clock in/out, geofence offices, WebAuthn fingerprint
│       ├── permissions.py   # early-leave permissions (استئذان) + attachments
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
- `POST /api/auth/login|logout`, `GET /api/auth/me`, `POST /api/auth/forgot|reset` — cookie-session auth
- `GET/POST /api/auth/users`, `DELETE /api/auth/users/{id}` — user management (HR Manager only)
- `POST /api/attendance/clock-in|clock-out`, `GET /api/attendance/me` — GPS + fingerprint-verified attendance punches (any signed-in user)
- `GET /api/attendance`, `GET /api/attendance/export` — attendance log (role-scoped; list is paginated via `limit`/`offset` and returns `{rows, total, limit, offset}`) and Excel export (HR staff)
- `GET/POST /api/attendance/offices`, `DELETE /api/attendance/offices/{id}` — geofence office locations (read: HR staff, write: HR Manager)
- `GET/POST /api/attendance/networks`, `DELETE /api/attendance/networks/{id}`, `GET /api/attendance/my-ip` — office network IP/CIDR allow-list (Wi-Fi egress IP) for the advisory `off_network` flag; read + `my-ip`: HR staff, write: HR Manager
- `POST /api/attendance/webauthn/register/begin|complete`, `POST /api/attendance/webauthn/clock/begin`, `GET/DELETE /api/attendance/webauthn/credentials` — WebAuthn (device fingerprint) enrolment and clock assertions
- `GET/POST /api/permissions`, `DELETE /api/permissions/{id}`, `GET /api/permissions/{id}/attachment` — early-leave permissions (استئذان): per-employee monthly quota (default 2, `PERMISSION_MONTHLY_QUOTA`); list/create for HR staff, delete + attachment view for HR Manager only
- Auth is an httpOnly `hr_session` cookie + `X-CSRF-Token` header on mutations (double-submit `hr_csrf` cookie). Every endpoint declares role requirements via `require_user`/`require_role` from `auth.py`; `/health` and the login/forgot/reset endpoints are the only unguarded ones.
- Roles: `hr_manager` (everything), `hr_officer` (log/manage, no deletes or user admin), `dept_head` (read-only, own department), `employee` (own violations only)

## Database tables
`init_db()` in `db.py` creates eleven tables:
- `employees` — name (unique), email, department, manager_email
- `violations` — employee_name, category, incident, penalty_color, penalty_label, deduction_hours, deduction_days, freeze_months, comment, submitted_by, proof_image (base64), created_at
- `users` — email (unique), name, role (hr_manager/hr_officer/dept_head/employee), department, bcrypt password_hash, is_active, lockout columns
- `sessions` — SHA-256 of the session cookie token, user_id, csrf_token, expires_at
- `password_resets` — SHA-256 of the reset token, user_id, expires_at, used
- `attendance` — one row per user per work day: user_id, work_date, clock_in/out timestamps (UTC), GPS lat/lng/accuracy, matched office, distance, verified flags, request IP (in/out, audit-only), per-punch `edge` markers (punch only inside the fence via the accuracy slack), and per-punch `on_network` flags (whether the request IP fell inside a configured office network — NULL when none configured). List responses add an advisory `risk` field (spoof signals: unrealistic/coarse accuracy, missing accuracy, edge-of-fence, impossible travel, off-network) computed at read time; the IP, edge markers, `on_network`, and `risk` are HR-only (never returned to the employee's own view). The accuracy slack is capped tight (`MAX_ACCURACY_SLACK_M`), so it can't be abused to widen the geofence; punches that lean on it are flagged rather than silently accepted
- `office_locations` — geofence anchors (name, lat, lng, radius_m) that punches must fall inside
- `office_networks` — public IP / CIDR ranges the office network exits from (e.g. the office Wi-Fi's egress IP). A punch whose request IP falls outside every configured range is flagged `off_network` in `risk` (advisory — never blocks the punch). Browsers can't read the Wi-Fi SSID, so this egress-IP match is the in-browser way to tie a punch to the office network
- `webauthn_credentials` — per-user device fingerprint credentials (credential_id, public_key base64url, sign_count)
- `webauthn_challenges` — short-lived WebAuthn challenges (one per user per purpose)
- `permissions` — early-leave permissions (استئذان): employee_name, permission_date, month_key (drives the monthly quota), note, attachment (base64, HR-manager only), created_by, created_at

There is no `rules` table: the rules matrix lives in `penalties.py`. The first HR Manager account is seeded from `HR_BOOTSTRAP_ADMIN_EMAIL` / `HR_BOOTSTRAP_ADMIN_PASSWORD` when the `users` table is empty. Failed logins are rate-limited per IP and per account (5 per 15 min each). Other env vars: `COOKIE_SECURE` (set `true` in prod), `APP_BASE_URL` (reset links + WebAuthn origin/RP ID), `SMTP_HOST/PORT/USER/PASSWORD/FROM`, `CORS_ORIGINS`, `HR_DB_FILE`. Attendance env vars: `ATTENDANCE_REQUIRE_BIOMETRIC` / `ATTENDANCE_REQUIRE_GEOFENCE` (default `true`), `ATTENDANCE_TZ_OFFSET_MINUTES` (default `180`, KSA), `WEBAUTHN_RP_ID` (defaults to the `APP_BASE_URL` hostname), `ATTENDANCE_RETENTION_DAYS` (default `90`; raw GPS coordinates/accuracy and request IPs are scrubbed from attendance rows older than this — derived facts like office/distance/verified are kept — for PDPL data-minimisation; `0` disables). The purge runs at startup and opportunistically (throttled) on clock-in. WebAuthn and geolocation both require HTTPS (or localhost).

## Production deployment (Railway, Docker)
The `Dockerfile` builds the SPA and serves it from the FastAPI app (same origin). `railway.json` sets the healthcheck to `/health`. Full env reference is in `backend/.env.example`. Checklist before going live:
1. **Mount a Volume** and set `HR_DB_FILE` to a path on it (e.g. `/data/hr_system.db`) — SQLite otherwise lives in the ephemeral container and is wiped on every redeploy. `db.py` creates the parent dir automatically.
2. Set `COOKIE_SECURE=true`, `APP_BASE_URL=https://<host>` (drives WebAuthn RP ID + reset links), and `HR_BOOTSTRAP_ADMIN_EMAIL` / `HR_BOOTSTRAP_ADMIN_PASSWORD`.
3. The container runs uvicorn with `--proxy-headers --forwarded-allow-ips='*'` so `request.client.host` is the real client IP behind Railway's edge (correct per-IP login lockout, attendance IP audit, and HTTPS/HSTS detection). Without it, all clients share the proxy IP and one burst of failed logins would lock everyone out.
4. On boot, `_check_production_config()` logs loud warnings for missing/weak prod config (insecure cookies, unset `APP_BASE_URL`/`HR_DB_FILE`, biometric disabled). These are warnings, not hard failures.

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
