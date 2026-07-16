# HR Disciplinary System — Local Setup, Test, Performance & Deployment Report

> ⚠️ **Outdated point-in-time report (2026-06-06).** Parts of it no longer match
> the code — notably auth is now cookie sessions + bcrypt (not HTTP Basic), there
> is no `admin123` default, and the API surface has grown. Treat **`CLAUDE.md`**
> as the source of truth for current architecture, tables, and endpoints.

**Prepared:** 2026-06-06
**Scope:** Make the app run locally (the previous hosted deployment is offline), test all features, optimize performance, assess production readiness, and recommend a hosting target for 50–100 users.

---

## 0. What the project actually is (architecture clarification)

The repo contains **several historical copies**. The *current, live* stack (branch `feat/new-design-production-frontend`, latest commit "ship new design as production HR app") is:

| Layer | Path | Tech |
|-------|------|------|
| **Frontend** | `frontend/` | React 18 + Vite 5 (vanilla JS, inline styles, bilingual EN/AR) |
| **Backend**  | `backend/`  | FastAPI + **SQLite** (`hr_system.db`), HTTP Basic auth |

The frontend calls `/api/*`, which Vite proxies to `http://localhost:8000`. The API surface the frontend uses (`/auth/check`, `/employees`, `/violations`, `/stats/dashboard`, `/matrix`) matches **`backend/`** exactly.

> The `production/` directory and the root `*.html` / `main.py` / Streamlit files are **older, superseded implementations**. They are *not* part of the running app and can be archived. (The populated 9 MB DB lived under `production/backend/` but its `employees`/`violations` schema is byte-identical to the current backend, so it was reused as the local dataset.)

---

## A. Local Deployment Documentation

### Prerequisites discovered on this machine
- **Python 3.12** ✅ installed (`%LOCALAPPDATA%\Programs\Python\Python312`) and already has `fastapi`, `uvicorn`, `openpyxl`, `pydantic`.
- **Node.js** ❌ was **not installed**, and no `winget`/`choco`/`nvm` available. A **portable Node 20.18.1** was downloaded and extracted to `./.tools/` (git-ignored, no admin/system change required).

### One-command start
```powershell
# from repo root
powershell -ExecutionPolicy Bypass -File .\run-local.ps1
```
This launches both servers in separate windows:
- **Backend** → http://localhost:8000  (health: `/health`, interactive docs: `/docs`)
- **Frontend** → http://localhost:5173
- **Login:** `hr` / `admin123`

Run only one side with `-Backend` or `-Frontend`.

### Manual start (equivalent)
```powershell
# Backend
cd backend
$env:HR_ADMIN_USERNAME="hr"; $env:HR_ADMIN_PASSWORD="admin123"
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --port 8000 --host 127.0.0.1

# Frontend (new terminal)
cd frontend
$env:Path = "$PWD\..\.tools\node-v20.18.1-win-x64;$env:Path"
npm install   # first time only
npm run dev
```

### Environment variables
| Var | Default | Purpose |
|-----|---------|---------|
| `HR_ADMIN_USERNAME` | `hr` | Basic-auth username |
| `HR_ADMIN_PASSWORD` | `admin123` | Basic-auth password |
| `HR_DB_FILE` | `<repo>/hr_system.db` | SQLite file path |

### Data
The local DB (`hr_system.db`, ~8.6 MB, 2 employees / 7 violations) was seeded from the previous deployment's database. `*.db` is git-ignored.

### ⚠️ Known toolchain quirk (documented, worked around)
On this machine **pip itself hangs** (every `pip ...` invocation blocks at 0 % CPU during CLI startup, even offline commands like `pip list`; `import pip` works and Python's own `urllib` reaches PyPI in 0.3 s — so it is a local pip/CLI environment issue, not network). **Workaround used:** the backend runs on the system Python, which already has all required packages, so no `pip install` is needed locally. If you ever need to install Python packages, do it from a fresh shell / a repaired Python, or use the system interpreter that already has them.

---

## B. Testing Report

All API features were exercised against the running backend (direct and through the Vite proxy). **No functional bugs were found in the current backend/frontend — the escalation engine, auth, CRUD, filtering, and export all behave correctly.**

| Feature | Test | Result |
|---------|------|--------|
| Health | `GET /health` | ✅ `{ok:true}` |
| Auth — reject | `GET /api/auth/check` no creds | ✅ `401` |
| Auth — reject | bad password through proxy | ✅ `401` |
| Auth — accept | `hr/admin123` | ✅ `200 {user:"hr"}` |
| Employees list | `GET /api/employees` | ✅ 2 rows |
| Employee create | `POST` new employee | ✅ `201`, upsert works |
| Employee delete | `DELETE /api/employees/{name}` | ✅ `204` |
| Matrix | `GET /api/matrix` | ✅ 4 categories / 17 incidents + penalty map |
| **Escalation engine** | 6× "Late Arrival" for one employee | ✅ **Yellow → Yellow → Orange → Red → Black → Investigation** (exactly per ladder) |
| Escalation cap | 7th preview | ✅ stays `Investigation` (capped) |
| Penalty days | per level | ✅ 0 / 0.5 / 2 / 4 days as configured |
| Force investigation | `force_investigation:true` | ✅ overrides to `Investigation` |
| Override days | `override_days:3.5` | ✅ label "Red Card — 3.5 Days Deduction (Override)" |
| Preview | `GET /violations/preview` | ✅ correct next penalty (needs URL-encoded `&` in category) |
| Dashboard stats | `GET /api/stats/dashboard` | ✅ totals, by_color, by_category, top_incidents, monthly, recent |
| Report filters | employee/date/penalty filters | ✅ server-side filtering correct |
| Excel export | `GET /api/violations/export` | ✅ `200`, valid `.xlsx` (5.6 KB) |
| Frontend serve | Vite dev + proxy | ✅ HTML, JS modules, `/api` proxy all `200` |
| Production build | `npm run build` | ✅ compiles, 40 modules, 189.7 KB JS |

### Issues found & fixed (see Performance section for the big one)
1. **🔴 Major — base64 proof images inlined in list/dashboard responses.** Root cause: `SELECT *` returned the `proof_image` blob in `GET /api/violations` and dashboard `recent`. **Fixed.**
2. **🟡 Minor — no DB indexes.** Escalation/filter queries did full scans. **Fixed** (indexes added).
3. **🟡 Minor — `--reload` not effective** with the system uvicorn (watchfiles not picked up). Documented; restart the backend after backend code changes.

### Remaining concerns (not blocking)
- Seed violations use old category/incident names (e.g. `Attendance`, `Sleeping on Job`) that predate the current matrix (`Attendance & Adherence`, `Sleeping on the Job`). Old rows display fine but won't escalate against the new ladder. Cosmetic / historical only.
- Single hardcoded admin user (`hr`) — no per-user accounts (frontend shows a static "Amin").
- No automated test suite in `backend/tests` for the current backend.

---

## C. Performance Report

### Before → After

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| `GET /api/violations` payload (7 rows, 3 with images) | **~9,000,000 bytes (9 MB)** | **2,174 bytes (2.2 KB)** | **≈4,000× smaller** |
| Dashboard `recent` | included full base64 images | flags only (`has_proof`) | image bytes removed |
| Escalation / filter queries | full table scan | indexed | scales with row count |
| Frontend bundle (gzip) | 58 KB | 58 KB (already small) | n/a |

The hosted "slow loading / slow data fetch / delayed UI" symptoms were almost entirely this: **every Reports/Dashboard load shipped multi-MB of base64 image data** (and Reports re-fetches on every filter change). That payload now fits in a couple of kilobytes.

### Optimizations implemented (code)
- **`backend/app/routers/violations.py`** — list query now selects explicit columns **excluding `proof_image`** and returns a `has_proof` boolean; added **`GET /api/violations/{id}/proof`** to fetch a single image on demand.
- **`backend/app/routers/stats.py`** — dashboard `recent` no longer returns image blobs.
- **`backend/app/schemas.py`** — `Violation` drops `proof_image`, adds `has_proof`.
- **`backend/app/db.py`** — added indexes: `(employee_name, incident, created_at)`, `(created_at)`, `(penalty_color)`.

Frontend list/grid views never displayed the inline image, so this change is **backwards-compatible** (no UI breakage). Total verified.

### Frontend findings (good as-is for this scale)
- Single 189.7 KB / **58 KB gzip** bundle — code-splitting/lazy-loading is **unnecessary** at this size; would add complexity for no benefit at 50–100 users.
- Matrix and employee lists are fetched once and cached in component state. Fine.
- Minor future polish (optional): debounce Reports filter refetch; preconnect/​self-host the Google Fonts `<link>`; serve the built `dist/` behind gzip/brotli in production (handled automatically by the recommended hosts).

### Recommended next optimization (not yet done)
- **Stop storing proof images in the DB.** Base64 in SQLite is what made the DB 9 MB for 7 rows. Move proofs to object/file storage (local disk volume, or S3/R2) and keep only a path. This also shrinks backups and memory use on export.

---

## D. Production Readiness Report

### Already in good shape (improved vs. the old `CLAUDE.md` "known issues")
- ✅ **CORS is locked** to `localhost:5173/127.0.0.1:5173` (not wildcard `*`). Update this list to the real production frontend origin at deploy time.
- ✅ **Auth is enforced** on every data route (`Depends(require_admin)` on all routers) using constant-time comparison.
- ✅ Clean, small, readable backend; pydantic schemas; parametrized SQL (no injection); transactional DB context manager with rollback.

### Security items to address before public production
1. **🔴 Secret committed to git:** `production/backend/.env` contains a real Gmail SMTP **app password**. Rotate that credential and purge the file from history (`git rm --cached`, add to `.gitignore` — done for new `.env`). It belongs to the old backend but is still exposed.
2. **🔴 Default admin password** `admin123`. Set a strong `HR_ADMIN_PASSWORD` via environment/secret manager in production. Never bake it into images.
3. **🟠 HTTP Basic single-user auth.** Acceptable for a tiny internal tool, but for real HR data prefer: per-user accounts, hashed passwords (bcrypt/argon2), JWT or server sessions, and an audit log of who logged what. The `users` table already exists to build on.
4. **🟠 Serve over HTTPS only** (the recommended hosts give this free). Send the Basic-auth header only over TLS.
5. **🟡 Proof images** as base64 in DB (see Performance) — also a data-hygiene/PII concern; put behind auth + object storage with signed URLs.

### Engineering / maintainability
- **Logging/monitoring readiness:** add structured request logging + a `/health` (exists) and `/ready` probe; ship logs to the platform's log drain. Add Sentry (free tier) for error tracking — ~15 min.
- **Config management:** centralize env reading; provide `.env.example`; never commit `.env` (now git-ignored).
- **Dependency review:** `backend/requirements.txt` pins **`psycopg2-binary` and `asyncpg`** that are **never imported** (the code is SQLite-only). These caused the install to stall and are dead weight — remove them, or actually wire PostgreSQL if you plan to scale (recommended for production, see below).
- **Type safety:** backend is already typed via pydantic; frontend is plain JS — fine for the size, but TypeScript would help if the team grows.
- **Dead code:** archive `production/`, root `*.html`, `main.py`, `*.xlsx`, `hr system-handoff.zip` to a separate branch/folder to avoid confusion about which app is live.

### Architecture recommendation
Keep the simple 2-tier (React static + FastAPI) shape. For production, **migrate SQLite → PostgreSQL** (managed) and move proof images to object storage. Everything else can stay as-is.

---

## E. Scalability Assessment (50–100 users)

- **Load profile:** internal HR tool, ~50–100 users, mostly reads (dashboard/reports) with occasional writes (log a violation). Realistically a few requests/second peak.
- **Current suitability:** A single small instance (1 vCPU / 1–2 GB RAM) running uvicorn + the static frontend **easily** handles this *once the payload fix is in* (it is).
- **Bottlenecks:**
  - *Was:* the multi-MB image payloads (**fixed**).
  - *SQLite write concurrency:* SQLite serializes writes. At this user count it's fine, but it's the first thing to outgrow → move to **PostgreSQL** for safe concurrency and easy backups.
  - *Proof images in DB:* inflate memory/backup → object storage.
- **Resource target:** 2 vCPU / 2–4 GB RAM is comfortable headroom. Add `uvicorn --workers 2–4` (or gunicorn+uvicorn workers) behind the platform's TLS/proxy.

---

## F. Deployment on Railway

The deployment target is **Railway** (https://railway.com). This section covers how to host the two services, how to handle proof photos, and which pricing plan to pick.

### Service layout

Run the app as one Railway **project** with two services deployed from the GitHub repo:

| Service | Source | Build | Runtime |
|---------|--------|-------|---------|
| **backend** | `backend/` | Dockerfile or Nixpacks (Python) | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **frontend** | `frontend/` | `npm run build` | serve static `dist/` |

Railway provides automatic HTTPS and a public domain per service, and redeploys on every push. Set `HR_ADMIN_USERNAME` and `HR_ADMIN_PASSWORD` (a strong value — not `admin123`) as service **variables/secrets**, and lock backend `CORS_ORIGINS` to the frontend's Railway domain.

> SQLite serializes writes and a Railway volume attaches to **one** service instance, so keep the backend at a **single replica** (do not enable horizontal scaling on it). That is plenty for 50–100 users (see § E).

### Persisting the database

Railway containers have an **ephemeral filesystem** — anything not on a mounted volume is wiped on every redeploy/restart. So:

1. Add a **Volume** to the backend service (e.g. mounted at `/data`).
2. Set `HR_DB_FILE=/data/hr_system.db` so the SQLite file lives on the volume and survives deploys.

Without this, the database resets on each deploy. This is the single most important step.

### Handling proof photos

Proof images are currently stored as **base64 inside the SQLite row** (`violations.proof_image`). That works on Railway as-is once the DB is on a volume, but it has real downsides here: it inflated the DB to ~9 MB for 7 rows, bloats backups, and — because Railway **bills egress** — re-serving image bytes on every report/dashboard load costs money. The list/dashboard payload fix (§ C) already stopped shipping those bytes in bulk; images are now fetched one-at-a-time via `GET /api/violations/{id}/proof`.

Three options, in order of recommendation:

1. **Move proofs to files on the Railway Volume (recommended).** Write each upload to `/data/proofs/<id>.<ext>` and store only the path in the DB. Keeps the DB tiny and fast to back up, survives redeploys, no extra service. Same single-replica caveat as the DB.
2. **Move proofs to external object storage (Cloudflare R2 / S3).** Store a key in the DB and serve via short-lived signed URLs. Best for backups and egress, and decouples photos from the app instance; costs ~15–30 min of wiring plus a (free-tier) R2 bucket. Pick this if proof volume grows large.
3. **Leave them in SQLite.** Zero work, already functioning. Acceptable only while the proof count stays small; revisit before the DB grows past a few hundred MB.

Either way, keep proof images **behind auth** (they are PII) — never expose a public bucket or unauthenticated path.

### Pricing tiers — which to pick

> Railway is **usage-metered** (CPU, RAM, egress, volume storage) on top of a plan fee. The figures below are Railway's published plans **as of June 2026** and change over time — confirm on https://railway.com/pricing before committing.

| Plan | Fee | Included usage | Notes |
|------|-----|----------------|-------|
| **Trial** | $0 | one-time credit | For evaluation only; not for a real deployment. |
| **Hobby** | **$5/mo** | **$5 of usage included** | Persistent volumes, custom domains, auto-TLS. Sufficient for this app's traffic. |
| **Pro** | $20/mo per seat | $20 of usage included | Higher resource limits, team features, priority support. Not needed at this scale. |

**Pick Hobby.** For a single-replica FastAPI backend + a static frontend at 50–100 internal users, expected usage sits at or near the $5 included credit, so the realistic bill is **~$5/mo** (a little more if proofs stay in the DB and drive egress — another reason to apply proof-storage option 1 or 2). Move to Pro only if you outgrow Hobby's resource caps or need team/seat features.

### Deployment steps

1. **Backend prep:** add a `Dockerfile` (or rely on Railway's Python/Nixpacks build). Remove the unused `psycopg2-binary`/`asyncpg` from `requirements.txt` (the code is SQLite-only — see § D) so builds stay lean.
2. **Create the backend service** from the GitHub repo with root `backend/`; set `HR_ADMIN_USERNAME`, `HR_ADMIN_PASSWORD`, and `CORS_ORIGINS` as variables.
3. **Add a Volume** to the backend, mount at `/data`, and set `HR_DB_FILE=/data/hr_system.db`. Apply a proof-photo option above.
4. **Create the frontend service** from `frontend/`: build `npm run build`, serve `dist/`. Point its API base at the backend's Railway URL (replace the dev `/api`→localhost proxy) and add that origin to backend CORS.
5. **Verify** HTTPS, login, a full log-violation flow, and that data survives a redeploy.
6. *(Optional)* Add Sentry (free tier) for error tracking.

---

## Files changed in this pass
- `backend/app/routers/violations.py` — drop `proof_image` from list; add `has_proof`; new `GET /violations/{id}/proof`.
- `backend/app/routers/stats.py` — drop image blobs from dashboard `recent`.
- `backend/app/schemas.py` — `Violation`: `proof_image` → `has_proof`.
- `backend/app/db.py` — add 3 indexes.
- `run-local.ps1` — one-command local startup (system-Python fallback).
- `.gitignore` — ignore `.tools/`, `.env`, `*.local`.
- `HANDOVER.md` — this document.
