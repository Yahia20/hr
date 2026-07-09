import { useEffect, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, BtnPri, BtnSec, Th, FG, inp } from "../components";
import { ConfirmModal } from "../modal";
import { useToast } from "../toast";

const EMPTY_FORM = { name: "", email: "", role: "hr_officer", department: "", password: "" };

export default function Users({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const roleLabel = { hr_manager: t("roleManager"), hr_officer: t("roleOfficer"), dept_head: t("roleDeptHead"), employee: t("roleEmployee") };

  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmUser, setConfirmUser] = useState(null);
  const [deactivating, setDeactivating] = useState(false);
  const [savingRole, setSavingRole] = useState(null);
  const toast = useToast();

  async function load() {
    try { setList(await api.listUsers()); } catch (e) { setErr(e.message); }
    setLoading(false);
  }
  useEffect(() => { load(); }, []);

  async function save() {
    setErr(null);
    if (!form.name.trim() || !form.email.trim()) return;
    if (form.password.length < 8) { setErr(t("pwdTooShort")); return; }
    setSaving(true);
    try {
      await api.createUser(form);
      setForm(EMPTY_FORM);
      setOpen(false);
      toast("ok", t("savedOk"));
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function deactivate() {
    setDeactivating(true);
    try {
      await api.deactivateUser(confirmUser.id);
      toast("ok", t("deactOk"));
      setConfirmUser(null);
      await load();
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeactivating(false);
    }
  }

  async function changeRole(u, role) {
    if (role === u.role) return;
    setSavingRole(u.id);
    try {
      await api.updateUser(u.id, { role });
      toast("ok", t("roleUpdated"));
      await load();
    } catch (e) {
      toast("err", e?.status === 409 ? t("errLastManager") : (e?.message || t("errGeneric")));
    } finally {
      setSavingRole(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("users")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{ar ? "حسابات الدخول والأدوار" : "Login accounts and roles"}</p>
        </div>
        <BtnPri onClick={() => setOpen(!open)}>{IC.plus} <span>{t("addUser")}</span></BtnPri>
      </div>

      {open && (
        <Card style={{ border: "2px solid rgba(47,184,158,.2)" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("addUser")}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 14, marginBottom: 16 }}>
            <FG label={t("name")}><input style={inp} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></FG>
            <FG label={t("email")}><input style={inp} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></FG>
            <FG label={t("role")}>
              <select style={{ ...inp, cursor: "pointer" }} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {Object.entries(roleLabel).map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
              </select>
            </FG>
            <FG label={t("dept")}><input style={inp} value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></FG>
            <FG label={t("password")}><input style={inp} type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></FG>
          </div>
          {err && <div style={{ color: S.err, fontSize: 13, marginBottom: 12 }}>{err}</div>}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{t("save")}</span></BtnPri>
            <BtnSec onClick={() => setOpen(false)}><span>{t("cancel")}</span></BtnSec>
          </div>
        </Card>
      )}

      {!open && err && <div style={{ color: S.err, fontSize: 13 }}>{err}</div>}

      <Card flush>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr>{[t("name"), t("email"), t("role"), t("dept"), t("status"), t("act")].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={4} cols={6} />
              ) : list.length === 0 ? (
                <tr><td colSpan={6}><Empty text={t("noUsers")} /></td></tr>
              ) : list.map((u) => (
                <tr key={u.id} style={{ borderBottom: `1px solid ${S.g100}`, opacity: u.is_active ? 1 : 0.5 }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>{u.name}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{u.email}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>
                    {u.is_active && u.id !== user.id ? (
                      <select
                        value={u.role}
                        disabled={savingRole === u.id}
                        onChange={(e) => changeRole(u, e.target.value)}
                        aria-label={t("role")}
                        style={{ ...inp, padding: "6px 10px", cursor: savingRole === u.id ? "wait" : "pointer", minWidth: 130 }}
                      >
                        {Object.entries(roleLabel).map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
                      </select>
                    ) : (
                      roleLabel[u.role] || u.role
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{u.department}</td>
                  <td style={{ padding: "12px 16px", color: u.is_active ? S.ok : S.g400, fontWeight: 600 }}>{u.is_active ? t("active") : t("inactive")}</td>
                  <td style={{ padding: "12px 16px" }}>
                    {u.is_active && u.id !== user.id ? (
                      <button onClick={() => setConfirmUser(u)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("deactivate")}</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <ConfirmModal
        open={confirmUser !== null}
        onClose={() => setConfirmUser(null)}
        onConfirm={deactivate}
        busy={deactivating}
        title={t("confirmDeact")}
        body={`${t("deactivate")}: ${confirmUser?.name} (${confirmUser?.email})`}
        confirmLabel={t("deactivate")}
        cancelLabel={t("cancel")}
      />
    </div>
  );
}
