import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, Pager, BtnPri, BtnSec, Th, FG, inp } from "../components";
import { ConfirmModal } from "../modal";
import { useToast } from "../toast";
import { useDebouncedValue, useFocusSearch, usePagination } from "../hooks";

export default function Employees({ lang, user, onGoPerm }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isHR = user?.role === "hr_manager" || user?.role === "hr_officer";
  const canDelete = user?.role === "hr_manager";
  // Extra columns beyond name/email/dept/manager: the permission indicator (HR
  // staff) and the delete action (HR manager).
  const colCount = 4 + (isHR ? 1 : 0) + (canDelete ? 1 : 0);

  const [list, setList] = useState([]);
  const [perm, setPerm] = useState({ quota: 2, used: {} });
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", department: "", manager_email: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmName, setConfirmName] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const toast = useToast();
  const searchRef = useRef(null);
  useFocusSearch(searchRef);
  const dq = useDebouncedValue(search, 300);

  async function load() {
    try {
      setList(await api.listEmployees());
      if (isHR) {
        // Best-effort: the per-employee permission tally for the current month.
        // A failure here must not blank out the employee list.
        try {
          const month = new Date().toISOString().slice(0, 7);
          const p = await api.listPermissions(month);
          const used = {};
          for (const e of p.employees || []) used[e.employee_name] = e.used;
          setPerm({ quota: p.quota ?? 2, used });
        } catch { /* leave the indicator empty */ }
      }
    } catch (e) {
      setErr(e.message);
    }
    setLoading(false);
  }
  useEffect(() => { load(); }, []);


  async function save() {
    if (!form.name.trim() || !form.email.trim()) return;
    setSaving(true); setErr(null);
    try {
      await api.createEmployee(form);
      setForm({ name: "", email: "", department: "", manager_email: "" });
      setOpen(false);
      toast("ok", t("savedOk"));
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.deleteEmployee(confirmName);
      toast("ok", t("delOk"));
      setConfirmName(null);
      await load();
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeleting(false);
    }
  }

  const filtered = useMemo(() => list.filter((e) =>
    [e.name, e.email, e.department].some((f) => (f || "").toLowerCase().includes(dq.toLowerCase()))
  ), [list, dq]);
  const pg = usePagination(filtered, 10);

  // Used/quota dots for one employee's early-leave permissions this month,
  // matching the Permissions page so the two views read the same.
  const slots = (used) => {
    const q = perm.quota || 2;
    return (
      <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
        {Array.from({ length: q }).map((_, i) => (
          <span key={i} style={{ width: 9, height: 9, borderRadius: "50%", background: i < used ? S.warn : S.g200, display: "inline-block" }} />
        ))}
        <span style={{ fontSize: 12, color: S.g500, marginInlineStart: 4 }}>{used}/{q}</span>
      </span>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("emp")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{ar ? "\u0625\u062F\u0627\u0631\u0629 \u0628\u064A\u0627\u0646\u0627\u062A \u0627\u0644\u0645\u0648\u0638\u0641\u064A\u0646" : "Manage employee records"}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
            <span style={{ position: "absolute", insetInlineStart: 12, pointerEvents: "none", display: "flex" }}>{IC.srch}</span>
            <input ref={searchRef} style={{ ...inp, padding: "10px 14px 10px 14px", paddingInlineStart: 36, width: 210 }} placeholder={t("search")} value={search} onChange={(e) => setSearch(e.target.value)} aria-label={t("search")} />
          </div>
          {isHR && <BtnPri onClick={() => setOpen(!open)}>{IC.plus} <span>{t("addEmp")}</span></BtnPri>}
        </div>
      </div>

      {open && (
        <Card style={{ border: "2px solid rgba(47,184,158,.2)" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("addEmp")}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14, marginBottom: 16 }}>
            <FG label={t("name")}><input style={inp} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></FG>
            <FG label={t("email")}><input style={inp} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></FG>
            <FG label={t("dept")}><input style={inp} value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></FG>
            <FG label={t("mgrEmail")}><input style={inp} type="email" value={form.manager_email} onChange={(e) => setForm({ ...form, manager_email: e.target.value })} /></FG>
          </div>
          {err && <div style={{ color: S.err, fontSize: 13, marginBottom: 12 }}>{err}</div>}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{t("save")}</span></BtnPri>
            <BtnSec onClick={() => setOpen(false)}><span>{t("cancel")}</span></BtnSec>
          </div>
        </Card>
      )}

      <Card flush>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr>{[t("name"), t("email"), t("dept"), t("mgrEmail"), ...(isHR ? [t("slotsLabel")] : []), ...(canDelete ? [t("act")] : [])].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} cols={colCount} />
              ) : filtered.length === 0 ? (
                <tr><td colSpan={colCount}><Empty text={t("noEmp")} sub={isHR ? t("addEmpHint") : undefined} /></td></tr>
              ) : pg.slice.map((e) => (
                <tr key={e.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>{e.name}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{e.email}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{e.department}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{e.manager_email}</td>
                  {isHR && (
                    <td style={{ padding: "12px 16px" }}>
                      <button
                        onClick={() => onGoPerm && onGoPerm()}
                        title={t("scPerm")}
                        style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 8px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, cursor: onGoPerm ? "pointer" : "default", fontFamily: "inherit" }}
                      >
                        {slots(perm.used[e.name] || 0)}
                      </button>
                    </td>
                  )}
                  {canDelete && (
                    <td style={{ padding: "12px 16px" }}>
                      <button onClick={() => setConfirmName(e.name)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && <Pager {...pg} ar={ar} label={t("emp")} />}
      </Card>

      <ConfirmModal
        open={confirmName !== null}
        onClose={() => setConfirmName(null)}
        onConfirm={remove}
        busy={deleting}
        title={t("confirmDel")}
        body={`${t("del")}: ${confirmName} — ${t("irreversible")}`}
        confirmLabel={t("del")}
        cancelLabel={t("cancel")}
      />
    </div>
  );
}
