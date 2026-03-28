
# =============================================================
# HR Disciplinary Management System — Clean Production v3.0
# =============================================================
# Single-file Streamlit app. SQLite only. No Google Sheets.
# Phases covered:
#   1 – SQLite-only, GSheets fully removed
#   2 – Bug fixes & stability
#   3 – Refactor & cleanup
#   4 – Core features verified
#   5 – Audit trail (submitted_by column)
#   6 – Final clean version
# =============================================================

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG  (must be the very first Streamlit call)
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HR Disciplinary System",
    page_icon="⚖️",
    layout="wide",
)


# =============================================================
# SECTION 1 — CONSTANTS & CONFIGURATION
# =============================================================

# ── Penalty colour → consequence mapping ─────────────────────
# deduction_days supports 0, 0.5, 2, 4  (stored as REAL in DB)
PENALTY_MAP: dict[str, dict] = {
    "Yellow": {
        "label":           "Performance Notice",
        "deduction_hours": 0.0,
        "deduction_days":  0.0,
        "freeze_months":   0,
        "badge":           "🟡",
    },
    "Orange": {
        "label":           "Performance Flag — 4.5 hrs (Half Day) Deduction",
        "deduction_hours": 4.5,
        "deduction_days":  0.5,   # FIX: was 0 in v1
        "freeze_months":   0,
        "badge":           "🟠",
    },
    "Red": {
        "label":           "Performance Alert — 2 Days Deduction",
        "deduction_hours": 0.0,
        "deduction_days":  2.0,
        "freeze_months":   0,
        "badge":           "🔴",
    },
    "Black": {
        "label":           "Performance Warning — 4 Days Deduction + 3-Month Freeze",
        "deduction_hours": 0.0,
        "deduction_days":  4.0,
        "freeze_months":   3,
        "badge":           "⬛",
    },
    "Investigation": {
        "label":           "Suspended — Transferred to Investigation on Spot",
        "deduction_hours": 0.0,
        "deduction_days":  0.0,
        "freeze_months":   0,
        "badge":           "🔍",
    },
}

# ── Violation matrix (mirrors the Excel requirements sheet) ──
MATRIX_DATA: dict[str, dict] = {
    "Attendance & Adherence": {
        "Late Arrival": {
            "reset": 30,
            "escalation": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"],
            "details": "Arriving late to work.",
            "hr_note": "Time deduction required. Manager alignment is mandatory; "
                       "failure to align escalates to the next level.",
        },
        "No-Show": {
            "reset": 90,
            "escalation": ["Red", "Red", "Black", "Investigation"],
            "details": "Missing a scheduled shift without prior notification.",
        },
        "Exceed Breaks": {
            "reset": 30,
            "escalation": [
                "Yellow", "Yellow", "Yellow", "Yellow",
                "Orange", "Red", "Black", "Investigation",
            ],
            "details": "Taking longer breaks than the permitted duration.",
        },
        "Unscheduled Breaks": {
            "reset": 30,
            "escalation": ["Yellow", "Red", "Black", "Investigation"],
            "details": "Taking breaks at unauthorised times.",
        },
        "Out-of-Hours Attendance": {
            "reset": 90,
            "escalation": ["Yellow", "Red", "Black", "Investigation"],
            "details": "Remaining in the workplace beyond the end of a shift without approval.",
        },
        "Attendance Manipulation": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Falsifying or manipulating attendance records.",
        },
        "Early Leave": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Leaving work before end of shift without approval.",
        },
    },
    "Personal Attitude": {
        "Use of Abusive Words": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Using offensive or disrespectful language.",
        },
        "Physical Harm": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Causing physical harm to any person on company premises.",
        },
        "Sleeping on the Job": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Sleeping in the workplace during working hours.",
        },
        "Unprofessional Behaviour": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Conduct that is inappropriate for a professional workplace.",
        },
    },
    "Abusing": {
        "Company Assets": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Damaging or misusing company property.",
        },
        "Routing Calls / Tickets": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Avoiding or incorrectly redirecting assigned calls or tickets.",
        },
        "Releasing Calls / Tickets": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Closing assigned work items without completing them.",
        },
        "Using Colleague Logins": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Sharing or using another employee's login credentials.",
        },
        "Aux System Abuse": {
            "reset": 30,
            "escalation": ["Yellow", "Yellow", "Orange", "Red", "Black", "Investigation"],
            "details": "Misusing auxiliary systems, reports, or tools.",
        },
    },
    "Policy Violations": {
        "Refusing Medical Examination": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Refusing to undergo a required medical examination.",
        },
        "Unauthorised Visitors": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Meeting personal visitors in unauthorised areas.",
        },
        "Smoking in Prohibited Areas": {
            "reset": 180,
            "escalation": ["Black", "Investigation"],
            "details": "Smoking in areas where it is strictly prohibited.",
        },
        "Alcohol / Drug Influence": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Being under the influence of alcohol or drugs at work.",
        },
        "Harassment": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Engaging in any form of harassment towards colleagues or customers.",
        },
        "Theft": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Taking company or personal property without permission.",
        },
        "Social Media Misuse": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Using social media in a way that damages the company's reputation.",
        },
        "Data Confidentiality Breach": {
            "reset": 180,
            "escalation": ["Investigation"],
            "details": "Unauthorised data sharing, unethical conduct, or actions causing reputational damage.",
        },
        "Personal Mobile Phone Use": {
            "reset": 30,
            "escalation": ["Red", "Black", "Investigation"],
            "details": "Using personal mobile phones for non-work purposes during working hours.",
        },
        "Food & Beverage in Prohibited Areas": {
            "reset": 30,
            "escalation": ["Orange", "Red", "Black", "Investigation"],
            "details": "Eating or drinking in areas where it is not permitted.",
        },
        "Business Process Failure": {
            "reset": 30,
            "escalation": ["Orange", "Red", "Black", "Investigation"],
            "details": "Repeated or severe violation of a critical business process.",
        },
        "End-User Critical Failure": {
            "reset": 60,
            "escalation": ["Black", "Investigation"],
            "details": "Severe failure directly impacting end-users (e.g. payouts, customer attitude).",
        },
        "Cyber Security Breach": {
            "reset": 30,
            "escalation": ["Red", "Black", "Investigation"],
            "details": "Downloading unauthorised software, bypassing security, or sharing restricted links.",
        },
    },
}

# ── Secrets (safe defaults for local dev without secrets.toml) ──
def _secret(key: str, default: str = "") -> str:
    """Read from st.secrets without raising KeyError."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return default


SENDER_EMAIL      = _secret("EMAIL")
SENDER_PASSWORD   = _secret("PASSWORD")
HR_MANAGER_EMAIL  = _secret("HR_MANAGER_EMAIL", SENDER_EMAIL)
HR_ADMIN_PASSWORD = _secret("HR_ADMIN_PASSWORD", "admin123")


# =============================================================
# SECTION 2 — DATABASE LAYER  (SQLite only)
# =============================================================

DB_FILE = "hr_system.db"


@contextmanager
def _db():
    """
    Context manager that yields a committed-or-rolled-back connection.
    Always closes the connection, even on exception.
    """
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Create tables and run lightweight schema migrations.
    Safe to call on every app startup — all operations are idempotent.

    Migrations handled:
      • Add submitted_by column if upgrading from an older schema.
      • Recreate violations table if deduction_days was stored as INTEGER
        (needed to support the 0.5 value for Orange penalties).
    """
    with _db() as conn:
        # ── Create tables ────────────────────────────────
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    UNIQUE NOT NULL,
                email         TEXT    NOT NULL,
                department    TEXT    DEFAULT '',
                manager_email TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS violations (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                employee_name   TEXT     NOT NULL,
                category        TEXT     NOT NULL,
                incident        TEXT     NOT NULL,
                penalty_color   TEXT     NOT NULL,
                penalty_label   TEXT     NOT NULL,
                deduction_hours REAL     DEFAULT 0.0,
                deduction_days  REAL     DEFAULT 0.0,
                freeze_months   INTEGER  DEFAULT 0,
                comment         TEXT     DEFAULT '',
                submitted_by    TEXT     NOT NULL DEFAULT '',
                created_at      DATETIME NOT NULL
            );
        """)

        # ── Migration 1: add submitted_by if missing ──────
        existing_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(violations)")
        }
        if "submitted_by" not in existing_cols:
            conn.execute(
                "ALTER TABLE violations "
                "ADD COLUMN submitted_by TEXT NOT NULL DEFAULT ''"
            )

        # ── Migration 2: fix INTEGER → REAL for deduction_days ──
        col_types = {
            r[1]: r[2].upper()
            for r in conn.execute("PRAGMA table_info(violations)")
        }
        if col_types.get("deduction_days", "REAL") == "INTEGER":
            conn.executescript("""
                ALTER TABLE violations RENAME TO violations_v1;

                CREATE TABLE violations (
                    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                    employee_name   TEXT     NOT NULL,
                    category        TEXT     NOT NULL,
                    incident        TEXT     NOT NULL,
                    penalty_color   TEXT     NOT NULL,
                    penalty_label   TEXT     NOT NULL,
                    deduction_hours REAL     DEFAULT 0.0,
                    deduction_days  REAL     DEFAULT 0.0,
                    freeze_months   INTEGER  DEFAULT 0,
                    comment         TEXT     DEFAULT '',
                    submitted_by    TEXT     NOT NULL DEFAULT '',
                    created_at      DATETIME NOT NULL
                );

                INSERT INTO violations
                SELECT
                    id, employee_name, category, incident,
                    penalty_color, penalty_label,
                    CAST(deduction_hours AS REAL),
                    CAST(deduction_days  AS REAL),
                    freeze_months, comment,
                    COALESCE(submitted_by, ''),
                    created_at
                FROM violations_v1;

                DROP TABLE violations_v1;
            """)


# ── Employee CRUD ─────────────────────────────────────────────

def get_employees() -> pd.DataFrame:
    with _db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM employees ORDER BY name", conn
        )


def save_employee(
    name: str, email: str, dept: str, manager: str
) -> None:
    """Insert or update employee by name (UNIQUE constraint)."""
    with _db() as conn:
        conn.execute(
            """INSERT INTO employees (name, email, department, manager_email)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   email         = excluded.email,
                   department    = excluded.department,
                   manager_email = excluded.manager_email""",
            (name, email, dept, manager),
        )


def delete_employee(name: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM employees WHERE name = ?", (name,))


# ── Violation CRUD ────────────────────────────────────────────

def insert_violation(
    emp_name: str,
    category: str,
    incident: str,
    penalty_color: str,
    comment: str,
    submitted_by: str,
) -> None:
    """
    Persist a new violation.
    All derived fields (label, deductions, freeze) come from PENALTY_MAP,
    never from the UI — prevents data inconsistency.
    """
    p = PENALTY_MAP[penalty_color]
    with _db() as conn:
        conn.execute(
            """INSERT INTO violations
               (employee_name, category, incident, penalty_color, penalty_label,
                deduction_hours, deduction_days, freeze_months,
                comment, submitted_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                emp_name, category, incident,
                penalty_color, p["label"],
                p["deduction_hours"], p["deduction_days"], p["freeze_months"],
                comment, submitted_by,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )


def delete_violation(vid: int) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM violations WHERE id = ?", (vid,))


def get_violations(
    employee:  str | None = None,
    date_from: datetime | None = None,
    date_to:   datetime | None = None,
    incident:  str | None = None,
    penalty:   str | None = None,
) -> pd.DataFrame:
    """
    Parameterised, filtered query.
    Pass None for any field to skip that filter.
    'All' sentinel is handled by the callers — they pass None here.
    """
    clauses: list[str] = ["1=1"]
    params:  list      = []

    if employee:
        clauses.append("employee_name = ?")
        params.append(employee)
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from.strftime("%Y-%m-%d 00:00:00"))
    if date_to:
        clauses.append("created_at <= ?")
        params.append(date_to.strftime("%Y-%m-%d 23:59:59"))
    if incident:
        clauses.append("incident = ?")
        params.append(incident)
    if penalty:
        clauses.append("penalty_color = ?")
        params.append(penalty)

    sql = (
        f"SELECT * FROM violations "
        f"WHERE {' AND '.join(clauses)} "
        f"ORDER BY created_at DESC"
    )

    with _db() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    # Guarantee numeric dtypes even when result is empty
    for col in ("deduction_hours", "deduction_days", "freeze_months"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


# =============================================================
# SECTION 3 — BUSINESS LOGIC
# =============================================================

def calculate_next_penalty(
    emp_name: str, category: str, incident: str
) -> str:
    """
    Determine the correct next penalty colour for this employee + incident.

    Algorithm:
      1. Count violations within the incident's reset window.
      2. Skip terminal 'Investigation' violations (they don't escalate).
      3. Index into the escalation list; cap at the last entry if exhausted.
    """
    meta       = MATRIX_DATA[category][incident]
    escalation = meta["escalation"]
    reset_days = meta["reset"]
    cutoff     = (
        datetime.now() - timedelta(days=reset_days)
    ).strftime("%Y-%m-%d %H:%M:%S")

    with _db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM violations
               WHERE employee_name = ?
                 AND incident      = ?
                 AND created_at   >= ?
                 AND penalty_color != 'Investigation'""",
            (emp_name, incident, cutoff),
        ).fetchone()

    count = row[0] if row else 0
    index = min(count, len(escalation) - 1)   # never raises IndexError
    return escalation[index]


# =============================================================
# SECTION 4 — EMAIL SERVICE
# =============================================================

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(addr: str) -> bool:
    return bool(_EMAIL_REGEX.match(addr.strip()))


def send_notifications(
    emp_email:     str,
    manager_email: str,
    emp_name:      str,
    category:      str,
    incident:      str,
    penalty_color: str,
    comment:       str,
) -> tuple[bool, str]:
    """
    Send disciplinary emails to the employee and their manager.

    Returns (success: bool, message: str).
    Pure logic — no Streamlit calls, making it testable in isolation.

    Investigation triggers:
      • Suspension email to employee.
      • Manager email CC'd to HR Director.
    """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return False, "Email credentials missing in secrets.toml."

    p         = PENALTY_MAP[penalty_color]
    is_invest = penalty_color == "Investigation"

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
            srv.login(SENDER_EMAIL, SENDER_PASSWORD)

            # ── 1. Employee notification ─────────────────
            if _valid_email(emp_email):
                msg = MIMEMultipart()
                msg["From"]    = SENDER_EMAIL
                msg["To"]      = emp_email
                msg["Subject"] = (
                    f"URGENT: Suspension Notice — {emp_name}"
                    if is_invest
                    else f"Disciplinary Action: {p['badge']} {penalty_color} Card"
                )
                if is_invest:
                    body = (
                        f"Dear {emp_name},\n\n"
                        f"You are hereby SUSPENDED pending an investigation.\n\n"
                        f"  Incident : {incident} ({category})\n"
                        f"  HR Notes : {comment}\n\n"
                        f"HR will contact you with further instructions.\n"
                        f"Do NOT report to the office until notified."
                    )
                else:
                    body = (
                        f"Dear {emp_name},\n\n"
                        f"A disciplinary action has been recorded on your file:\n\n"
                        f"  Incident : {incident} ({category})\n"
                        f"  Penalty  : {p['label']}\n"
                        f"  HR Notes : {comment}\n\n"
                        f"Please adhere to company policies to avoid further escalation.\n\n"
                        f"Human Resources Department"
                    )
                msg.attach(MIMEText(body, "plain", "utf-8"))
                srv.sendmail(SENDER_EMAIL, [emp_email], msg.as_string())

            # ── 2. Manager notification ──────────────────
            if manager_email and _valid_email(manager_email):
                mgr = MIMEMultipart()
                mgr["From"]    = SENDER_EMAIL
                mgr["To"]      = manager_email
                mgr["Subject"] = (
                    f"🚨 URGENT: Employee Suspended — {emp_name}"
                    if is_invest
                    else f"Manager Notice — {emp_name} | {p['badge']} {penalty_color}"
                )
                mgr_body = (
                    f"Dear Manager,\n\n"
                    f"Your team member {emp_name} has received a disciplinary penalty.\n\n"
                    f"  Incident : {incident} ({category})\n"
                    f"  Penalty  : {p['label']}\n"
                    f"  Notes    : {comment}\n"
                )
                if is_invest:
                    mgr_body += (
                        "\n\n🚨 IMPORTANT: This employee is SUSPENDED. "
                        "Do NOT allow them on-site until HR clearance is issued."
                    )
                    # Deduplicate in case manager IS the HR director
                    recipients = list({manager_email, HR_MANAGER_EMAIL} - {""})
                else:
                    recipients = [manager_email]

                mgr.attach(MIMEText(mgr_body, "plain", "utf-8"))
                srv.sendmail(SENDER_EMAIL, recipients, mgr.as_string())

        return True, "Emails sent successfully."

    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed — check EMAIL / PASSWORD in secrets."
    except smtplib.SMTPException as exc:
        return False, f"SMTP error: {exc}"
    except OSError as exc:
        return False, f"Network error: {exc}"


# =============================================================
# SECTION 5 — AUTHENTICATION
# =============================================================

def require_auth(page_key: str) -> bool:
    """
    Show a password form and return True when authenticated.

    FIX: Per-page state keys (auth_tab2, auth_tab3 are independent).
    The old shared 'authenticated' key let Tab-2 auth also unlock Tab-3.
    FIX: Never calls st.stop() — callers use `if not require_auth(): pass`.
    """
    state_key = f"auth_{page_key}"
    if st.session_state.get(state_key):
        return True

    st.markdown("### 🔑 HR Access Required")
    with st.form(f"login_{page_key}"):
        pwd    = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

    if submit:
        if pwd == HR_ADMIN_PASSWORD:
            st.session_state[state_key] = True
            st.rerun()
        else:
            st.error("❌ Incorrect password.")

    return False


def _logout_button(page_key: str) -> None:
    _, btn_col = st.columns([9, 1])
    if btn_col.button("Logout", key=f"logout_{page_key}"):
        st.session_state[f"auth_{page_key}"] = False
        st.rerun()


# =============================================================
# SECTION 6 — SHARED UI HELPERS
# =============================================================

def _kpi_row(df: pd.DataFrame) -> None:
    """Four summary metric cards shown above the charts."""
    today = datetime.now()

    # Count employees whose most recent Black-level freeze is still active
    def _active_freeze(sub: pd.DataFrame) -> bool:
        frozen = sub[sub["freeze_months"] > 0]
        if frozen.empty:
            return False
        last = frozen.loc[frozen["created_at"].idxmax()]
        end  = pd.to_datetime(last["created_at"]) + pd.DateOffset(
            months=int(last["freeze_months"])
        )
        return end.to_pydatetime() > today

    active_freezes = (
        df.groupby("employee_name")
          .apply(_active_freeze)
          .sum()
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Violations",       len(df))
    k2.metric("Unique Employees",        df["employee_name"].nunique())
    k3.metric("Total Deduction Days",    f"{df['deduction_days'].sum():.1f}")
    k4.metric("Active Promotion Freezes", int(active_freezes))


# =============================================================
# SECTION 7 — APP BOOTSTRAP
# =============================================================

init_db()

st.title("⚖️ HR Disciplinary Management System")

tab_log, tab_admin, tab_reports = st.tabs([
    "📝 Log Violation",
    "⚙️ Admin Dashboard",
    "📊 Reports & Analytics",
])


# =============================================================
# TAB 1 — LOG VIOLATION
# =============================================================
with tab_log:
    employees_df = get_employees()

    if employees_df.empty:
        st.warning(
            "⚠️ No employees found. "
            "Please add employees in the **Admin Dashboard** tab first."
        )
    else:
        st.subheader("Register New Violation")

        # Dynamic dropdowns — OUTSIDE the form so the incident list
        # refreshes immediately when the category changes.
        col_cat, col_inc = st.columns(2)
        with col_cat:
            category = st.selectbox(
                "Violation Category",
                list(MATRIX_DATA.keys()),
                key="t1_cat",
            )
        with col_inc:
            incident = st.selectbox(
                "Incident Type",
                list(MATRIX_DATA[category].keys()),
                key="t1_inc",
            )

        inc_meta   = MATRIX_DATA[category][incident]
        escalation = inc_meta["escalation"]
        reset_days = inc_meta["reset"]
        details    = inc_meta.get("details", "")
        hr_note    = inc_meta.get("hr_note", "")

        with st.expander("ℹ️ Incident Reference", expanded=True):
            d1, d2 = st.columns(2)
            d1.info(f"**Details:** {details}")
            d2.info(
                f"**Reset Window:** {reset_days} days  "
                f"|  **Max Steps:** {len(escalation)}"
            )
            if hr_note:
                st.warning(f"📌 **HR Note:** {hr_note}")
            path_str = "  →  ".join(
                f"{PENALTY_MAP[p]['badge']} {p}" for p in escalation
            )
            st.write(f"**Escalation path:** {path_str}")

        # Stable form fields — only submitted when the button is clicked.
        with st.form("violation_form", clear_on_submit=True):
            f1, f2 = st.columns(2)
            with f1:
                emp_name = st.selectbox(
                    "Employee *", employees_df["name"].tolist()
                )
                submitted_by = st.text_input(
                    "HR Representative Name *",
                    help="Name of the HR staff member logging this violation. "
                         "Stored as the Audit Trail entry.",
                )
            with f2:
                comment = st.text_area(
                    "HR Comments / Alignment Notes",
                    height=130,
                    help="Include contextual notes, manager alignment details, "
                         "or any mitigating factors.",
                )

            do_submit = st.form_submit_button(
                "✅ Submit & Notify", use_container_width=True
            )

        if do_submit:
            if not submitted_by.strip():
                st.error(
                    "⚠️ **HR Representative Name** is required. "
                    "This field is the system's audit trail."
                )
            else:
                penalty_color = calculate_next_penalty(
                    emp_name, category, incident
                )
                p_info  = PENALTY_MAP[penalty_color]
                emp_row = employees_df[
                    employees_df["name"] == emp_name
                ].iloc[0]

                # Persist to DB first — data is safe even if email fails.
                insert_violation(
                    emp_name, category, incident,
                    penalty_color, comment, submitted_by.strip(),
                )

                # Send notifications
                email_ok, email_msg = send_notifications(
                    str(emp_row["email"]),
                    str(emp_row["manager_email"] or ""),
                    emp_name, category, incident,
                    penalty_color, comment,
                )

                # ── Outcome feedback ──────────────────────
                badge = p_info["badge"]
                if email_ok:
                    st.success(
                        f"{badge} Penalty recorded: **{p_info['label']}** "
                        f"— Notifications sent."
                    )
                else:
                    st.warning(
                        f"{badge} Penalty recorded: **{p_info['label']}** "
                        f"— Email skipped: {email_msg}"
                    )

                if penalty_color == "Investigation":
                    st.error(
                        "🚨 **INVESTIGATION TRIGGERED**  \n"
                        "The employee must be suspended immediately. "
                        "Escalate to the HR Director and do **not** allow "
                        "the employee on-site."
                    )
                elif p_info["deduction_days"] > 0:
                    hrs = (
                        f" ({p_info['deduction_hours']} hrs)"
                        if p_info["deduction_hours"] > 0 else ""
                    )
                    st.info(
                        f"💰 **Payroll:** {p_info['deduction_days']} day(s)"
                        f" deduction{hrs} must be applied."
                    )

                if p_info["freeze_months"] > 0:
                    until = (
                        datetime.now()
                        + timedelta(days=30 * p_info["freeze_months"])
                    ).strftime("%d %b %Y")
                    st.warning(
                        f"🔒 **Promotion freeze** active until **{until}** "
                        f"({p_info['freeze_months']} months)."
                    )


# =============================================================
# TAB 2 — ADMIN DASHBOARD
# =============================================================
with tab_admin:
    if not require_auth("tab2"):
        pass   # Login form already rendered by require_auth
    else:
        _logout_button("tab2")
        st.subheader("👥 Employee Management")

        # ── Add / Update Employee ─────────────────────────
        with st.form("add_emp_form", clear_on_submit=True):
            a1, a2 = st.columns(2)
            with a1:
                e_name  = st.text_input("Full Name *")
                e_email = st.text_input("Email Address *")
            with a2:
                e_dept    = st.text_input("Department")
                e_manager = st.text_input("Manager Email (CC on penalties)")

            if st.form_submit_button("💾 Save Employee"):
                errors: list[str] = []
                if not e_name.strip():
                    errors.append("Employee name is required.")
                if not e_email.strip():
                    errors.append("Email address is required.")
                elif not _valid_email(e_email.strip()):
                    errors.append("Email address format is invalid.")
                if e_manager.strip() and not _valid_email(e_manager.strip()):
                    errors.append("Manager email format is invalid.")

                if errors:
                    for err in errors:
                        st.error(f"⚠️ {err}")
                else:
                    save_employee(
                        e_name.strip(), e_email.strip(),
                        e_dept.strip(), e_manager.strip(),
                    )
                    st.success(f"✅ Employee **{e_name.strip()}** saved.")
                    st.rerun()

        # ── Employee List ─────────────────────────────────
        emp_df = get_employees()
        if not emp_df.empty:
            st.dataframe(
                emp_df[["name", "email", "department", "manager_email"]],
                use_container_width=True,
            )
            del_name = st.selectbox(
                "Select employee to remove:",
                ["— select —"] + emp_df["name"].tolist(),
                key="del_emp_sel",
            )
            if del_name != "— select —":
                if st.button("🗑️ Delete Employee", key="del_emp_btn"):
                    delete_employee(del_name)
                    st.success(f"Employee **{del_name}** removed.")
                    st.rerun()
        else:
            st.info("No employees yet. Use the form above to add one.")

        st.divider()

        # ── Violation Records (admin view) ────────────────
        st.subheader("🗂️ Violation Records")
        v_all = get_violations()

        if not v_all.empty:
            st.dataframe(
                v_all[[
                    "id", "employee_name", "incident",
                    "penalty_color", "deduction_days",
                    "submitted_by", "created_at",
                ]],
                use_container_width=True,
            )
            del_id = st.selectbox(
                "Select Record ID to delete:",
                v_all["id"].tolist(),
                key="del_v_sel",
            )
            if st.button("🗑️ Delete Violation Record", key="del_v_btn"):
                delete_violation(int(del_id))
                st.success(f"Record **{del_id}** deleted.")
                st.rerun()
        else:
            st.info("No violations logged yet.")


# =============================================================
# TAB 3 — REPORTS & ANALYTICS
# =============================================================
with tab_reports:
    if not require_auth("tab3"):
        pass   # Login form already rendered by require_auth
    else:
        _logout_button("tab3")
        st.header("📊 HR Reports & Analytics")

        # ── Filters ───────────────────────────────────────
        with st.expander("🔍 Filters", expanded=True):
            fi1, fi2, fi3, fi4 = st.columns([2, 3, 2, 2])

            all_names = ["All"] + sorted(
                get_employees()["name"].tolist()
            )
            all_incidents = ["All"] + sorted(
                inc
                for cat in MATRIX_DATA.values()
                for inc in cat
            )
            all_penalties = ["All"] + list(PENALTY_MAP.keys())

            with fi1:
                f_emp = st.selectbox(
                    "Employee Name", all_names, key="r_emp"
                )

            with fi2:
                fc1, fc2 = st.columns(2)
                with fc1:
                    f_from = st.date_input(
                        "From",
                        value=datetime.now().date() - timedelta(days=90),
                        key="r_from",
                    )
                with fc2:
                    f_to = st.date_input(
                        "To",
                        value=datetime.now().date(),
                        key="r_to",
                    )

            with fi3:
                f_inc = st.selectbox(
                    "Incident Type", all_incidents, key="r_inc"
                )

            with fi4:
                f_pen = st.selectbox(
                    "Penalty Level", all_penalties, key="r_pen"
                )

        # Validate date range — no st.stop() inside a tab.
        if f_from > f_to:
            st.error("⚠️ 'From' date must be before or equal to 'To' date.")
        else:
            df = get_violations(
                employee  = None if f_emp == "All" else f_emp,
                date_from = datetime.combine(f_from, datetime.min.time()),
                date_to   = datetime.combine(f_to,   datetime.max.time()),
                incident  = None if f_inc == "All" else f_inc,
                penalty   = None if f_pen == "All" else f_pen,
            )

            if df.empty:
                st.info("ℹ️ No violations match the selected filters.")
            else:
                df["created_at"] = pd.to_datetime(df["created_at"])

                # ── KPI row ───────────────────────────────
                _kpi_row(df)
                st.divider()

                # ── Chart row 1 ───────────────────────────
                ch1, ch2 = st.columns(2)

                with ch1:
                    fig_pie = px.pie(
                        df,
                        names="category",
                        title="Violations by Category",
                        color_discrete_sequence=px.colors.qualitative.Set2,
                    )
                    fig_pie.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                    )
                    fig_pie.update_layout(showlegend=False)
                    st.plotly_chart(fig_pie, use_container_width=True)

                with ch2:
                    emp_cnt = (
                        df["employee_name"]
                        .value_counts()
                        .reset_index()
                    )
                    emp_cnt.columns = ["Employee", "Count"]
                    fig_emp_bar = px.bar(
                        emp_cnt,
                        x="Employee",
                        y="Count",
                        title="Violations per Employee",
                        color="Count",
                        color_continuous_scale="Reds",
                    )
                    fig_emp_bar.update_layout(
                        showlegend=False,
                        xaxis_tickangle=-30,
                        coloraxis_showscale=False,
                    )
                    st.plotly_chart(fig_emp_bar, use_container_width=True)

                # ── Date bar chart (Feature B) ────────────
                st.subheader("📅 Violations Over Time")
                df["date_only"] = df["created_at"].dt.date
                daily = (
                    df.groupby("date_only")
                    .size()
                    .reset_index(name="count")
                )
                daily["date_only"] = pd.to_datetime(daily["date_only"])

                fig_time = px.bar(
                    daily,
                    x="date_only",
                    y="count",
                    title="Daily Violation Count",
                    labels={"date_only": "Date", "count": "Violations"},
                    color_discrete_sequence=["#EF553B"],
                )
                fig_time.update_layout(
                    bargap=0.25,
                    xaxis_tickformat="%d %b %Y",
                    xaxis_title="Date",
                    yaxis_title="Violations",
                )
                st.plotly_chart(fig_time, use_container_width=True)

                # ── Chart row 2 ───────────────────────────
                ch3, ch4 = st.columns(2)

                _PENALTY_COLOUR_MAP = {
                    "Yellow":        "#FFD700",
                    "Orange":        "#FF8C00",
                    "Red":           "#DC143C",
                    "Black":         "#444444",
                    "Investigation": "#7B2FBE",
                }

                with ch3:
                    pen_cnt = (
                        df["penalty_color"].value_counts().reset_index()
                    )
                    pen_cnt.columns = ["Penalty", "Count"]
                    fig_pen = px.bar(
                        pen_cnt,
                        x="Penalty",
                        y="Count",
                        title="Violations by Penalty Level",
                        color="Penalty",
                        color_discrete_map=_PENALTY_COLOUR_MAP,
                    )
                    fig_pen.update_layout(showlegend=False)
                    st.plotly_chart(fig_pen, use_container_width=True)

                with ch4:
                    inc_cnt = (
                        df["incident"]
                        .value_counts()
                        .head(10)
                        .reset_index()
                    )
                    inc_cnt.columns = ["Incident", "Count"]
                    fig_inc = px.bar(
                        inc_cnt,
                        x="Count",
                        y="Incident",
                        orientation="h",
                        title="Top 10 Incidents",
                        color_discrete_sequence=["#636EFA"],
                    )
                    fig_inc.update_layout(
                        yaxis={"categoryorder": "total ascending"}
                    )
                    st.plotly_chart(fig_inc, use_container_width=True)

                st.divider()

                # ── History table with deduction days ────
                # (Feature C — includes Submitted By audit trail column)
                st.subheader("📋 Violation History — Full Detail")

                today_d = date.today()

                df_disp = df.copy()
                df_disp["freeze_end_date"] = df_disp.apply(
                    lambda r: (
                        r["created_at"]
                        + pd.DateOffset(months=int(r["freeze_months"]))
                    ).date()
                    if r["freeze_months"] > 0 else None,
                    axis=1,
                )
                df_disp["Currently Frozen"] = df_disp[
                    "freeze_end_date"
                ].apply(
                    lambda d: "🔒 Yes"
                    if (d is not None and d > today_d)
                    else "✅ No"
                )

                # Column selection and renaming
                _cols = {
                    "employee_name":    "Employee",
                    "category":         "Category",
                    "incident":         "Incident",
                    "penalty_color":    "Penalty",
                    "penalty_label":    "Penalty Description",
                    "deduction_hours":  "Deduction (hrs)",
                    "deduction_days":   "Deduction (days)",
                    "freeze_end_date":  "Freeze Until",
                    "Currently Frozen": "Currently Frozen",
                    "submitted_by":     "Submitted By",   # ← Audit Trail
                    "created_at":       "Date & Time",
                }
                hist_df = df_disp[list(_cols.keys())].rename(columns=_cols)
                st.dataframe(hist_df, use_container_width=True, height=420)

                # ── Payroll summary per employee ──────────
                st.subheader("💰 Payroll Deduction Summary")

                def _active_freeze_label(emp: str) -> str:
                    sub = df[
                        (df["employee_name"] == emp) & (df["freeze_months"] > 0)
                    ]
                    if sub.empty:
                        return "✅ No"
                    latest_idx = sub["created_at"].idxmax()
                    months     = int(sub.at[latest_idx, "freeze_months"])
                    end        = (
                        sub.at[latest_idx, "created_at"]
                        + pd.DateOffset(months=months)
                    ).date()
                    return "🔒 Yes" if end > today_d else "✅ No"

                payroll = (
                    df.groupby("employee_name")
                    .agg(
                        Violations      =("id",              "count"),
                        Deduction_Hours =("deduction_hours", "sum"),
                        Deduction_Days  =("deduction_days",  "sum"),
                    )
                    .reset_index()
                    .rename(columns={"employee_name": "Employee"})
                )
                payroll["Active Freeze"] = payroll["Employee"].apply(
                    _active_freeze_label
                )
                st.dataframe(payroll, use_container_width=True)

                # ── CSV export ────────────────────────────
                csv_bytes = hist_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 Export Filtered Report (CSV)",
                    data=csv_bytes,
                    file_name=(
                        f"hr_report_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                    ),
                    mime="text/csv",
                    use_container_width=True,
                )
