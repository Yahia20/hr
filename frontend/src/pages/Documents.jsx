import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, BtnPri, BtnSec, Th, FG, inp, chipBtn } from "../components";
import { Modal, ConfirmModal } from "../modal";
import { useToast } from "../toast";
import { exportDocumentsPdf } from "../pdf";

const ALLOWED = ["image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"];
const EMPTY_FILE = { name: "", b64: "", mime: "" };
const today = () => new Date().toISOString().slice(0, 10);
const plusYear = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
};

// Traffic-light palette keyed by the server-computed status.
const STATUS_STYLE = {
  green: { bg: S.okL, fg: S.ok, dot: S.ok },
  yellow: { bg: S.warnL, fg: S.warn, dot: S.warn },
  red: { bg: S.errL, fg: S.err, dot: S.err },
  expired: { bg: S.errL, fg: S.err, dot: S.err },
  unknown: { bg: S.g100, fg: S.g500, dot: S.g300 },
};
const STATUS_KEY = { green: "stGreen", yellow: "stYellow", red: "stRed", expired: "stExpired", unknown: "stUnknown" };

// Category → i18n key for a short chip label (iqama/contract reuse their own keys).
export const CATEGORY_LABEL_KEY = { iqama: "iqama", contract: "contract", rent: "catRent", vehicle: "catVehicle", license: "catLicense" };
const RENT_LABEL_KEY = { rawda: "rentRawda", hamra: "rentHamra", housing: "rentHousing" };

// A friendly headline for a document row, whatever its category.
export function docPrimaryLabel(t, doc) {
  if (doc.category === "iqama" || doc.category === "contract") return doc.owner || doc.title;
  if (doc.category === "rent") return t(RENT_LABEL_KEY[doc.owner] || "tabRents");
  return doc.title || doc.owner;
}

export function daysText(t, doc) {
  const n = doc.days_left;
  if (n === null || n === undefined) return "";
  if (doc.status === "expired") return t("expiredAgoN").replace("{n}", Math.abs(n));
  if (n === 0) return t("expiresTodayL");
  return t("expiresInN").replace("{n}", n);
}

// Hijri (Umm al-Qura) rendering of a YYYY-MM-DD date — relevant for KSA iqamas.
export function hijri(dateStr, ar) {
  if (!dateStr) return "";
  try {
    const locale = ar ? "ar-SA-u-ca-islamic-umalqura" : "en-US-u-ca-islamic-umalqura";
    return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${dateStr}T00:00:00`));
  } catch {
    return "";
  }
}

// A document flattened into the labelled shape the PDF export expects.
function toPdfRow(t, ar, d) {
  return {
    primary: docPrimaryLabel(t, d),
    category: t(CATEGORY_LABEL_KEY[d.category] || d.category),
    start: d.start_date,
    end: d.end_date,
    status: d.status,
    statusLabel: t(STATUS_KEY[d.status] || "stUnknown"),
    days: daysText(t, d),
    hijri: hijri(d.end_date, ar),
  };
}

function ExportBar({ t, onExcel, onPdf }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <BtnSec onClick={onExcel}>{IC.dl} <span>{t("export")}</span></BtnSec>
      <BtnSec onClick={onPdf}>{IC.dl} <span>{t("exportPdf")}</span></BtnSec>
    </div>
  );
}

function HistoryModal({ open, doc, t, ar, onClose }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if (!doc) { setRows(null); return; }
    setRows(null);
    api.documentHistory(doc.id).then(setRows).catch(() => setRows([]));
  }, [doc]);
  return (
    <Modal open={open} onClose={onClose} title={`${t("history")} — ${doc ? docPrimaryLabel(t, doc) : ""}`}>
      {rows === null ? (
        <div style={{ padding: 8, color: S.g400 }}>…</div>
      ) : rows.length === 0 ? (
        <Empty text={t("noHistory")} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 8 }}>
          {rows.map((h) => (
            <div key={h.id} style={{ padding: "10px 12px", borderRadius: S.r2, border: `1px solid ${S.g100}`, background: S.g50 }}>
              {/* An entry is a renewal, a reassignment, or both — show each part
                  only when that side actually changed. */}
              {h.old_end !== h.new_end && (
                <div style={{ direction: "ltr", fontSize: 13, fontWeight: 600, color: S.g700, textAlign: ar ? "right" : "left" }}>
                  {h.old_end} → {h.new_end}
                </div>
              )}
              {h.old_owner !== h.new_owner && (
                <div style={{ fontSize: 13, fontWeight: 600, color: S.g700 }}>
                  {t("docOwner")}: {h.old_owner || "—"} → {h.new_owner || "—"}
                </div>
              )}
              <div style={{ fontSize: 11.5, color: S.g400, marginTop: 3 }}>{h.changed_by} · {h.changed_at}</div>
            </div>
          ))}
        </div>
      )}
      <div style={{ textAlign: "end" }}>
        <BtnSec onClick={onClose}><span>{t("close")}</span></BtnSec>
      </div>
    </Modal>
  );
}

export function ExpiryBadge({ t, doc }) {
  const st = STATUS_STYLE[doc.status] || STATUS_STYLE.unknown;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: S.rF, background: st.bg, color: st.fg, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: st.dot }} />
      {t(STATUS_KEY[doc.status] || "stUnknown")}
    </span>
  );
}

// The shared add/edit form. `ctx` describes the target slot/list item. Once a
// record exists every field is correctable — name, who it belongs to, the dates,
// the note, and the attachment (keep / replace / remove). Changing an existing
// attachment is manager-only (mirrors the backend gate); officers can still
// attach a file where none exists.
function DocModal({ open, ctx, isManager, onClose, onSaved, t, ar }) {
  const [form, setForm] = useState({ title: "", owner: "", start: today(), end: plusYear(), note: "", file: EMPTY_FILE, dropAttach: false });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!ctx) return;
    const d = ctx.doc;
    setErr(null);
    setForm({
      title: d?.title ?? ctx.title ?? "",
      owner: d?.owner ?? ctx.owner ?? "",
      start: d?.start_date ?? today(),
      end: d?.end_date ?? plusYear(),
      note: d?.note ?? "",
      file: EMPTY_FILE,
      dropAttach: false,
    });
  }, [ctx]);

  if (!ctx) return null;

  // Reassigning only makes sense once the record exists: on create the owner is
  // already fixed by the row/slot the user clicked.
  const ownerEditable = Boolean(ctx.doc && ctx.ownerOptions?.length);
  const hasAttach = Boolean(ctx.doc?.has_attachment) && !form.dropAttach && !form.file.b64;
  // Officers may add a first attachment but not replace/remove an existing one.
  const attachEditable = isManager || !ctx.doc?.has_attachment;

  function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) { setForm((f) => ({ ...f, file: EMPTY_FILE })); return; }
    if (!ALLOWED.includes(file.type)) { setErr(t("errFileType")); return; }
    if (file.size > 5 * 1024 * 1024) { setErr(ar ? "الحجم أكبر من 5MB" : "File exceeds 5MB"); return; }
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, file: { name: file.name, b64: String(reader.result).split(",")[1] || "", mime: file.type }, dropAttach: false }));
    reader.readAsDataURL(file);
    setErr(null);
  }

  async function save() {
    if (form.end < form.start) { setErr(ar ? "تاريخ النهاية قبل البداية" : "End date is before start date"); return; }
    if (ctx.titleEditable && !form.title.trim()) { setErr(ar ? "الاسم مطلوب" : "Name is required"); return; }
    if (ownerEditable && !form.owner) { setErr(ar ? "اختر صاحب المستند" : "Choose who this belongs to"); return; }
    setSaving(true);
    setErr(null);
    try {
      // A new file replaces the old one; "remove" clears it (the server drops the
      // stored name/type too). Neither touched → the attachment is left alone.
      const attach = form.file.b64
        ? { attachment: form.file.b64, attachment_name: form.file.name, attachment_mime: form.file.mime }
        : form.dropAttach ? { attachment: "" } : {};
      if (ctx.doc) {
        await api.updateDocument(ctx.doc.id, {
          title: form.title, start_date: form.start, end_date: form.end, note: form.note,
          ...(ownerEditable ? { owner: form.owner } : {}),
          ...attach,
        });
      } else {
        await api.createDocument({ category: ctx.category, owner: ctx.owner || "", title: form.title, start_date: form.start, end_date: form.end, note: form.note, ...attach });
      }
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.message === "slot_exists" ? t("errSlotExists")
        : e?.message === "attachment_locked" ? t("attachLocked")
        : e?.message || t("errGeneric"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={ctx.heading}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
        {ownerEditable && (
          <FG label={ctx.ownerLabel || t("docOwner")}>
            <select style={{ ...inp, cursor: "pointer" }} value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })}>
              {ctx.ownerOptions.some((o) => o.value === form.owner) ? null : <option value={form.owner}>{form.owner}</option>}
              {ctx.ownerOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </FG>
        )}
        {ctx.titleEditable && (
          <FG label={ctx.titleLabel || t("docTitle")}>
            <input style={inp} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder={ctx.titleLabel || t("docTitle")} />
          </FG>
        )}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <FG label={t("startDate")}><input style={{ ...inp, minWidth: 150 }} type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></FG>
          <FG label={t("endDate")}><input style={{ ...inp, minWidth: 150 }} type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></FG>
        </div>
        <FG label={t("docNote")}>
          <textarea style={{ ...inp, resize: "vertical", minHeight: 54 }} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </FG>
        <FG label={t("attach")}>
          {hasAttach && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", marginBottom: 8, borderRadius: S.r2, border: `1px solid ${S.g100}`, background: S.g50, fontSize: 12.5, color: S.g500 }}>
              {IC.clip}
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {/* The name is manager-only; officers just see that a file is there. */}
                {t("currentFile")}: {ctx.doc.attachment_name || t("attach")}
              </span>
              {isManager && <button onClick={() => setForm({ ...form, dropAttach: true })} style={chipBtn(S.err)}>{t("removeAttach")}</button>}
            </div>
          )}
          {form.dropAttach && !form.file.b64 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, fontSize: 12.5, color: S.err }}>
              <span style={{ flex: 1 }}>{t("attachRemoved")}</span>
              <button onClick={() => setForm({ ...form, dropAttach: false })} style={chipBtn(S.g500)}>{t("undo")}</button>
            </div>
          )}
          {attachEditable ? (
            <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: S.r2, border: `1.5px dashed ${S.g300}`, cursor: "pointer", background: S.g50, fontSize: 13, color: S.g500 }}>
              {IC.upload}
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{form.file.name || t("chooseFile")}</span>
              <input type="file" accept="image/*,application/pdf" onChange={onFile} style={{ display: "none" }} />
            </label>
          ) : (
            <div style={{ fontSize: 12, color: S.g400 }}>{t("attachLocked")}</div>
          )}
        </FG>
      </div>
      {err && <div style={{ color: S.err, fontSize: 13, marginBottom: 12 }}>{err}</div>}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
        <BtnSec onClick={onClose}><span>{t("cancel")}</span></BtnSec>
        <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{saving ? "…" : t("save")}</span></BtnPri>
      </div>
    </Modal>
  );
}

// A cell/row rendering a single tracked document (or an "add" prompt when empty).
function DocLine({ t, ar, doc, isManager, onAdd, onEdit, onView, onDelete, onHistory, busyAttach }) {
  if (!doc) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ color: S.g400, fontSize: 13 }}>{t("notSet")}</span>
        <button onClick={onAdd} style={chipBtn(S.pri)}>{IC.plus} <span>{t("addDoc")}</span></button>
      </div>
    );
  }
  const hj = hijri(doc.end_date, ar);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <ExpiryBadge t={t} doc={doc} />
      <span style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.25 }}>
        <span style={{ direction: "ltr", fontWeight: 600, color: S.g700, fontSize: 12.5, textAlign: ar ? "right" : "left" }}>{doc.end_date}</span>
        {hj && <span style={{ fontSize: 10.5, color: S.g400 }}>{hj}</span>}
      </span>
      <span style={{ color: S.g400, fontSize: 12 }}>{daysText(t, doc)}</span>
      {/* Same form renews and corrects, so it's labelled "Edit". */}
      <button onClick={onEdit} style={chipBtn(S.info)}>{t("editDoc")}</button>
      {onHistory && <button onClick={onHistory} title={t("history")} style={chipBtn(S.g500)}>{t("history")}</button>}
      {doc.has_attachment && isManager && (
        <button onClick={onView} disabled={busyAttach === doc.id} title={t("viewAttach")} style={chipBtn(S.info)}>{IC.clip} <span>{t("attach")}</span></button>
      )}
      {doc.has_attachment && !isManager && (
        <span style={{ display: "inline-flex", alignItems: "center", color: S.g400 }}>{IC.clip}</span>
      )}
      {isManager && <button onClick={onDelete} title={t("del")} style={chipBtn(S.err)}>{t("del")}</button>}
    </div>
  );
}

// Shared state/handlers for a page that manages documents.
function useDocs() {
  const toast = useToast();
  const [busyAttach, setBusyAttach] = useState(null);
  async function viewAttachment(id, tt) {
    setBusyAttach(id);
    try {
      const a = await api.documentAttachment(id);
      const bytes = Uint8Array.from(atob(a.attachment), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: a.attachment_mime }));
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      toast("err", e?.message || tt("errGeneric"));
    } finally {
      setBusyAttach(null);
    }
  }
  return { toast, busyAttach, viewAttachment };
}

// ─────────────────────────────────────────────────────────────────────────────
// Employee Documents: one iqama + one contract per employee.
// ─────────────────────────────────────────────────────────────────────────────
export function EmployeeDocs({ lang, user, onChanged }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isManager = user?.role === "hr_manager";
  const { toast, busyAttach, viewAttachment } = useDocs();

  const [employees, setEmployees] = useState(null);
  const [iqamas, setIqamas] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [ctx, setCtx] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [histDoc, setHistDoc] = useState(null);

  async function load() {
    try {
      const [emps, iq, ct] = await Promise.all([
        api.listEmployees(),
        api.listDocuments({ category: "iqama" }),
        api.listDocuments({ category: "contract" }),
      ]);
      setEmployees(emps);
      setIqamas(iq);
      setContracts(ct);
      onChanged?.();
    } catch {
      toast("err", t("errGeneric"));
      setEmployees([]);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const byOwner = useMemo(() => {
    const m = {};
    for (const d of iqamas) m[d.owner] = { ...(m[d.owner] || {}), iqama: d };
    for (const d of contracts) m[d.owner] = { ...(m[d.owner] || {}), contract: d };
    return m;
  }, [iqamas, contracts]);

  function openFor(empName, category, doc) {
    setCtx({
      category,
      owner: empName,
      title: t(category),
      titleEditable: true,
      titleLabel: t("docTitle"),
      // Lets a paper filed under the wrong person be moved to the right one.
      ownerOptions: (employees || []).map((e) => ({ value: e.name, label: e.name })),
      ownerLabel: t("employee"),
      doc: doc || null,
      heading: `${t(category)} — ${empName}`,
    });
  }

  async function removeDoc() {
    setDeleting(true);
    try {
      await api.deleteDocument(confirm.id);
      toast("ok", t("delOk"));
      setConfirm(null);
      await load();
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeleting(false);
    }
  }

  async function exportExcel() {
    try { await api.exportDocuments({ scope: "employee" }); toast("ok", t("exportOk")); }
    catch { toast("err", t("errGeneric")); }
  }
  function exportPdf() {
    const rows = [...iqamas, ...contracts].map((d) => toPdfRow(t, ar, d));
    if (!exportDocumentsPdf({ rows, t, ar, title: t("edocs") })) toast("err", t("popupBlocked"));
  }

  const loading = employees === null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <Header t={t} title={t("edocs")} sub={t("edocsSub")} />
        <ExportBar t={t} onExcel={exportExcel} onPdf={exportPdf} />
      </div>
      <Legend t={t} />
      <Card flush>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr>{[t("employee"), t("iqama"), t("contract")].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} cols={3} />
              ) : employees.length === 0 ? (
                <tr><td colSpan={3}><Empty text={t("noEmp")} /></td></tr>
              ) : employees.map((e) => {
                const docs = byOwner[e.name] || {};
                return (
                  <tr key={e.name} style={{ borderBottom: `1px solid ${S.g100}` }}>
                    <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>
                      {e.name}
                      {e.department && <small style={{ display: "block", color: S.g400, fontWeight: 400 }}>{e.department}</small>}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <DocLine t={t} ar={ar} doc={docs.iqama} isManager={isManager} busyAttach={busyAttach}
                        onAdd={() => openFor(e.name, "iqama", null)}
                        onEdit={() => openFor(e.name, "iqama", docs.iqama)}
                        onView={() => viewAttachment(docs.iqama.id, t)}
                        onHistory={() => setHistDoc(docs.iqama)}
                        onDelete={() => setConfirm(docs.iqama)} />
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <DocLine t={t} ar={ar} doc={docs.contract} isManager={isManager} busyAttach={busyAttach}
                        onAdd={() => openFor(e.name, "contract", null)}
                        onEdit={() => openFor(e.name, "contract", docs.contract)}
                        onView={() => viewAttachment(docs.contract.id, t)}
                        onHistory={() => setHistDoc(docs.contract)}
                        onDelete={() => setConfirm(docs.contract)} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <DocModal open={ctx !== null} ctx={ctx} isManager={isManager} onClose={() => setCtx(null)} onSaved={() => { toast("ok", t("docSaved")); load(); }} t={t} ar={ar} />
      <ConfirmModal open={confirm !== null} onClose={() => setConfirm(null)} onConfirm={removeDoc} busy={deleting}
        title={t("confirmDel")} body={`${t("del")}: ${confirm?.title || ""} — ${t("irreversible")}`} confirmLabel={t("del")} cancelLabel={t("cancel")} />
      <HistoryModal open={histDoc !== null} doc={histDoc} t={t} ar={ar} onClose={() => setHistDoc(null)} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Company Documents: rents (3 fixed slots) / vehicles / licenses.
// ─────────────────────────────────────────────────────────────────────────────
const RENT_SLOTS = Object.entries(RENT_LABEL_KEY).map(([owner, key]) => ({ owner, key }));

export function CompanyDocs({ lang, user, onChanged }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isManager = user?.role === "hr_manager";
  const { toast, busyAttach, viewAttachment } = useDocs();

  const [tab, setTab] = useState("rent");
  const [docs, setDocs] = useState(null);
  const [ctx, setCtx] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [histDoc, setHistDoc] = useState(null);

  async function load() {
    setDocs(null);
    try {
      setDocs(await api.listDocuments({ category: tab }));
      onChanged?.();
    } catch {
      toast("err", t("errGeneric"));
      setDocs([]);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [tab]);

  async function removeDoc() {
    setDeleting(true);
    try {
      await api.deleteDocument(confirm.id);
      toast("ok", t("delOk"));
      setConfirm(null);
      await load();
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeleting(false);
    }
  }

  const onSaved = () => { toast("ok", t("docSaved")); load(); };
  const tabs = [
    { id: "rent", label: t("tabRents") },
    { id: "vehicle", label: t("tabVehicles") },
    { id: "license", label: t("tabLicenses") },
  ];

  async function exportExcel() {
    try { await api.exportDocuments({ category: tab }); toast("ok", t("exportOk")); }
    catch { toast("err", t("errGeneric")); }
  }
  function exportPdf() {
    const rows = (docs || []).map((d) => toPdfRow(t, ar, d));
    if (!exportDocumentsPdf({ rows, t, ar, title: t("cdocs") })) toast("err", t("popupBlocked"));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <Header t={t} title={t("cdocs")} sub={t("cdocsSub")} />
        <ExportBar t={t} onExcel={exportExcel} onPdf={exportPdf} />
      </div>
      <Legend t={t} />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {tabs.map((tb) => (
          <button key={tb.id} onClick={() => setTab(tb.id)} style={{
            padding: "8px 16px", borderRadius: S.rF, border: `1px solid ${tab === tb.id ? S.pri : S.g200}`,
            background: tab === tb.id ? S.priL : S.w, color: tab === tb.id ? S.priD : S.g500,
            fontWeight: 600, fontSize: 13, cursor: "pointer", fontFamily: "inherit",
          }}>{tb.label}</button>
        ))}
      </div>

      {tab === "rent" ? (
        <RentGrid t={t} ar={ar} docs={docs} isManager={isManager} busyAttach={busyAttach}
          onAdd={(slot) => setCtx({ category: "rent", owner: slot.owner, title: t(slot.key), titleEditable: true, titleLabel: t("docTitle"), doc: null, heading: t(slot.key) })}
          onEdit={(slot, doc) => setCtx({
            category: "rent", owner: slot.owner, title: t(slot.key),
            titleEditable: true, titleLabel: t("docTitle"),
            ownerOptions: RENT_SLOTS.map((s) => ({ value: s.owner, label: t(s.key) })),
            ownerLabel: t("docOwner"),
            doc, heading: t(slot.key),
          })}
          onView={viewAttachment} onDelete={setConfirm} onHistory={setHistDoc} />
      ) : (
        <OpenList t={t} ar={ar} docs={docs} isManager={isManager} busyAttach={busyAttach}
          addLabel={tab === "vehicle" ? t("addVehicle") : t("addLicense")}
          titleLabel={tab === "vehicle" ? t("vehicleName") : t("licenseName")}
          onAdd={() => setCtx({ category: tab, owner: "", title: "", titleEditable: true, titleLabel: tab === "vehicle" ? t("vehicleName") : t("licenseName"), doc: null, heading: tab === "vehicle" ? t("addVehicle") : t("addLicense") })}
          onEdit={(doc) => setCtx({ category: tab, owner: doc.owner, title: doc.title, titleEditable: true, titleLabel: tab === "vehicle" ? t("vehicleName") : t("licenseName"), doc, heading: doc.title || t("editDoc") })}
          onView={viewAttachment} onDelete={setConfirm} onHistory={setHistDoc} />
      )}

      <DocModal open={ctx !== null} ctx={ctx} isManager={isManager} onClose={() => setCtx(null)} onSaved={onSaved} t={t} ar={ar} />
      <ConfirmModal open={confirm !== null} onClose={() => setConfirm(null)} onConfirm={removeDoc} busy={deleting}
        title={t("confirmDel")} body={`${t("del")}: ${confirm?.title || ""} — ${t("irreversible")}`} confirmLabel={t("del")} cancelLabel={t("cancel")} />
      <HistoryModal open={histDoc !== null} doc={histDoc} t={t} ar={ar} onClose={() => setHistDoc(null)} />
    </div>
  );
}

function RentGrid({ t, ar, docs, isManager, busyAttach, onAdd, onEdit, onView, onDelete, onHistory }) {
  const byOwner = useMemo(() => Object.fromEntries((docs || []).map((d) => [d.owner, d])), [docs]);
  const loading = docs === null;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}>
      {RENT_SLOTS.map((slot) => {
        const doc = byOwner[slot.owner];
        return (
          <Card key={slot.owner}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ fontWeight: 700, color: S.g800, fontSize: 15 }}>{t(slot.key)}</div>
              {loading ? (
                <span style={{ color: S.g400, fontSize: 13 }}>…</span>
              ) : (
                <DocLine t={t} ar={ar} doc={doc} isManager={isManager} busyAttach={busyAttach}
                  onAdd={() => onAdd(slot)} onEdit={() => onEdit(slot, doc)}
                  onView={() => onView(doc.id, t)} onDelete={() => onDelete(doc)}
                  onHistory={doc ? () => onHistory(doc) : undefined} />
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function OpenList({ t, ar, docs, isManager, busyAttach, addLabel, onAdd, onEdit, onView, onDelete, onHistory }) {
  const loading = docs === null;
  return (
    <Card flush>
      <div style={{ display: "flex", justifyContent: "flex-end", padding: 14, borderBottom: `1px solid ${S.g100}` }}>
        <BtnPri onClick={onAdd}>{IC.plus} <span>{addLabel}</span></BtnPri>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead><tr>{[t("docTitle"), t("status"), t("act")].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
          <tbody>
            {loading ? (
              <SkeletonRows rows={4} cols={3} />
            ) : docs.length === 0 ? (
              <tr><td colSpan={3}><Empty text={t("noDocs")} /></td></tr>
            ) : docs.map((doc) => (
              <tr key={doc.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>
                  {doc.title}
                  {doc.note && <small style={{ display: "block", color: S.g400, fontWeight: 400 }}>{doc.note}</small>}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <DocLine t={t} ar={ar} doc={doc} isManager={isManager} busyAttach={busyAttach}
                    onEdit={() => onEdit(doc)} onView={() => onView(doc.id, t)} onDelete={() => onDelete(doc)}
                    onHistory={() => onHistory(doc)} />
                </td>
                <td style={{ padding: "12px 16px" }} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Header({ title, sub }) {
  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{title}</h2>
      <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{sub}</p>
    </div>
  );
}

function Legend({ t }) {
  const items = [
    { key: "green", label: t("stGreen") },
    { key: "yellow", label: t("stYellow") },
    { key: "red", label: t("stRed") },
    { key: "expired", label: t("stExpired") },
  ];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", fontSize: 12, color: S.g500 }}>
      {items.map((i) => (
        <span key={i.key} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 9, height: 9, borderRadius: "50%", background: STATUS_STYLE[i.key].dot }} />
          {i.label}
        </span>
      ))}
      <span style={{ color: S.g400 }}>· {t("docLegend")}</span>
    </div>
  );
}
