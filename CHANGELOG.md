# Changelog

## Phase 4 — Code Quality (2026-06-09)

- **Branding**: official Travel Gate logo wired into the sidebar, login screen, and
  favicon (`frontend/public/logo.png`, `src/assets/logo.png`); page title updated.
- **Component splits — every source file is now ≤ 200 lines**:
  - `src/layout.jsx` — `Sidebar` + `Topbar` extracted from `App.jsx` (251 → 178).
  - `src/charts.jsx` — shared `BarList` + `PenaltyDist`, deduplicating near-identical
    chart code that existed in both Dashboard and Reports.
  - `src/authui.jsx` — `PasswordInput`, `AuthShell`, `AuthAlert` out of `Login.jsx` (201 → 141).
  - `src/pages/ViolationsTable.jsx` + `src/pages/EscalationAside.jsx` — out of
    Reports (265 → 199) and LogViolation (225 → 200).
- **Custom hooks**: `useFocusSearch` consolidates the duplicated "/"-shortcut listener
  (joins Phase 3's `useDebouncedValue`, `usePagination`, `useHotkeys`, `useMediaQuery`,
  `useLocalStorage`).
- **PropTypes** added to every shared component (`prop-types` dependency): buttons,
  Card/Empty/Skeleton/Pager/PenBadge/KpiCard, Modal/ConfirmModal, ToastProvider,
  layout, charts, and the extracted page components.
- **Error boundaries**: new `ErrorBoundary` class at the app root (`main.jsx`) and
  around each page (keyed by page id so navigating away resets a tripped boundary);
  bilingual fallback UI with a retry button.
- **Performance**: `React.memo` on `PenBadge` (rendered per table row), `KpiCard`,
  `BarList`, `PenaltyDist`, `Sidebar`, `Topbar`; `App.jsx` handlers wrapped in
  `useCallback` so the memoized layout actually skips re-renders; heavy list
  computations were already `useMemo`-ized in Phase 3.
- **Bug found & fixed during refactor QA**: `Reports.jsx` referenced the removed
  `PENALTIES` constant in the distribution chart — would have crashed the Reports page
  at runtime.

### Final QA (all phases)
67 automated checks, all passing:
- 21 backend business-logic checks (escalation sequence Y→Y→O→R→B→I, penalty preview,
  force-investigation, deduction override + bounds, proof-image roundtrip + base64
  validation, filters + date validation, Excel export, dashboard aggregates, employee
  upsert, CSRF-guarded deletes, cookie flags).
- 31 auth/RBAC checks (login/logout/me, lockout, CSRF, all four roles' permission
  matrix, department/self scoping, forgot/reset incl. single-use tokens and session
  revocation).
- 15 browser E2E checks via headless Chromium (manager: add employee → log violation →
  search → delete via confirm modal → create user → PDF export popup → logout;
  officer: no Users nav, no delete buttons, can export; invalid-login error;
  forgot-password generic message) — **zero console or page errors**.

## Next steps & remaining items
1. **Deploy**: set `HR_BOOTSTRAP_ADMIN_EMAIL/_PASSWORD`, `COOKIE_SECURE=true`,
   `CORS_ORIGINS`, `APP_BASE_URL`, and `SMTP_*` on Railway; mount a persistent volume
   for `HR_DB_FILE`.
2. **Rotate the historically committed Gmail app password** (audit F-18) — still pending.
3. **Delete the legacy `production/` tree and root `main.py`** (audit F-17) — awaiting approval.
4. Move proof images out of the DB into file/object storage (known issue).
5. Implement or remove the Settings page stub.
6. Optional 2FA (email or TOTP) on top of the Phase 2 auth module.
7. Self-service password change for logged-in users.
8. List virtualization if violation history grows past a few thousand rows.

## Phase 3 — UX Improvements (2026-06-09)

All frontend; verified in a real browser (login → dashboard → dark mode → shortcuts →
Arabic RTL → mobile viewport) with zero console errors.

- **Dark mode** (`src/theme.css`, `src/tokens.js`): every color now resolves through CSS
  variables; toggling sets `data-theme` on `<html>` and persists in `localStorage`.
  Penalty badges, charts, skeletons, and modals all have tuned dark variants.
- **Loading skeletons** (`Skeleton`, `SkeletonRows`, `KpiSkeleton` in
  `src/components.jsx`): shimmer placeholders replace text spinners on Dashboard,
  Reports, Employees, Users, and the Log Violation form; respects
  `prefers-reduced-motion`.
- **Toast notifications** (`src/toast.jsx`): success/error/warning/info toasts with
  `aria-live`, auto-dismiss, manual close; wired to every create/delete/export action.
- **Confirmation modals** (`src/modal.jsx`): accessible dialog (focus trap, Esc, focus
  restore, `aria-modal`) replaces `window.confirm` for deleting violations/employees and
  deactivating users.
- **Debounced search** (`useDebouncedValue` in `src/hooks.js`): 300 ms debounce on the
  Employees search and a new free-text search on Reports (employee, incident, category,
  comment, submitted-by); `/` focuses the search box.
- **Pagination** (`usePagination` + `Pager`): Reports history and Employees tables page
  at 10 rows with an accessible pager. (Virtualization deferred — see changelog notes.)
- **PDF export** (`src/pdf.js`): print-window export with brand header, filter summary,
  and totals — chosen over a JS PDF lib because the browser shapes Arabic/RTL text
  correctly with no font embedding. Excel export now reports success/failure via toast;
  the Dashboard's previously dead Export button is wired up.
- **Keyboard shortcuts** (`useHotkeys`): `d/n/e/r` navigate (role-aware), `/` focuses
  search, `?` opens a shortcuts help modal, Esc closes overlays; suppressed while typing.
- **Mobile responsiveness**: sidebar becomes a hamburger-triggered overlay drawer below
  820 px; all fixed multi-column grids converted to `auto-fit/minmax`; topbar condenses.
- **Accessibility**: WCAG AA contrast fix for secondary text (`--g400` darkened),
  `:focus-visible` outlines, `scope="col"` on table headers, `aria-label`s on all
  icon-only buttons, `aria-current` on nav, `role="alert"`/`role="status"` on
  messages, labeled search inputs.
- **Self-hosted fonts** (closes audit F-22): DM Sans + Noto Sans Arabic bundled via
  `@fontsource-variable`; the Google Fonts runtime `<link>` is gone.
- **Persisted preferences**: language and theme survive reloads (`localStorage`).

### Removed
- The decorative (non-functional) notification-bell button in the topbar.

### Deferred
- List virtualization — pagination covers current data volumes; revisit if tables
  exceed a few thousand rows.

## Phase 2 — Authentication Module (2026-06-09)

Replaces the single shared HTTP Basic credential with per-user accounts, server-side
sessions, and role-based access control. ⚠️ Breaking: `HR_ADMIN_*` env vars are retired;
set `HR_BOOTSTRAP_ADMIN_EMAIL` / `HR_BOOTSTRAP_ADMIN_PASSWORD` (+ optional `_NAME`) to
seed the first HR Manager account on an empty `users` table.

### Backend
- **Per-user accounts** (`app/db.py`, `app/routers/auth.py`): new `users` table (bcrypt
  password hashes, role, department, active flag); manager-only user management endpoints
  (`GET/POST /api/auth/users`, `DELETE /api/auth/users/{id}` deactivates + kills sessions).
- **Cookie sessions** (`app/auth.py`): `POST /api/auth/login` sets an httpOnly,
  SameSite=Lax `hr_session` cookie (12 h, or 30 days with *remember me*); only the
  SHA-256 of the token is stored server-side. `POST /api/auth/logout` revokes it.
  Set `COOKIE_SECURE=true` in production.
- **CSRF protection**: double-submit token — readable `hr_csrf` cookie must be echoed in
  `X-CSRF-Token` on every non-GET request, verified against the session row.
- **RBAC** — vertical: violations create = Manager/Officer, delete = Manager only;
  employees write = Manager/Officer, delete = Manager; dashboard/export/proof = Manager/
  Officer. Horizontal: Department Heads only see their department's employees/violations;
  Employees only their own violations (scoped SQL, not client-side filtering).
- **Account lockout** (`app/auth.py`): 5 failed logins per account in 15 min locks the
  account for 15 min (persisted), on top of Phase 1's per-IP throttle. Generic
  "Invalid email or password" regardless of which part was wrong.
- **Password reset** (`app/routers/auth.py`, `app/emailer.py`): `POST /api/auth/forgot`
  always returns the same body (no user enumeration) and emails a single-use, 60-minute
  token (SHA-256-stored) via SMTP (`SMTP_HOST/PORT/USER/PASSWORD/FROM`, link base
  `APP_BASE_URL`); without SMTP the link goes to server logs only. `POST /api/auth/reset`
  burns the token and revokes all of the user's sessions.
- **`submitted_by` is now server-derived** from the session user — clients can no longer
  spoof who logged a violation.
- `GET /api/auth/check` (Basic) removed; `/api/auth/me` returns the session user.

### Frontend
- **Login page rebuilt** (`src/pages/Login.jsx`): email + password with client-side
  validation, show/hide password toggle, *remember me*, forgot-password flow, token reset
  screen (`/?reset_token=…`), loading states, bilingual (EN/AR) error messages mapped
  from status codes, brand teal/orange, full RTL/LTR.
- **Session bootstrap & protected shell** (`src/App.jsx`): `/auth/me` on load restores the
  session; unauthenticated users only ever see the login screen; nav and landing page are
  filtered per role; topbar shows the real user's name + role (hardcoded "Amin" removed);
  logout calls the API and clears the session server-side.
- **API client** (`src/api.js`): credentials: same-origin cookies, automatic
  `X-CSRF-Token` header on mutations, no tokens in web storage at all (closes F-2).
- **Users admin page** (`src/pages/Users.jsx`, HR Manager only): list/create/deactivate
  accounts with role + department.
- **Role-aware UI**: Reports hides export/delete from unauthorized roles; Employees page
  is read-only for Department Heads; Log Violation shows the session user as the
  (non-editable) HR representative.

### Deferred
- 2FA (optional scope) — recommend after Phase 3/4.
- Password change for logged-in users (self-service) — reset flow covers it interim.

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
