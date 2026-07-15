import logging
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import (
    ROLE_HR_MANAGER,
    ROLE_HR_OFFICER,
    CurrentUser,
    require_role,
)
from ..db import db
from ..expiry import ATTENTION_STATUSES, compute_status as _status
from ..schemas import DOCUMENT_CATEGORIES, DocumentIn, DocumentUpdateIn

logger = logging.getLogger("hr.documents")

router = APIRouter(prefix="/documents", tags=["documents"])

_hr_staff = require_role(ROLE_HR_MANAGER, ROLE_HR_OFFICER)
_manager = require_role(ROLE_HR_MANAGER)


def _now() -> datetime:
    return datetime.now()


def _public(row: dict) -> dict:
    """A document record without the heavy/private attachment bytes, plus its
    computed expiry status."""
    return {
        "id": row["id"],
        "category": row["category"],
        "owner": row["owner"],
        "title": row["title"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "note": row["note"],
        "has_attachment": bool(row["attachment"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        **_status(row["end_date"]),
    }


@router.get("")
def list_documents(
    category: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    _: CurrentUser = Depends(_hr_staff),
):
    """List tracked documents, newest expiry first. Filter by category and/or
    owner. Attachment bytes are omitted — fetch one via /{id}/attachment."""
    if category is not None and category not in DOCUMENT_CATEGORIES:
        raise HTTPException(400, "unsupported document category")

    clauses, params = [], []
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if owner is not None:
        clauses.append("owner = ?")
        params.append(owner)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM documents {where} ORDER BY end_date ASC, id DESC",
            params,
        ).fetchall()
    return [_public(dict(r)) for r in rows]


# Categories shown on the "Employee Documents" page; the rest are company docs.
_EMPLOYEE_CATEGORIES = {"iqama", "contract"}


@router.get("/expiring")
def expiring_documents(_: CurrentUser = Depends(_hr_staff)):
    """Everything that needs attention (yellow / red / expired), most urgent
    first, plus counts. Powers the dashboard widget and the sidebar badges."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM documents").fetchall()

    items = []
    for r in rows:
        pub = _public(dict(r))
        if pub["status"] in ATTENTION_STATUSES:
            items.append(pub)
    # Most urgent first: fewest days left (expired = negative) leads.
    items.sort(key=lambda d: (d["days_left"] if d["days_left"] is not None else 1 << 30))

    counts = {"yellow": 0, "red": 0, "expired": 0}
    scope = {"employee": 0, "company": 0}
    for d in items:
        counts[d["status"]] += 1
        scope["employee" if d["category"] in _EMPLOYEE_CATEGORIES else "company"] += 1
    counts["total"] = len(items)
    return {"counts": counts, "by_scope": scope, "items": items}


@router.post("", status_code=201)
def create_document(payload: DocumentIn, user: CurrentUser = Depends(_hr_staff)):
    with db() as conn:
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
            return _public(dict(cur.fetchone()))
        except sqlite3.IntegrityError:
            # Hit the (owner, category) slot uniqueness for iqama/contract/rent —
            # a record already exists; the caller should renew it (PATCH) instead.
            raise HTTPException(409, "slot_exists")


@router.patch("/{did}")
def update_document(did: int, payload: DocumentUpdateIn, _: CurrentUser = Depends(_hr_staff)):
    fields = payload.model_dump(exclude_unset=True)
    with db() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (did,)).fetchone()
        if row is None:
            raise HTTPException(404, "Document not found")

        merged = dict(row)
        for key in ("title", "start_date", "end_date", "note",
                    "attachment", "attachment_name", "attachment_mime"):
            if key in fields:
                merged[key] = fields[key]
        # If the attachment is cleared, drop its metadata too.
        if fields.get("attachment") == "":
            merged["attachment_name"] = ""
            merged["attachment_mime"] = ""
        if merged["end_date"] < merged["start_date"]:
            raise HTTPException(400, "end_date must be on or after start_date")

        cur = conn.execute(
            """UPDATE documents SET
                   title = ?, start_date = ?, end_date = ?, note = ?,
                   attachment = ?, attachment_name = ?, attachment_mime = ?
               WHERE id = ? RETURNING *""",
            (
                merged["title"], merged["start_date"], merged["end_date"], merged["note"],
                merged["attachment"], merged["attachment_name"], merged["attachment_mime"],
                did,
            ),
        )
        return _public(dict(cur.fetchone()))


@router.delete("/{did}", status_code=204)
def delete_document(did: int, _: CurrentUser = Depends(_manager)):
    with db() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (did,))


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
