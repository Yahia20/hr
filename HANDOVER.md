# HR Disciplinary System — Local Setup, Test, Performance & Deployment Report

**Prepared:** 2026-06-06
**Scope:** Make the app run locally (Fly.io trial ended), test all features, optimize performance, assess production readiness, and recommend a hosting target for 50–100 users.

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

The Fly.io "slow loading / slow data fetch / delayed UI" symptoms were almost entirely this: **every Reports/Dashboard load shipped multi-MB of base64 image data** (and Reports re-fetches on every filter change). That payload now fits in a couple of kilobytes.

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

## F. Deployment Recommendation (ranked)

Goal: cheapest reliable host for a small internal app, easy to maintain, room to grow. Costs are approximate monthly USD as of 2026.

### Ranked

| # | Option | Est. /mo | Best for | Notes |
|---|--------|----------|----------|-------|
| **1 (Recommended)** | **Render** (Web Service + Static Site + free/cheap Postgres) | **$0–14** | Lowest ops effort | Free static frontend; web service from ~$7; managed Postgres ~$7. Auto-TLS, auto-deploy from GitHub, logs/metrics built in. No server to patch. |
| 2 | **Railway** | **~$5–15** (usage) | Fast setup, great DX | Usage-based; deploys Docker/Nixpacks; managed Postgres add-on; auto-TLS. Slightly less predictable cost. |
| 3 | **Fly.io (paid)** | **~$5–15** | Staying on current platform | You already have `fly.toml`. Smallest `shared-cpu-1x` + a volume; add Fly Postgres. Re-uses existing config. |
| 4 | **Hetzner CPX11 VPS + Coolify** | **~$5 (€4.5)** | Lowest raw cost, full control | 2 vCPU / 2 GB. Install Coolify for Heroku-like deploys. You own patching/backups. Best price/perf if you want a server. |
| 5 | **Oracle Cloud Free Tier** | **$0** | Zero budget | Generous always-free ARM VM (up to 4 vCPU/24 GB). Free forever but capacity/onboarding can be fiddly; you self-manage everything. |
| 6 | DigitalOcean App Platform / Lightsail | ~$5–12 | Familiar ecosystem | Solid, slightly pricier than Hetzner; managed-ish. |
| — | Contabo / Hostinger VPS | ~$5–7 | Cheap VPS alt to Hetzner | Cheap; mixed reliability reputation vs Hetzner. |

### Final recommendation
- **Want least maintenance (recommended):** **Render** — frontend as a free Static Site, backend as a small Web Service, and **managed PostgreSQL**. Auto-HTTPS, auto-deploy on push, built-in logs. Total ≈ **$7–14/mo** (or near-$0 to start on free tiers).
- **Want lowest cost / full control:** **Hetzner CPX11 (~€4.5/mo) + Coolify**, Postgres in a container, nightly volume snapshots.
- **Want to keep Fly.io:** re-enable the existing `fly.toml`, smallest paid instance + Fly Postgres (~$5–15/mo).

### Deployment steps (Render — recommended)
1. **Backend prep:** remove unused `psycopg2-binary`/`asyncpg` *or* (for Postgres) add a real Postgres driver and point `HR_DB_FILE`/`DATABASE_URL` at the managed DB. Add a `Dockerfile` or use Render's Python runtime with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
2. **Create Web Service** from the GitHub repo, root `backend/`; set env vars `HR_ADMIN_USERNAME`, `HR_ADMIN_PASSWORD` (strong), and DB URL as **secrets**.
3. **Create PostgreSQL** instance; migrate the SQLite data (small).
4. **Create Static Site** from `frontend/`; build `npm run build`, publish `dist/`. Set the API base / proxy to the backend URL (replace the dev `/api`→localhost proxy with the real backend origin, and add that origin to backend CORS).
5. **Lock CORS** to the Static Site URL; verify HTTPS, login, and a full log-violation flow.
6. **Add Sentry + log drain** (optional, free) for monitoring.

---

## Files changed in this pass
- `backend/app/routers/violations.py` — drop `proof_image` from list; add `has_proof`; new `GET /violations/{id}/proof`.
- `backend/app/routers/stats.py` — drop image blobs from dashboard `recent`.
- `backend/app/schemas.py` — `Violation`: `proof_image` → `has_proof`.
- `backend/app/db.py` — add 3 indexes.
- `run-local.ps1` — one-command local startup (system-Python fallback).
- `.gitignore` — ignore `.tools/`, `.env`, `*.local`.
- `HANDOVER.md` — this document.
