import { useEffect, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, BtnPri, BtnSec, Th, FG, inp } from "../components";

export default function Employees({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isHR = user?.role === "hr_manager" || user?.role === "hr_officer";
  const canDelete = user?.role === "hr_manager";

  const [list, setList] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", department: "", manager_email: "" });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  async function load() {
    try { setList(await api.listEmployees()); } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    if (!form.name.trim() || !form.email.trim()) return;
    setSaving(true); setErr(null);
    try {
      await api.createEmployee(form);
      setForm({ name: "", email: "", department: "", manager_email: "" });
      setOpen(false);
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(name) {
    if (!confirm(`${t("del")}: ${name}?`)) return;
    await api.deleteEmployee(name);
    await load();
  }

  const filtered = list.filter((e) =>
    [e.name, e.email, e.department].some((f) => (f || "").toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("emp")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{ar ? "\u0625\u062F\u0627\u0631\u0629 \u0628\u064A\u0627\u0646\u0627\u062A \u0627\u0644\u0645\u0648\u0638\u0641\u064A\u0646" : "Manage employee records"}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
            <span style={{ position: "absolute", [ar ? "right" : "left"]: 12, pointerEvents: "none", display: "flex" }}>{IC.srch}</span>
            <input style={{ ...inp, [ar ? "paddingRight" : "paddingLeft"]: 36, width: 210 }} placeholder={t("search")} value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {isHR && <BtnPri onClick={() => setOpen(!open)}>{IC.plus} <span>{t("addEmp")}</span></BtnPri>}
        </div>
      </div>

      {open && (
        <Card style={{ border: "2px solid rgba(47,184,158,.2)" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("addEmp")}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 16 }}>
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
            <thead><tr>{[t("name"), t("email"), t("dept"), t("mgrEmail"), ...(canDelete ? [t("act")] : [])].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={canDelete ? 5 : 4}><Empty text={t("noEmp")} sub={ar ? "\u0627\u0633\u062A\u062E\u062F\u0645 \u0632\u0631 \u0627\u0644\u0625\u0636\u0627\u0641\u0629 \u0623\u0639\u0644\u0627\u0647" : "Use the Add Employee button above"} /></td></tr>
              ) : filtered.map((e) => (
                <tr key={e.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>{e.name}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{e.email}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{e.department}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{e.manager_email}</td>
                  {canDelete && (
                    <td style={{ padding: "12px 16px" }}>
                      <button onClick={() => remove(e.name)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
