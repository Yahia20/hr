# Changelog

## Phase 1 — Security Audit & Hardening (2026-06-09)

Full findings, exploit scenarios, and severities: [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

### Backend
- **Auth fails closed** (`app/auth.py`): the default `admin123` fallback is gone. If neither `HR_ADMIN_PASSWORD_HASH` nor a strong `HR_ADMIN_PASSWORD` is set, all authenticated requests return 503. ⚠️ Breaking: every environment must now configure a real credential.
- **bcrypt password support** (`app/auth.py`): new `HR_ADMIN_PASSWORD_HASH` env var (takes precedence over plaintext `HR_ADMIN_PASSWORD`).
- **Brute-force lockout** (`app/auth.py`): 5 failed attempts per IP within 15 minutes → 429 for 15 minutes; failures are logged with username + source IP.
- **Non-ASCII login crash fixed** (`app/auth.py`): credentials are byte-encoded before constant-time comparison (was a 500 on e.g. Arabic input).
- **Security headers** (`app/main.py`): `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on `/api/*`, HSTS over HTTPS.
- **CORS tightened** (`app/main.py`): methods limited to GET/POST/DELETE, headers to `Authorization`/`Content-Type` (origins were already allow-listed).
- **Input validation** (`app/schemas.py`): `EmailStr` for employee email, length caps on all text fields, `override_days` bounded 0–365, `proof_image` capped at ~5 MB and validated as base64 server-side.
- **Excel formula injection neutralised** (`app/routers/violations.py`): free-text cells starting with `=`, `+`, `-`, `@`, tab, or CR are escaped in exports.
- **Date filters validated** (`app/routers/violations.py`): `date_from`/`date_to` must be `YYYY-MM-DD`, else 400.
- **No more raw DB errors to clients** (`app/routers/employees.py`): generic message returned, details logged server-side.
- **Dependencies** (`requirements.txt`): removed unused `psycopg2-binary` and `asyncpg`; added `bcrypt`, `email-validator`.

### Frontend
- **Credentials moved from `localStorage` to `sessionStorage`** (`src/api.js`) — interim until Phase 2's httpOnly-cookie sessions.
- **Login form** (`src/pages/Login.jsx`): no longer pre-fills the valid username; proper `autoComplete` attributes.
- **Vite 5 → 7** (+ `@vitejs/plugin-react` 5): clears the esbuild dev-server advisory (GHSA-67mh-4wv8-2f99); `npm audit` now clean; build verified.

### Deferred (tracked in SECURITY_AUDIT.md)
- Per-user accounts, RBAC, cookie sessions + CSRF → Phase 2 (F-2, F-6, F-21).
- Deletion of legacy `production/` tree and root `main.py` → awaiting approval (F-17).
- Rotation check on historically leaked Gmail app password (F-18).
- Self-hosted fonts (F-22) → Phase 3.
