import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from ..auth import (
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    require_role,
)
from ..db import IntegrityError, db
from ..doc_config import ALERT_ELIGIBLE_SQL, load_thresholds, thresholds_for
from ..expiry import ATTENTION_STATUSES, compute_status
from ..schemas import DOCUMENT_CATEGORIES, DocumentIn, DocumentUpdateIn

logger = logging.getLogger("hr.documents")

router = APIRouter(prefix="/documents", tags=["documents"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)
_manager = require_role(ROLE_HR_MANAGER)

# Categories shown on the "Employee Documents" page; the rest are company docs.
_EMPLOYEE_CATEGORIES = {"iqama", "contract"}
_COMPANY_CATEGORIES = {"rent", "vehicle", "license"}
# One-per-owner categories, guarded by the partial unique index in db.py. Their
# owner identifies the slot, so it can be corrected but never blanked.
_SLOT_CATEGORIES = {"iqama", "contract", "rent"}


def _now() -> datetime:
    return datetime.now()


# Columns for list/summary reads — everything _public needs EXCEPT the heavy
# base64 attachment, which is fetched on demand via /{id}/attachment. Selecting
# the blob for every row bloated dashboard/list reads (up to ~5 MB per row).
_LIST_COLUMNS = (
    "id, category, owner, title, start_date, end_date, note, "
    "(attachment != '') AS has_attachment, attachment_name, created_by, created_at"
)


def _status_for(row: dict, tmap: dict) -> dict:
    yellow, red = thresholds_for(row["category"], tmap)
    return compute_status(row["end_date"], yellow, red)


def _has_attachment(row: dict) -> bool:
    # List queries select a lightweight `has_attachment` flag; create/patch use
    # RETURNING * which still carries the raw `attachment` column.
    return bool(row["has_attachment"]) if "has_attachment" in row else bool(row.get("attachment"))


def _public(row: dict, tmap: dict, is_manager: bool = False) -> dict:
    """A document record without the heavy/private attachment bytes, plus its
    computed expiry status (using the category's thresholds).

    `attachment_name` rides the same HR-manager gate as the attachment itself:
    a file name ("ahmed-medical-report.pdf") leaks what the file contains, so
    officers — who get 403 from /{id}/attachment — must not read it either.
    They still see `has_attachment`, which is all the UI needs from them."""
    return {
        "id": row["id"],
        "category": row["category"],
        "owner": row["owner"],
        "title": row["title"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "note": row["note"],
        "has_attachment": _has_attachment(row),
        "attachment_name": row["attachment_name"] if is_manager else "",
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        **_status_for(row, tmap),
    }


def _xlsx_safe(value):
    """Neutralise Excel formula injection: a cell starting with =, +, -, @ or a
    control char would otherwise be evaluated as a formula when opened."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@router.get("/expiring")
def expiring_documents(user: CurrentUser = Depends(_hr_staff)):
    """Everything that needs attention (yellow / red / expired), most urgent
    first, plus counts. Powers the dashboard widget and the sidebar badges."""
    with db() as conn:
        tmap = load_thresholds(conn)
        rows = conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM documents WHERE {ALERT_ELIGIBLE_SQL}"
        ).fetchall()

    items = []
    for r in rows:
        pub = _public(dict(r), tmap, user.role == ROLE_HR_MANAGER)
        if pub["status"] in ATTENTION_STATUSES:
            items.append(pub)
    items.sort(key=lambda d: (d["days_left"] if d["days_left"] is not None else 1 << 30))

    counts = {"yellow": 0, "red": 0, "expired": 0}
    scope = {"employee": 0, "company": 0}
    for d in items:
        counts[d["status"]] += 1
        scope["employee" if d["category"] in _EMPLOYEE_CATEGORIES else "company"] += 1
    counts["total"] = len(items)
    return {"counts": counts, "by_scope": scope, "items": items}


def _query_rows(conn, category: Optional[str], owner: Optional[str], scope: Optional[str]):
    clauses, params = [], []
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if owner is not None:
        clauses.append("owner = ?")
        params.append(owner)
    if scope in ("employee", "company"):
        cats = _EMPLOYEE_CATEGORIES if scope == "employee" else _COMPANY_CATEGORIES
        clauses.append(f"category IN ({','.join('?' * len(cats))})")
        params.extend(sorted(cats))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(
        f"SELECT {_LIST_COLUMNS} FROM documents {where} ORDER BY end_date ASC, id DESC", params
    ).fetchall()


@router.get("")
def list_documents(
    category: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    user: CurrentUser = Depends(_hr_staff),
):
    """List tracked documents, soonest expiry first. Filter by category, owner
    and/or scope (employee | company). Attachment bytes are omitted."""
    if category is not None and category not in DOCUMENT_CATEGORIES:
        raise HTTPException(400, "unsupported document category")
    with db() as conn:
        tmap = load_thresholds(conn)
        rows = _query_rows(conn, category, owner, scope)
    is_manager = user.role == ROLE_HR_MANAGER
    return [_public(dict(r), tmap, is_manager) for r in rows]


@router.get("/export")
def export_documents(
    category: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    _: CurrentUser = Depends(_hr_staff),
):
    """Excel export of the (optionally filtered) documents, with computed status."""
    if category is not None and category not in DOCUMENT_CATEGORIES:
        raise HTTPException(400, "unsupported document category")
    with db() as conn:
        tmap = load_thresholds(conn)
        rows = _query_rows(conn, category, owner, scope)

    wb = Workbook()
    ws = wb.active
    ws.title = "Documents"
    ws.append(["Category", "Owner", "Title", "Start Date", "End Date",
               "Status", "Days Left", "Note", "Created By", "Created At"])
    for r in rows:
        d = dict(r)
        st = _status_for(d, tmap)
        ws.append([
            d["category"], _xlsx_safe(d["owner"]), _xlsx_safe(d["title"]),
            d["start_date"], d["end_date"], st["status"], st["days_left"],
            _xlsx_safe(d["note"]), _xlsx_safe(d["created_by"]), d["created_at"],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", status_code=201)
def create_document(payload: DocumentIn, user: CurrentUser = Depends(_hr_staff)):
    with db() as conn:
        tmap = load_thresholds(conn)
        try:
            cur = conn.execute(
                """INSERT INTO documents
                   (category, owner, title, start_date, end_date, note,
                    attachment, attachment_name, attachment_mime, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
                (
                    payload.category, payload.owner, payload.title,
                    payload.start_date, payload.end_date, payload.note,
                    payload.attachment, payload.attachment_name, payload.attachment_mime,
                    user.name, _now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            return _public(dict(cur.fetchone()), tmap, user.role == ROLE_HR_MANAGER)
        except IntegrityError:
            # Hit the (owner, category) slot uniqueness for iqama/contract/rent —
            # a record already exists; the caller should renew it (PATCH) instead.
            raise HTTPException(409, "slot_exists")


@router.patch("/{did}")
def update_document(did: int, payload: DocumentUpdateIn, user: CurrentUser = Depends(_hr_staff)):
    fields = payload.model_dump(exclude_unset=True)
    with db() as conn:
        tmap = load_thresholds(conn)
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (did,)).fetchone()
        if row is None:
            raise HTTPException(404, "Document not found")

        # Replacing or clearing an existing attachment destroys a file the
        # officer isn't even allowed to open (attachment view is manager-only),
        # so it rides the same gate. Adding one where none exists stays open to
        # all HR staff — nothing is hidden or lost by that.
        touches_attachment = any(
            k in fields for k in ("attachment", "attachment_name", "attachment_mime")
        )
        if touches_attachment and row["attachment"] and user.role != ROLE_HR_MANAGER:
            raise HTTPException(403, "attachment_locked")

        merged = dict(row)
        for key in ("owner", "title", "start_date", "end_date", "note",
                    "attachment", "attachment_name", "attachment_mime"):
            if key in fields:
                merged[key] = fields[key]
        # If the attachment is cleared, drop its metadata too.
        if fields.get("attachment") == "":
            merged["attachment_name"] = ""
            merged["attachment_mime"] = ""
        if merged["end_date"] < merged["start_date"]:
            raise HTTPException(400, "end_date must be on or after start_date")
        if row["category"] in _SLOT_CATEGORIES and not merged["owner"]:
            raise HTTPException(400, "owner_required")

        # One audit row per edit that moves the record: a renewal (new validity
        # dates), a reassignment (new owner), or both at once. Cosmetic edits
        # (title/note/attachment) leave no trace, as before.
        # Unchanged sides are written as "" so a reader can tell which kind of
        # change it was by comparing old/new — including an owner cleared to "".
        dates_changed = (merged["start_date"] != row["start_date"]
                         or merged["end_date"] != row["end_date"])
        owner_changed = merged["owner"] != row["owner"]
        if dates_changed or owner_changed:
            conn.execute(
                """INSERT INTO document_history
                   (document_id, old_start, old_end, new_start, new_end,
                    old_owner, new_owner, changed_by, changed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (did, row["start_date"], row["end_date"], merged["start_date"], merged["end_date"],
                 row["owner"] if owner_changed else "", merged["owner"] if owner_changed else "",
                 user.name, _now().strftime("%Y-%m-%d %H:%M:%S")),
            )

        try:
            cur = conn.execute(
                """UPDATE documents SET
                       owner = ?, title = ?, start_date = ?, end_date = ?, note = ?,
                       attachment = ?, attachment_name = ?, attachment_mime = ?
                   WHERE id = ? RETURNING *""",
                (
                    merged["owner"], merged["title"], merged["start_date"], merged["end_date"],
                    merged["note"], merged["attachment"], merged["attachment_name"],
                    merged["attachment_mime"], did,
                ),
            )
        except IntegrityError:
            # Moving a slot record onto an owner who already has one of this
            # category — same collision the create path reports.
            raise HTTPException(409, "slot_exists")
        return _public(dict(cur.fetchone()), tmap, user.role == ROLE_HR_MANAGER)


@router.get("/{did}/history")
def document_history(did: int, _: CurrentUser = Depends(_hr_staff)):
    """Past renewals (date changes) for a document, newest first."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM document_history WHERE document_id = ? ORDER BY id DESC", (did,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.delete("/{did}", status_code=204)
def delete_document(did: int, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (did,))
        conn.execute("DELETE FROM document_history WHERE document_id = ?", (did,))


@router.get("/{did}/attachment")
def get_attachment(did: int, _: CurrentUser = Depends(_manager)):
    """Fetch a document's attachment (base64). HR Manager only — same gate the
    early-leave permission attachments sit behind."""
    with db() as conn:
        row = conn.execute(
            "SELECT attachment, attachment_name, attachment_mime FROM documents WHERE id = ?",
            (did,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Document not found")
    if not row["attachment"]:
        raise HTTPException(404, "No attachment")
    return {
        "id": did,
        "attachment": row["attachment"],
        "attachment_name": row["attachment_name"],
        "attachment_mime": row["attachment_mime"] or "application/octet-stream",
    }
