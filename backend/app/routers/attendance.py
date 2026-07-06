import io
import json
import logging
import math
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..auth import (
    ROLE_DEPT_HEAD,
    ROLE_EMPLOYEE,
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    client_ip,
    require_role,
    require_user,
)
from ..db import db
from ..schemas import ClockActionIn, Office, OfficeIn, WebAuthnRegisterIn

logger = logging.getLogger("hr.attendance")

router = APIRouter(prefix="/attendance", tags=["attendance"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)
_manager = require_role(ROLE_HR_MANAGER)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Business-day offset from UTC; KSA is UTC+3. Only used to decide which
# calendar day a punch belongs to — timestamps themselves are stored in UTC.
TZ_OFFSET_MINUTES = int(os.environ.get("ATTENDANCE_TZ_OFFSET_MINUTES", "180"))

# When true (default), clocking in/out demands a WebAuthn (device fingerprint)
# assertion, and requires being inside an office geofence when offices exist.
REQUIRE_BIOMETRIC = os.environ.get("ATTENDANCE_REQUIRE_BIOMETRIC", "true").lower() in ("1", "true", "yes")
REQUIRE_GEOFENCE = os.environ.get("ATTENDANCE_REQUIRE_GEOFENCE", "true").lower() in ("1", "true", "yes")

# GPS accuracy slack added to the geofence radius, capped so a wildly
# inaccurate fix can't bypass the fence.
MAX_ACCURACY_SLACK_M = 100.0

# --- GPS spoof monitoring (advisory only — flags for HR review, never blocks).
# Browser GPS practically never reports sub-metre accuracy; 0/near-0 is the
# tell-tale of a DevTools override or a fake-GPS app.
SUSPICIOUS_ACCURACY_M = 1.0
# Straight-line speed between the in and out punches above which the movement
# is physically implausible (spoofed location on one of the two punches).
MAX_PLAUSIBLE_KMH = 300.0

CHALLENGE_MINUTES = 5
RP_NAME = "Travel Gate HR"


def _rp_id() -> str:
    configured = os.environ.get("WEBAUTHN_RP_ID", "").strip()
    if configured:
        return configured
    base = os.environ.get("APP_BASE_URL", "").strip()
    if base:
        host = urlparse(base).hostname
        if host:
            return host
    return "localhost"


def _expected_origins() -> list[str]:
    origins = set()
    # Local dev origins are only trusted when not running in production
    # (COOKIE_SECURE=true marks prod), so a localhost-issued assertion can't be
    # replayed against the deployed instance.
    if os.environ.get("COOKIE_SECURE", "false").lower() not in ("1", "true", "yes"):
        origins.update({"http://localhost:5173", "http://127.0.0.1:5173"})
    base = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    if base:
        origins.add(base)
    for o in os.environ.get("CORS_ORIGINS", "").split(","):
        o = o.strip().rstrip("/")
        if o:
            origins.add(o)
    return sorted(origins)


def _utcnow() -> datetime:
    # naive UTC (tz stripped) to match the "%Y-%m-%d %H:%M:%S" strings stored in
    # the DB, while avoiding the deprecated datetime.utcnow().
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _work_date(now: datetime) -> str:
    return (now + timedelta(minutes=TZ_OFFSET_MINUTES)).strftime("%Y-%m-%d")


def _check_date(value: Optional[str], name: str) -> None:
    if value and not _DATE_RE.match(value):
        raise HTTPException(400, f"{name} must be formatted YYYY-MM-DD")


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _xlsx_safe(value):
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


# ---------------------------------------------------------------------------
# WebAuthn challenges & credentials
# ---------------------------------------------------------------------------

def _store_challenge(user_id: int, purpose: str, challenge: bytes) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO webauthn_challenges (user_id, purpose, challenge, expires_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, purpose) DO UPDATE SET
                   challenge = excluded.challenge, expires_at = excluded.expires_at""",
            (user_id, purpose, bytes_to_base64url(challenge),
             _fmt(_utcnow() + timedelta(minutes=CHALLENGE_MINUTES))),
        )


def _pop_challenge(user_id: int, purpose: str) -> bytes:
    with db() as conn:
        row = conn.execute(
            "SELECT challenge, expires_at FROM webauthn_challenges WHERE user_id = ? AND purpose = ?",
            (user_id, purpose),
        ).fetchone()
        conn.execute(
            "DELETE FROM webauthn_challenges WHERE user_id = ? AND purpose = ?",
            (user_id, purpose),
        )
    if row is None or row["expires_at"] < _fmt(_utcnow()):
        raise HTTPException(403, "challenge_expired")
    return base64url_to_bytes(row["challenge"])


def _user_credentials(user_id: int) -> list:
    with db() as conn:
        return conn.execute(
            "SELECT * FROM webauthn_credentials WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()


def _verify_clock_assertion(user: CurrentUser, assertion: Optional[dict]) -> bool:
    """Verify the WebAuthn assertion sent with a clock action. Returns True on
    success; raises 403 with a short machine-readable code otherwise."""
    creds = _user_credentials(user.id)
    if not creds:
        raise HTTPException(403, "fingerprint_not_registered")
    if not assertion:
        raise HTTPException(403, "fingerprint_required")

    cred_id = assertion.get("id") or assertion.get("rawId") or ""
    match = next((c for c in creds if c["credential_id"] == cred_id), None)
    if match is None:
        raise HTTPException(403, "unknown_credential")

    expected_challenge = _pop_challenge(user.id, "clock")
    try:
        verified = verify_authentication_response(
            credential=assertion,
            expected_challenge=expected_challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_expected_origins(),
            credential_public_key=base64url_to_bytes(match["public_key"]),
            credential_current_sign_count=match["sign_count"],
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        logger.warning("WebAuthn assertion rejected for user %s: %s", user.email, exc)
        raise HTTPException(403, "fingerprint_failed")
    except Exception as exc:  # malformed client JSON raises assorted errors
        logger.warning("WebAuthn assertion unparseable for user %s: %s", user.email, exc)
        raise HTTPException(403, "fingerprint_failed")
    with db() as conn:
        conn.execute(
            "UPDATE webauthn_credentials SET sign_count = ? WHERE id = ?",
            (verified.new_sign_count, match["id"]),
        )
    return True


# ---------------------------------------------------------------------------
# Geofence
# ---------------------------------------------------------------------------

def _check_geofence(payload: ClockActionIn) -> tuple[str, Optional[float]]:
    """Returns (office_name, distance_m) of the nearest office. Raises 403 when
    geofencing is enforced and the punch is outside every office radius."""
    with db() as conn:
        offices = conn.execute("SELECT * FROM office_locations").fetchall()
    if not offices:
        return "", None
    if payload.lat is None or payload.lng is None:
        if REQUIRE_GEOFENCE:
            raise HTTPException(400, "location_required")
        return "", None

    nearest_name, nearest_dist, within = "", None, False
    for o in offices:
        dist = _haversine_m(payload.lat, payload.lng, o["lat"], o["lng"])
        if nearest_dist is None or dist < nearest_dist:
            nearest_name, nearest_dist = o["name"], dist
        slack = min(payload.accuracy or 0.0, MAX_ACCURACY_SLACK_M)
        if dist <= o["radius_m"] + slack:
            within = True
    if REQUIRE_GEOFENCE and not within:
        raise HTTPException(403, f"outside_geofence:{round(nearest_dist)}")
    return (nearest_name if within else ""), (round(nearest_dist, 1) if nearest_dist is not None else None)


# ---------------------------------------------------------------------------
# WebAuthn registration / authentication ceremonies
# ---------------------------------------------------------------------------

@router.post("/webauthn/register/begin")
def webauthn_register_begin(user: CurrentUser = Depends(require_user)):
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.email,
        user_display_name=user.name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
            for c in _user_credentials(user.id)
        ],
    )
    _store_challenge(user.id, "register", options.challenge)
    return json.loads(options_to_json(options))


@router.post("/webauthn/register/complete", status_code=201)
def webauthn_register_complete(payload: WebAuthnRegisterIn, user: CurrentUser = Depends(require_user)):
    expected_challenge = _pop_challenge(user.id, "register")
    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_expected_origins(),
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        logger.warning("WebAuthn registration rejected for user %s: %s", user.email, exc)
        raise HTTPException(400, "registration_failed")
    except Exception as exc:  # malformed client JSON raises assorted errors
        logger.warning("WebAuthn registration unparseable for user %s: %s", user.email, exc)
        raise HTTPException(400, "registration_failed")

    transports = ",".join(payload.credential.get("response", {}).get("transports") or [])
    with db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO webauthn_credentials
               (user_id, credential_id, public_key, sign_count, transports, device_label, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user.id,
                bytes_to_base64url(verified.credential_id),
                bytes_to_base64url(verified.credential_public_key),
                verified.sign_count,
                transports,
                payload.device_label.strip(),
                _fmt(_utcnow()),
            ),
        )
    return {"registered": True}


@router.get("/webauthn/credentials")
def list_credentials(user: CurrentUser = Depends(require_user)):
    return [
        {"id": c["id"], "device_label": c["device_label"], "created_at": c["created_at"]}
        for c in _user_credentials(user.id)
    ]


@router.delete("/webauthn/credentials/{cid}", status_code=204)
def delete_credential(cid: int, user: CurrentUser = Depends(require_user)):
    with db() as conn:
        conn.execute(
            "DELETE FROM webauthn_credentials WHERE id = ? AND user_id = ?", (cid, user.id)
        )


@router.post("/webauthn/clock/begin")
def webauthn_clock_begin(user: CurrentUser = Depends(require_user)):
    creds = _user_credentials(user.id)
    if not creds:
        raise HTTPException(403, "fingerprint_not_registered")
    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"])) for c in creds
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _store_challenge(user.id, "clock", options.challenge)
    return json.loads(options_to_json(options))


# ---------------------------------------------------------------------------
# Office locations (geofence anchors)
# ---------------------------------------------------------------------------

@router.get("/offices", response_model=list[Office])
def list_offices(_: CurrentUser = Depends(_hr_staff)):
    with db() as conn:
        rows = conn.execute("SELECT id, name, lat, lng, radius_m FROM office_locations ORDER BY name").fetchall()
        return [dict(r) for r in rows]


@router.post("/offices", response_model=Office, status_code=201)
def create_office(payload: OfficeIn, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO office_locations (name, lat, lng, radius_m, created_at)
               VALUES (?, ?, ?, ?, ?) RETURNING id, name, lat, lng, radius_m""",
            (payload.name, payload.lat, payload.lng, payload.radius_m, _fmt(_utcnow())),
        )
        return dict(cur.fetchone())


@router.delete("/offices/{oid}", status_code=204)
def delete_office(oid: int, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        conn.execute("DELETE FROM office_locations WHERE id = ?", (oid,))


# ---------------------------------------------------------------------------
# Clock in / out
# ---------------------------------------------------------------------------

def _today_row(conn, user_id: int, work_date: str):
    return conn.execute(
        "SELECT * FROM attendance WHERE user_id = ? AND work_date = ?", (user_id, work_date)
    ).fetchone()


@router.get("/me")
def my_status(user: CurrentUser = Depends(require_user)):
    now = _utcnow()
    work_date = _work_date(now)
    with db() as conn:
        today = _today_row(conn, user.id, work_date)
        offices = conn.execute("SELECT COUNT(*) FROM office_locations").fetchone()[0]
    return {
        "work_date": work_date,
        "today": _without_ip(dict(today)) if today else None,
        "has_credential": bool(_user_credentials(user.id)),
        "require_biometric": REQUIRE_BIOMETRIC,
        "require_geofence": REQUIRE_GEOFENCE and offices > 0,
    }


def _without_ip(row: dict) -> dict:
    row.pop("clock_in_ip", None)
    row.pop("clock_out_ip", None)
    return row


@router.post("/clock-in", status_code=201)
def clock_in(payload: ClockActionIn, request: Request, user: CurrentUser = Depends(require_user)):
    now = _utcnow()
    work_date = _work_date(now)
    with db() as conn:
        if _today_row(conn, user.id, work_date) is not None:
            raise HTTPException(409, "already_clocked_in")

    # Geofence first: it's read-only, so a location failure won't have consumed
    # the WebAuthn challenge or bumped the credential's sign counter.
    office, distance = _check_geofence(payload)
    verified = _verify_clock_assertion(user, payload.assertion) if REQUIRE_BIOMETRIC else False

    try:
        with db() as conn:
            cur = conn.execute(
                """INSERT INTO attendance
                   (user_id, work_date, clock_in_at, clock_in_lat, clock_in_lng, clock_in_accuracy,
                    clock_in_office, clock_in_distance_m, clock_in_verified, clock_in_ip)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
                (user.id, work_date, _fmt(now), payload.lat, payload.lng, payload.accuracy,
                 office, distance, int(verified), client_ip(request)),
            )
            return _without_ip(dict(cur.fetchone()))
    except sqlite3.IntegrityError:
        # two punches raced past the existence check; UNIQUE(user_id, work_date) wins
        raise HTTPException(409, "already_clocked_in")


@router.post("/clock-out")
def clock_out(payload: ClockActionIn, request: Request, user: CurrentUser = Depends(require_user)):
    now = _utcnow()
    work_date = _work_date(now)
    with db() as conn:
        row = _today_row(conn, user.id, work_date)
    if row is None:
        raise HTTPException(409, "not_clocked_in")

    office, distance = _check_geofence(payload)
    verified = _verify_clock_assertion(user, payload.assertion) if REQUIRE_BIOMETRIC else False

    # Re-clocking out is allowed: the last punch of the day wins.
    with db() as conn:
        cur = conn.execute(
            """UPDATE attendance SET
                 clock_out_at = ?, clock_out_lat = ?, clock_out_lng = ?, clock_out_accuracy = ?,
                 clock_out_office = ?, clock_out_distance_m = ?, clock_out_verified = ?, clock_out_ip = ?
               WHERE id = ? RETURNING *""",
            (_fmt(now), payload.lat, payload.lng, payload.accuracy,
             office, distance, int(verified), client_ip(request), row["id"]),
        )
        return _without_ip(dict(cur.fetchone()))


# ---------------------------------------------------------------------------
# Records & export
# ---------------------------------------------------------------------------

def _worked_hours(row: dict) -> Optional[float]:
    if not row.get("clock_out_at"):
        return None
    try:
        t_in = datetime.strptime(row["clock_in_at"], "%Y-%m-%d %H:%M:%S")
        t_out = datetime.strptime(row["clock_out_at"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    return round(max((t_out - t_in).total_seconds(), 0) / 3600, 2)


def _risk(row: dict) -> dict:
    """Advisory GPS-spoof signals for a punch, for HR to review. Never blocks —
    location is client-supplied and can't be trusted absolutely; these are just
    tell-tales worth a second look. Returns {level, reasons[]}."""
    reasons: list[str] = []
    for side in ("clock_in", "clock_out"):
        lat, lng = row.get(f"{side}_lat"), row.get(f"{side}_lng")
        acc = row.get(f"{side}_accuracy")
        if lat is None or lng is None:
            continue
        if acc is None:
            reasons.append("no_accuracy")
        elif acc <= SUSPICIOUS_ACCURACY_M:
            reasons.append("zero_accuracy")

    have_both = all(
        row.get(k) is not None
        for k in ("clock_in_lat", "clock_in_lng", "clock_out_lat", "clock_out_lng", "clock_out_at")
    )
    if have_both:
        try:
            t_in = datetime.strptime(row["clock_in_at"], "%Y-%m-%d %H:%M:%S")
            t_out = datetime.strptime(row["clock_out_at"], "%Y-%m-%d %H:%M:%S")
            hours = (t_out - t_in).total_seconds() / 3600
            dist_km = _haversine_m(
                row["clock_in_lat"], row["clock_in_lng"],
                row["clock_out_lat"], row["clock_out_lng"],
            ) / 1000
            if (hours > 0 and dist_km / hours > MAX_PLAUSIBLE_KMH) or (hours <= 0 and dist_km > 1):
                reasons.append("impossible_travel")
        except (ValueError, TypeError):
            pass

    reasons = list(dict.fromkeys(reasons))  # de-dupe, keep order
    strong = {"zero_accuracy", "impossible_travel"}
    level = "high" if strong.intersection(reasons) else ("low" if reasons else "none")
    return {"level": level, "reasons": reasons}


MAX_PAGE_SIZE = 200


def _build_filters(user: CurrentUser, employee: Optional[str], date_from: Optional[str], date_to: Optional[str]):
    _check_date(date_from, "date_from")
    _check_date(date_to, "date_to")
    clauses = ["1=1"]
    params: list = []
    # Horizontal access control mirrors the violations router: employees see
    # only themselves, department heads only their department.
    if user.role == ROLE_EMPLOYEE:
        clauses.append("a.user_id = ?")
        params.append(user.id)
    elif user.role == ROLE_DEPT_HEAD:
        clauses.append("u.department = ?")
        params.append(user.department)
    if employee and user.role in (ROLE_HR_MANAGER, ROLE_HR_OFFICER, ROLE_DEPT_HEAD):
        clauses.append("(u.name LIKE ? OR u.email LIKE ?)")
        params.extend([f"%{employee}%", f"%{employee}%"])
    if date_from:
        clauses.append("a.work_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("a.work_date <= ?")
        params.append(date_to)
    return " AND ".join(clauses), params


def _fetch_records(where: str, params: list, limit: Optional[int] = None, offset: int = 0):
    sql = (
        "SELECT a.*, u.name, u.email, u.department FROM attendance a "
        f"JOIN users u ON u.id = a.user_id WHERE {where} "
        "ORDER BY a.work_date DESC, a.clock_in_at DESC"
    )
    q_params = list(params)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        q_params += [limit, offset]
    with db() as conn:
        rows = [dict(r) for r in conn.execute(sql, q_params).fetchall()]
    for r in rows:
        r["worked_hours"] = _worked_hours(r)
        r["risk"] = _risk(r)
    return rows


@router.get("")
def list_attendance(
    employee: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(require_user),
):
    where, params = _build_filters(user, employee, date_from, date_to)
    with db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM attendance a JOIN users u ON u.id = a.user_id WHERE {where}",
            params,
        ).fetchone()[0]
    rows = _fetch_records(where, params, limit=limit, offset=offset)
    for r in rows:
        # IPs are audit data — kept for the HR-only export, not the list UI.
        r.pop("clock_in_ip", None)
        r.pop("clock_out_ip", None)
        # Don't reveal spoof flags to an employee viewing their own record.
        if user.role == ROLE_EMPLOYEE:
            r.pop("risk", None)
    return {"rows": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/export")
def export_attendance(
    employee: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: CurrentUser = Depends(_hr_staff),
):
    where, params = _build_filters(user, employee, date_from, date_to)
    rows = _fetch_records(where, params)
    offset = timedelta(minutes=TZ_OFFSET_MINUTES)

    def local(ts: Optional[str]) -> str:
        if not ts:
            return ""
        try:
            return _fmt(datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + offset)
        except ValueError:
            return ts

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append([
        "Date", "Employee", "Email", "Department", "Clock In", "Clock Out",
        "Hours", "Office (In)", "Office (Out)", "Fingerprint In", "Fingerprint Out",
        "Risk", "Risk Reasons", "IP (In)", "IP (Out)",
    ])
    for r in rows:
        risk = r.get("risk") or {"level": "none", "reasons": []}
        ws.append([
            r["work_date"], _xlsx_safe(r["name"]), _xlsx_safe(r["email"]), _xlsx_safe(r["department"]),
            local(r["clock_in_at"]), local(r["clock_out_at"]),
            r["worked_hours"] if r["worked_hours"] is not None else "",
            _xlsx_safe(r["clock_in_office"]), _xlsx_safe(r["clock_out_office"]),
            "yes" if r["clock_in_verified"] else "no",
            "yes" if r["clock_out_verified"] else "no",
            risk["level"], ", ".join(risk["reasons"]),
            _xlsx_safe(r.get("clock_in_ip", "")), _xlsx_safe(r.get("clock_out_ip", "")),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
