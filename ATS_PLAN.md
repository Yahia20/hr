# ATS Module — Implementation Plan (rules + jev classifier)

Adds recruitment (Applicant Tracking) to the Travel Gate HR system: job openings,
applicants with CV upload, automatic CV evaluation, a hiring pipeline and
interview feedback. The **ranking score is deterministic and explainable**:
keyword/taxonomy matching + rules, every point with a quoted line, computed
locally. Since 2026-10-04 an optional **jev** layer (TypeSafe classifier via
OpenRouter, no text generation) judges per-job yes/no "semantic criteria" on a
redacted copy of the CV — see Phase 1b. It starts in shadow mode (shown to HR,
not used for ranking) and only sends data out after the privacy prerequisites
in Phase 1b are met.

Reference designs (ideas only, no code copied — GPL/AGPL):
Frappe HR recruitment doctypes (tables/stages), sliday/resume-job-matcher
(hard gates + anchored 0–4 criteria + quoted evidence), sunnypatell/ats-screener
(keyword weights used by commercial ATSs).

Conventions: follow the existing modules exactly — raw SQL through `db()`,
`CREATE TABLE IF NOT EXISTS` in `_SCHEMA`, base64 attachments in the row
(see `permissions`), `require_role` guards, Pydantic models in `schemas.py`,
one React page per feature, every string in `i18n.js` (EN + AR).

---

## Phase 0 — Seed taxonomy + role templates (derived, not supplied) · 1 day

HR has **no job list and no criteria**. So we ship sensible defaults and make
everything editable in the app; HR refines by using it, not by filling a spec.

Inputs: 13 real CVs in `ats-samples/` (git-ignored, **never committed**, never
copied into tests). Observed mix: reservation/ticketing officer, visa consultant,
travel consultant, branch/operations manager, marketing manager, data analyst,
HR/customer service. Observed extraction problems that the engine must handle:
Arabic PDFs come out as presentation-form glyphs with reversed word order, and
Latin words inside them are letter-spaced ("A m a d e u s", "N D C"); one DOCX;
multi-page CVs with a cover letter first.

Deliverables:
- `backend/app/ats/taxonomy.py` — seeded skills (list below + anything recurring in the samples).
- `backend/app/ats/role_templates.py` — 6 starter job templates, each with
  required/preferred skills, min years, education, languages, default weights:
  Reservation & Ticketing Officer, Travel Consultant, Visa Consultant,
  Branch/Operations Manager, Marketing Specialist, HR & Customer Service.
  "New job" in the UI starts from a template.

1. **Roles** — the 6 templates above; more are created in the app.
2. **Skills taxonomy**: canonical skill → aliases (EN + AR), grouped by
   category. Seeded by us, HR corrects it in Settings:
   - GDS / ticketing: Amadeus, Sabre, Galileo/Travelport, IATA, BSP, fare rules,
     PNR, refunds/reissue, LCC portals.
   - Product: hotel booking, Umrah/Hajj packages, visa processing, tours,
     car rental, B2B suppliers (Hotelbeds, WebBeds, TBO…).
   - Sales/CRM: Bitrix24, cold calling, upselling, quotations, WhatsApp sales.
   - Office: Excel, Word, email etiquette, Arabic typing, English.
   - Finance: bookkeeping, invoicing, VAT/ZATCA, Zoho Books, QuickBooks.
   - Soft: negotiation, customer service, teamwork (low weight).
3. **Hard gates** HR wants available: nationality, city/relocation, language,
   min years, education, driving licence, transferable iqama.
4. **Default weights** per criterion (see scoring spec). HR can override per job.

---

## Phase 1 — Parsing + scoring engine (pure Python, no API) · 3 days

New package `backend/app/ats/`:

| file | responsibility |
|---|---|
| `extract.py` | bytes → text. PDF via `pypdf`, DOCX via `python-docx`, TXT as-is. Reject > 5 MB. If extracted text < 200 chars → `needs_manual_review=True` (scanned CV). |
| `normalize.py` | NFKC, lowercase, Arabic normalisation (أإآ→ا, ة→ه, ى→ي, strip tashkeel + tatweel), collapse whitespace, keep a line-indexed copy for evidence. |
| `taxonomy.py` | `SKILLS = [{"id","canonical","category","aliases":[…]}]` (like `MATRIX_DATA` in `penalties.py`). Loaded into DB table `skills_taxonomy` on boot if empty. |
| `parse.py` | `parse_cv(text) -> ParsedCV`: email, phone (KSA/EG/intl regex), name heuristic (first line without digits/@, else filename), sections by EN/AR heading dictionary, **years of experience** (date-range regex incl. "Present/حتى الآن" + Arabic months; merge overlaps; fallback "X years" phrase), education level ordinal (PhD>Master>Bachelor>Diploma>High school, EN+AR), languages, skills (alias match on word boundaries, multi-word first) each with the matching line as evidence. |
| `score.py` | `score(parsed, job) -> ScoreResult` per spec below. |
| `similarity.py` | Hand-rolled TF-IDF cosine between JD text and CV text (~40 lines, avoids the scikit-learn dependency). |

### Scoring spec

1. **Hard gates** (pass/fail, evaluated first). Any failure → `score = 0`,
   `gate_failures = [...]`, applicant stays visible but flagged. Gate types:
   `nationality_in`, `city_in`, `language_required`, `min_years`,
   `min_education`, `licence_required`. Unknown value (parser found nothing)
   → gate result `unknown`, does **not** fail; surfaced for HR review.
2. **Criteria**, each scored 0–4 with an anchored rule, each with evidence:

   | criterion | default weight | 0–4 rule |
   |---|---|---|
   | required skills | 40 | coverage = matched/required: 0 <25%, 1 <50%, 2 <75%, 3 <100%, 4 = all |
   | experience | 20 | years/min_years: 0 <50%, 1 <75%, 2 <100%, 3 <150%, 4 ≥150% (no min → 4 if any experience found) |
   | preferred skills | 10 | same coverage ladder as required |
   | education | 10 | ordinal distance from required level: 4 equal/above, 2 one below, 0 otherwise |
   | languages | 10 | required languages found / total |

   TF-IDF JD similarity is **not** a scoring criterion (weak, redundant, hard to
   explain — decided 2026-10-04). `similarity.py` is kept only to suggest the
   best-matching role template, and may abstain.

   `final = Σ(w·s) / (4·Σw) · 100`, rounded. Weights editable per job; must sum > 0.
3. **Output** stored on the applicant: `score`, `score_breakdown` JSON
   `[{criterion, weight, score_0_4, evidence:[{term, line}], missing:[…]}]`,
   `gate_failures`, `parsed` JSON, `needs_manual_review`.
4. Manual corrections to parsed fields (years, education, skills) by HR trigger
   a re-score; corrections are stored separately from the parser output.

### Tests (`backend/tests/test_ats_parse.py`, `test_ats_score.py`)
- Committed fixtures are **synthetic only** (fake names/emails), generated in
  the tests: EN text, AR text, bilingual DOCX built with python-docx, a
  presentation-form + reversed-order Arabic string, letter-spaced Latin, and an
  empty/scanned-like PDF (expects manual-review flag).
- Golden expectations per fixture (email, years ±1, education, ≥N skills).
- Score: gates fail → 0; weights sum; each criterion ladder boundary; evidence
  present for every matched term; re-score after correction.

### Real-CV evaluation (local only)
`backend/scripts/ats_eval.py <folder>` runs extract→parse→score (against every
role template) on a folder and prints a table; nothing written to the repo.
Accuracy is checked against hand-written labels kept in
`ats-samples/labels.json` (git-ignored, written by the reviewer, not the implementer).

Exit criteria: email/phone correct on ≥ 12/13 real CVs, education on ≥ 11/13,
years within ±1 on ≥ 10/13, the Arabic reservation CV finds Amadeus + NDC,
each CV's best-matching template is the sensible one, < 300 ms per CV for
parse+score (extraction of long PDFs measured separately; the 6-page sample
takes ~0.5 s and runs off the event loop).

Arabic extraction (prerequisite for Phase 1b): keep two outputs — a **readable
text** (logical order, letter-spaced Latin re-joined, with a line map back to the
source) and the aggressive matching normalisation. Tests must cover
already-logical Arabic, presentation-form + reversed Arabic, mixed scripts,
two-column layouts and spaced Latin, and verify whole experience statements read
correctly, not just that "Amadeus" is detected. (2026-10-04: the Arabic
reservation sample still misses Amadeus; `__init__.py` imports `parse`/`score`
which do not exist yet.)

---

## Phase 1b — Semantic criteria with jev (shadow first) · 3 days build, validation ongoing

Decided 2026-10-04 by the owner; design reviewed with astra (Codex) the same day.

**What jev is.** `POST https://openrouter.ai/api/alpha/decisions`, model
`typesafe/jev-1.13`, body `{model, state:{…}, questions:{key:{type:"noul",
instructions}}}` → `answers.key.noul` ∈ [0,1]. Several questions per call.
No reasoning text, no evidence span. Limit 32,000 tokens (state + questions),
billed per input token (`usage.cost` in each response); output free.

**Scope.**
- Per job, 2–6 **semantic criteria**: English yes/no definitions phrased as
  *"Does the CV explicitly state …"* (a CV classifier checks what the CV says,
  not real competence), each with exclusions, an Arabic description, weight,
  per-question thresholds and a validation status (`draft` / `shadow` /
  `validated`). Seed 2 per relevant role template.
- Never a hard gate, never changes a stage, no tools. Don't double-count a
  skill that keyword matching already scores.
- **Shadow mode first:** HR sees the model's assessment next to the rules score;
  ranking uses `rules_score` only until a question is `validated`.

**Input.** One call per (applicant, rubric revision): the whole readable CV
after **local span redaction** (emails, phones, URLs, ID/iqama/passport-like
numbers incl. Arabic digits and spaced forms, birth dates, the contact/references
block, the candidate's name spans — not every token that matches the name, and
keep job titles, employers and employment dates) plus all the job's questions.
No chunking, no silent truncation: over the local size ceiling, poor extraction
or uncertain redaction → no external call, `needs_manual_review`.
CV text goes only into `state`, never into a question definition (prompt
injection); questions are trusted config.

**Evidence.** jev gives none, so the UI shows "model assessment" + locally
selected "passages to review" (taxonomy/keyword hits). A passage becomes
supporting evidence only when HR confirms it. Raw `p` is shown in details,
labelled as model output.

**Score mapping.** `p ≥ t_yes` → 4, `p < t_no` → 0, otherwise `uncertain`
(NULL, needs HR decision — not "half qualified"). Starting values 0.70 / 0.35,
calibrated per question. `rules_score` is always stored; `final_score`
(rules + validated semantic criteria) is NULL while any required judgement is
missing or uncertain — **no renormalising**, so an outage or opt-out never
changes someone's score. Opted-out applicants get a manual-assessment route.

**Execution.** Upload commits the applicant + a pending semantic run in one
transaction. One lifespan-managed worker (next to `_reminder_scheduler`) claims
runs with a lease + expiry, calls jev **outside** any `db()`/`lock()`
transaction, and publishes results only if the CV / rubric / consent revision is
unchanged. Restart recovery picks up pending and expired-lease runs. Before every
dispatch (incl. retries and previews) re-check consent, kill switch and budget.
At-least-once calls, idempotent publication. Retry only network/429/5xx (max 3,
backoff + jitter); stop on 4xx. Strict response validation (all keys present,
finite, in [0,1]). Uvicorn stays at one worker (no `--workers` in the Dockerfile).

**Modules** (`backend/app/ats/`): `semantic_input.py` (readable text,
redaction, limits, quality checks) · `jev_client.py` (bounded HTTP, validation,
usage capture) · `semantic.py` (question versions, cache identity, mapping) ·
`semantic_worker.py` (claim/retry/publish; wired in Phase 2) ·
`backend/scripts/ats_semantic_eval.py` (private evaluation, local only).

**Data** (created in Phase 2, `_SCHEMA` / `_ADDED_COLUMNS`, SQLite + Postgres tested):
- `job_openings` + `rubric_version`, `semantic_criteria` JSON.
- `applicants` + `cv_revision`, `rules_score`, nullable `final_score`,
  `semantic_status` (pending/done/partial/failed/disabled/opted_out/manual),
  `semantic_reason`, `external_processing_consent_at`, `consent_notice_version`.
- `ats_semantic_runs` — applicant FK (cascade), cv/rubric/consent revisions,
  input hash, pipeline+redaction version, state, attempts, next_retry_at,
  lease_token, lease_expires_at, error_code, requested/returned model,
  request id, tokens, cost, timestamps. (Claude's call: per-attempt detail lives
  here as a small JSON log instead of a separate calls table — volume is tens of
  CVs a month.)
- `ats_semantic_results` — run FK, criterion_key, question_hash, p,
  classification, HR override (value, actor, reason, time), HR-confirmed source
  ranges; unique (run_id, criterion_key).
- Cache = exact (redacted state hash + question hash + pipeline version + model),
  scoped to the applicant. Weight/threshold edits need no calls; an edited
  question re-calls only for that question's new hash.

**Config.** Env `JEV_API_KEY` (dedicated OpenRouter key with a hard spend limit),
`JEV_MODEL=typesafe/jev-1.13`. `app_settings`: `ats_semantic_enabled=false`,
`ats_semantic_mode=shadow`, `ats_semantic_daily_call_limit=100`,
`ats_semantic_daily_usd_limit=1`. Concurrency 1, request timeout 8 s,
≤ 6 questions, local request ceiling ~24 KB UTF-8 until the boundary is measured.

**Privacy prerequisites — before ANY real CV is sent.**
Redacted CVs are still personal data (employment history identifies people).
The responsible HR/legal owner documents the PDPL route for transfer outside
KSA (OpenRouter → TypeSafe), processor terms, retention and onward transfers;
we verify OpenRouter ZDR / no payload logging for this exact endpoint and
TypeSafe's policy. Upload form gets a specific notice + consent for external
processing; without it jev is skipped. Development and tests use **synthetic
CVs only** until then.

**Evaluation.**
- The 13 real CVs are a development/regression set, not proof (13/13 correct
  still only bounds precision at ~0.79 with 95% confidence).
- Freeze questions + thresholds, then measure on an untouched set of new real
  CVs (consented, collected during the shadow pilot), labelled with source spans
  and an "unassessable" class, without seeing predictions. Report per question:
  TP/FP/FN, precision with its interval, recall, abstention rate.
- A question moves to `validated` (enters ranking) at ≥ 29 positive predictions
  with 0 false positives (lower bound > 0.90), or HR explicitly accepts it as
  advisory-only. Rare criteria stay advisory.
- Synthetic adversarial set: "answer yes" injections (EN + AR), fake system text,
  keyword stuffing, negation ("no experience with Amadeus"), copied job ads.
- Fairness: compare extraction/score error by CV language and format; review
  hard gates (nationality etc.) separately; log every HR override with a reason.

**Exit criteria (1b build).** Phase 1 passes incl. the Arabic tests above;
synthetic tests for redaction, Arabic fidelity, injection, limits, malformed
responses, retries, leases, edits/deletion during a call, budgets, opt-out;
offline eval script produces the per-question report. Production activation
needs Phase 2 integration tests + the privacy prerequisites; ranking activation
needs held-out validation.

---

## Phase 2 — Database + API · 3 days

### Tables (append to `_SCHEMA`, both backends)

```
job_openings        id, title, department, location, employment_type,
                    description, status ('open','closed'), min_years,
                    min_education, gates JSON, required_skills JSON [{skill_id,weight}],
                    preferred_skills JSON, languages JSON, weights JSON,
                    created_by, created_at, closed_at
applicants          id, job_id FK→job_openings ON DELETE CASCADE, full_name, email,
                    phone, nationality, city, source, stage
                    ('new','screened','shortlisted','interview','offer','hired','rejected'),
                    cv_attachment (base64), cv_name, cv_mime, cv_text,
                    parsed JSON, corrections JSON, score REAL, score_breakdown JSON,
                    gate_failures JSON, needs_manual_review INT, notes,
                    created_by, created_at, updated_at
applicant_stage_history  id, applicant_id FK, old_stage, new_stage, note, changed_by, changed_at
interview_feedback  id, applicant_id FK, interviewer, result ('cleared','rejected'),
                    ratings JSON [{skill, score_1_5}], avg_rating REAL, comment, created_at
skills_taxonomy     id, canonical, category, aliases JSON, is_active INT
```
Indexes: `applicants(job_id, score DESC)`, `applicants(job_id, stage)`,
`applicant_stage_history(applicant_id, id)`.
Unique: `applicants(job_id, email)` where email <> '' (duplicate application guard).

### Router `backend/app/routers/recruitment.py` (prefix `/api/recruitment`)

| method & path | role | notes |
|---|---|---|
| GET/POST `/jobs` | hr_staff; dept_head sees own dept | list excludes description body |
| GET/PUT `/jobs/{id}` · POST `/jobs/{id}/close` | hr_staff | PUT of criteria → `rescore=true` re-runs all applicants |
| POST `/jobs/{id}/rescore` | hr_staff | re-runs all applicants with the current taxonomy, same rubric version (done 2026-10-08) |
| GET `/jobs/{id}/applicants?stage=&sort=score` | hr_staff, dept_head (own dept) | ranked, no CV bytes |
| POST `/jobs/{id}/applicants` | hr_staff | JSON body with base64 CV (same shape as permission attachments, limit 5 MB) → extract, parse, score synchronously |
| GET `/applicants/{id}` | hr_staff, dept_head | parsed + breakdown + history + feedback |
| GET `/applicants/{id}/cv` | hr_manager, hr_officer | base64 download |
| PATCH `/applicants/{id}` | hr_staff | notes, corrections → re-score |
| POST `/applicants/{id}/stage` | hr_staff | validates allowed transition, writes history |
| DELETE `/applicants/{id}` | hr_manager | |
| GET/POST `/applicants/{id}/feedback` | hr_staff, dept_head | avg_rating computed server-side |
| GET `/taxonomy` · POST `/taxonomy` | GET hr_staff, POST hr_manager | edits apply to future scores; "rescore job" is explicit |
| POST `/parse-preview` | hr_staff | parse without saving — used to tune the taxonomy |
| GET `/stats` | hr_staff | open jobs, applicants per stage, avg score per job (for Dashboard tile) |

Stage transitions: `new→screened→shortlisted→interview→offer→hired`, any → `rejected`,
`rejected→screened` (reopen). Enforced server-side.

Schemas in `schemas.py`: `JobIn`, `ApplicantIn`, `ApplicantPatchIn`, `StageIn`,
`FeedbackIn`, `TaxonomyIn` with the same `max_length` discipline as today.

Tests `test_recruitment.py` following `test_permissions.py`: role matrix,
upload+score round-trip, duplicate email, stage transition rules, rescore on
job edit, dept_head isolation.

---

## Phase 3 — Frontend · 4 days

Page ids `jobs` and `cands` added to `ROLE_PAGES` (hr_manager, hr_officer;
`jobs` read-only for dept_head), `NAV_ICONS`, hotkeys optional.

- `pages/Jobs.jsx` — list + drawer form. Criteria editor: gates (chips),
  required/preferred skills picked from taxonomy with weight, languages,
  min years, education, weights sliders with live "sum" indicator. Close/reopen.
- `pages/Applicants.jsx` — job selector → ranked table: score bar, gate flags,
  stage chip (dropdown to move), "needs review" badge, search, stage filter.
  No score-driven bulk reject in the first rollout (every rejection is a human
  decision with a reason). Upload button (drag-and-drop, PDF/DOCX/TXT).
- `ApplicantDrawer` (in the same file or `components.jsx`) — tabs:
  *Evaluation* (per-criterion score with evidence lines and missing items;
  semantic criteria shown separately as "model assessment" with p, passages to
  review, HR confirm/override),
  *Profile* (parsed fields, editable → PATCH), *CV* (download), *Interview*
  (feedback form + previous feedback), *History*.
- `pages/Settings.jsx` — new "Skills taxonomy" section (hr_manager) with a
  "Test on a CV" box that calls `/parse-preview`.
- Dashboard tile: open jobs / new applicants this week (from `/stats`).
- `i18n.js`: all keys EN + AR; RTL already handled by layout.
- Export: Excel of ranked applicants per job (reuse `openpyxl` path used by reports).

Exit criteria: an HR officer can create a job, upload 20 CVs, see them ranked
with reasons, move stages, record interview feedback — without leaving the app.

---

## Phase 4 — Privacy, retention, notifications · done 2026-10-05

Design reviewed with astra (Codex) before implementation; see SECURITY_AUDIT F-23…F-26.

- **Retention clock** (`app/recruitment_privacy.py`): set ONCE when an application
  first becomes `rejected`/`hired` or its job closes — `retention_started_at`,
  `erase_after`, `retention_days_snapshot` (UTC). Re-scoring, edits, reactivation
  and reopening never extend it. At `erase_after` the whole application is
  hard-deleted (children cascade). `ats_retention_days` default 180, 1–365,
  HR Manager; new value applies to clocks started afterwards. No disable toggle.
- **Sweep**: in-app task 60 s after boot and every 6 h (`main.py`), per-row locked
  transactions, failures isolated; `POST /recruitment/retention/run?dry_run=` (dry
  run reads only); last attempt / last success in `ats_retention_last`.
- **Early CV removal** (`POST /applicants/{id}/purge-cv`, reason `withdrawn|manual`,
  HR Manager): clears file, text, parsed, corrections, evidence lines, gate
  failures, source/nationality/city, notes, stage notes, feedback, semantic rows;
  keeps identity, stage and numeric score until `erase_after`. Afterwards: CV 410,
  PATCH/feedback 409, only a move to `rejected` allowed, skipped by re-scoring
  (`score_stale` shown).
- **Erasure request**: `DELETE /applicants/{id}?reason=erasure_request&all_for_email=true`.
  Every expiry / removal / deletion is logged in `ats_privacy_events` (ids only).
- **Notice attestation** (not "consent"): upload requires HR to confirm the
  candidate was given the privacy notice and how (email / WhatsApp / in person /
  other); parse-preview requires the confirmation only. Stored with time, user,
  `NOTICE_VERSION` and the retention days stated in the notice HR sent
  (`notice_retention_days`, sent by the page that produced the notice; today's
  setting if absent) — the clock is capped at that promise. The UI copies
  the bilingual notice text (with the current period) for HR to send.
- **Write safety** (fixed after astra's code review): one cooperating lock for
  upload (re-checks job status + criteria version before insert), close/edit job
  (read-version-write inside the lock), PATCH / re-score publication (applicant
  `row_version` AND job `rubric_version` must be unchanged → 409 `conflict` / row
  skipped), feedback (purge check + insert in one transaction), purge.
- **Candidate emails**: global toggle off by default; per-move opt-in checkbox in
  one shared stage dialog with recipient + message preview; stages interview /
  offer / rejected; EN+AR templates editable by the HR Manager, `{name}`/`{job}`
  only. The message is rendered at confirmation, must match the previewed hash,
  and is stored on the history row; the worker sends the stored text only if the
  row is still the applicant's latest move and the CV was not removed.
  BackgroundTasks send, status pending → sending → accepted|failed|cancelled;
  restart turns pending → cancelled and sending → unknown, never resent. History
  in the UI shows the status.
- API responses never include the CV's full text (`parsed.readable_text` etc.).
  Bulk export is HR Manager only. Email logs mask addresses.
- **Open / not in the app:** HR/legal sign-off on the period and the notice
  text; backup copies and restore-time re-deletion; deleting exports, inbox and
  WhatsApp copies; access/correction requests are handled by HR manually.

---

## Phase 5 — Deploy · ½ day

- Branch `feat/ats` off the deploy head; PR reviewed; `CHANGELOG.md` entry.
- New tables ship through `CREATE TABLE IF NOT EXISTS`; no data migration.
- Add `pypdf`, `python-docx` to `backend/requirements.txt` (Docker image
  +~5 MB). No new services.
- Deploy per `DEPLOY_RUNBOOK.md` (`railway up`; rollback = dashboard redeploy of
  the known-good deployment). Smoke test: create job, upload a CV, view score.

---

## Later (not in this scope)
Public application form (`/apply/<job>` like the customer feedback form),
email-inbox intake, OCR for scanned CVs (Tesseract), Bitrix/LinkedIn import,
embeddings-based similarity if keyword similarity proves too weak.

## Decisions taken
- No generative LLM. The only model is jev (classifier), behind a kill switch,
  shadow-first, on redacted text, after the privacy prerequisites (Phase 1b).
  Every point of `rules_score` has a rule and a quoted line.
- TF-IDF similarity hand-rolled to avoid scikit-learn in the image.
- CVs stored base64 in Postgres like other attachments (volume is small);
  revisit only if applicants exceed a few thousand.
- Scoring is synchronous on upload (< 300 ms); no queue.
