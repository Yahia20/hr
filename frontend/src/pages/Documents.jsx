import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, BtnPri, BtnSec, Th, FG, inp } from "../components";
import { Modal, ConfirmModal } from "../modal";
import { useToast } from "../toast";

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

function daysText(t, doc) {
  const n = doc.days_left;
  if (n === null || n === undefined) return "";
  if (doc.status === "expired") return t("expiredAgoN").replace("{n}", Math.abs(n));
  if (n === 0) return t("expiresTodayL");
  return t("expiresInN").replace("{n}", n);
}

function ExpiryBadge({ t, doc }) {
  const st = STATUS_STYLE[doc.status] || STATUS_STYLE.unknown;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: S.rF, background: st.bg, color: st.fg, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: st.dot }} />
      {t(STATUS_KEY[doc.status] || "stUnknown")}
    </span>
  );
}

// The shared add/renew form. `ctx` describes the target slot/list item.
function DocModal({ open, ctx, onClose, onSaved, t, ar }) {
  const [form, setForm] = useState({ title: "", start: today(), end: plusYear(), note: "", file: EMPTY_FILE });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!ctx) return;
    const d = ctx.doc;
    setErr(null);
    setForm({
      title: d?.title ?? ctx.title ?? "",
      start: d?.start_date ?? today(),
      end: d?.end_date ?? plusYear(),
      note: d?.note ?? "",
      file: EMPTY_FILE,
    });
  }, [ctx]);

  if (!ctx) return null;

  function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) { setForm((f) => ({ ...f, file: EMPTY_FILE })); return; }
    if (!ALLOWED.includes(file.type)) { setErr(t("errFileType")); return; }
    if (file.size > 5 * 1024 * 1024) { setErr(ar ? "الحجم أكبر من 5MB" : "File exceeds 5MB"); return; }
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, file: { name: file.name, b64: String(reader.result).split(",")[1] || "", mime: file.type } }));
    reader.readAsDataURL(file);
    setErr(null);
  }

  async function save() {
    if (form.end < form.start) { setErr(ar ? "تاريخ النهاية قبل البداية" : "End date is before start date"); return; }
    if (ctx.titleEditable && !form.title.trim()) { setErr(ar ? "الاسم مطلوب" : "Name is required"); return; }
    setSaving(true);
    setErr(null);
    try {
      const attach = form.file.b64
        ? { attachment: form.file.b64, attachment_name: form.file.name, attachment_mime: form.file.mime }
        : {};
      if (ctx.doc) {
        await api.updateDocument(ctx.doc.id, { title: form.title, start_date: form.start, end_date: form.end, note: form.note, ...attach });
      } else {
        await api.createDocument({ category: ctx.category, owner: ctx.owner || "", title: form.title, start_date: form.start, end_date: form.end, note: form.note, ...attach });
      }
      onSaved();
      onClose();
    } catch (e) {
      setErr(e?.message === "slot_exists" ? t("errSlotExists") : e?.message || t("errGeneric"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={ctx.heading}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
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
          <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: S.r2, border: `1.5px dashed ${S.g300}`, cursor: "pointer", background: S.g50, fontSize: 13, color: S.g500 }}>
            {IC.upload}
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{form.file.name || t("chooseFile")}</span>
            <input type="file" accept="image/*,application/pdf" onChange={onFile} style={{ display: "none" }} />
          </label>
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
function DocLine({ t, doc, isManager, onAdd, onEdit, onView, onDelete, busyAttach }) {
  if (!doc) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ color: S.g400, fontSize: 13 }}>{t("notSet")}</span>
        <button onClick={onAdd} style={chipBtn(S.pri)}>{IC.plus} <span>{t("addDoc")}</span></button>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <ExpiryBadge t={t} doc={doc} />
      <span style={{ direction: "ltr", fontWeight: 600, color: S.g700, fontSize: 12.5 }}>{doc.end_date}</span>
      <span style={{ color: S.g400, fontSize: 12 }}>{daysText(t, doc)}</span>
      <button onClick={onEdit} style={chipBtn(S.info)}>{t("renew")}</button>
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
export function EmployeeDocs({ lang, user }) {
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
      titleEditable: false,
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

  const loading = employees === null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Header t={t} title={t("edocs")} sub={t("edocsSub")} />
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
                      <DocLine t={t} doc={docs.iqama} isManager={isManager} busyAttach={busyAttach}
                        onAdd={() => openFor(e.name, "iqama", null)}
                        onEdit={() => openFor(e.name, "iqama", docs.iqama)}
                        onView={() => viewAttachment(docs.iqama.id, t)}
                        onDelete={() => setConfirm(docs.iqama)} />
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <DocLine t={t} doc={docs.contract} isManager={isManager} busyAttach={busyAttach}
                        onAdd={() => openFor(e.name, "contract", null)}
                        onEdit={() => openFor(e.name, "contract", docs.contract)}
                        onView={() => viewAttachment(docs.contract.id, t)}
                        onDelete={() => setConfirm(docs.contract)} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <DocModal open={ctx !== null} ctx={ctx} onClose={() => setCtx(null)} onSaved={() => { toast("ok", t("docSaved")); load(); }} t={t} ar={ar} />
      <ConfirmModal open={confirm !== null} onClose={() => setConfirm(null)} onConfirm={removeDoc} busy={deleting}
        title={t("confirmDel")} body={`${t("del")}: ${confirm?.title || ""} — ${t("irreversible")}`} confirmLabel={t("del")} cancelLabel={t("cancel")} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Company Documents: rents (3 fixed slots) / vehicles / licenses.
// ─────────────────────────────────────────────────────────────────────────────
const RENT_SLOTS = [
  { owner: "rawda", key: "rentRawda" },
  { owner: "hamra", key: "rentHamra" },
  { owner: "housing", key: "rentHousing" },
];

export function CompanyDocs({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isManager = user?.role === "hr_manager";
  const { toast, busyAttach, viewAttachment } = useDocs();

  const [tab, setTab] = useState("rent");
  const [docs, setDocs] = useState(null);
  const [ctx, setCtx] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setDocs(null);
    try {
      setDocs(await api.listDocuments({ category: tab }));
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Header t={t} title={t("cdocs")} sub={t("cdocsSub")} />
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
          onAdd={(slot) => setCtx({ category: "rent", owner: slot.owner, title: t(slot.key), titleEditable: false, doc: null, heading: t(slot.key) })}
          onEdit={(slot, doc) => setCtx({ category: "rent", owner: slot.owner, title: t(slot.key), titleEditable: false, doc, heading: t(slot.key) })}
          onView={viewAttachment} onDelete={setConfirm} />
      ) : (
        <OpenList t={t} ar={ar} docs={docs} isManager={isManager} busyAttach={busyAttach}
          addLabel={tab === "vehicle" ? t("addVehicle") : t("addLicense")}
          titleLabel={tab === "vehicle" ? t("vehicleName") : t("licenseName")}
          onAdd={() => setCtx({ category: tab, owner: "", title: "", titleEditable: true, titleLabel: tab === "vehicle" ? t("vehicleName") : t("licenseName"), doc: null, heading: tab === "vehicle" ? t("addVehicle") : t("addLicense") })}
          onEdit={(doc) => setCtx({ category: tab, owner: doc.owner, title: doc.title, titleEditable: true, titleLabel: tab === "vehicle" ? t("vehicleName") : t("licenseName"), doc, heading: doc.title || t("editDoc") })}
          onView={viewAttachment} onDelete={setConfirm} />
      )}

      <DocModal open={ctx !== null} ctx={ctx} onClose={() => setCtx(null)} onSaved={onSaved} t={t} ar={ar} />
      <ConfirmModal open={confirm !== null} onClose={() => setConfirm(null)} onConfirm={removeDoc} busy={deleting}
        title={t("confirmDel")} body={`${t("del")}: ${confirm?.title || ""} — ${t("irreversible")}`} confirmLabel={t("del")} cancelLabel={t("cancel")} />
    </div>
  );
}

function RentGrid({ t, docs, isManager, busyAttach, onAdd, onEdit, onView, onDelete }) {
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
                <DocLine t={t} doc={doc} isManager={isManager} busyAttach={busyAttach}
                  onAdd={() => onAdd(slot)} onEdit={() => onEdit(slot, doc)}
                  onView={() => onView(doc.id, t)} onDelete={() => onDelete(doc)} />
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function OpenList({ t, ar, docs, isManager, busyAttach, addLabel, onAdd, onEdit, onView, onDelete }) {
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
                  <DocLine t={t} doc={doc} isManager={isManager} busyAttach={busyAttach}
                    onEdit={() => onEdit(doc)} onView={() => onView(doc.id, t)} onDelete={() => onDelete(doc)} />
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
