import { useEffect, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, BtnPri, BtnSec, Th, FG, inp, chipBtn } from "../components";
import { Modal, ConfirmModal } from "../modal";
import { useToast } from "../toast";

const ALLOWED = ["image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"];
const ERR = { quota_exceeded: "errQuota", unknown_employee: "errUnknownEmp" };
const thisMonth = () => new Date().toISOString().slice(0, 10).slice(0, 7);
const today = () => new Date().toISOString().slice(0, 10);
const EMPTY_FILE = { name: "", b64: "", mime: "" };

export default function Permissions({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isManager = user?.role === "hr_manager";
  const toast = useToast();

  const [month, setMonth] = useState(thisMonth);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modalEmp, setModalEmp] = useState(null);
  const [form, setForm] = useState({ date: today(), note: "", file: EMPTY_FILE });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const [confirmPerm, setConfirmPerm] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [busyAttach, setBusyAttach] = useState(null);

  const em = (e) => (ERR[e?.message] ? t(ERR[e.message]) : e?.message || t("errGeneric"));

  async function load() {
    setLoading(true);
    try {
      setData(await api.listPermissions(month));
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  function openAdd(empName) {
    setErr(null);
    setForm({ date: month === thisMonth() ? today() : `${month}-01`, note: "", file: EMPTY_FILE });
    setModalEmp(empName);
  }

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
    setSaving(true);
    setErr(null);
    try {
      await api.createPermission({
        employee_name: modalEmp,
        permission_date: form.date,
        note: form.note,
        attachment: form.file.b64,
        attachment_name: form.file.name,
        attachment_mime: form.file.mime,
      });
      toast("ok", t("permSaved"));
      setModalEmp(null);
      await load();
    } catch (e) {
      setErr(em(e));
    } finally {
      setSaving(false);
    }
  }

  async function removePerm() {
    setDeleting(true);
    try {
      await api.deletePermission(confirmPerm.id);
      toast("ok", t("delOk"));
      setConfirmPerm(null);
      await load();
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeleting(false);
    }
  }

  async function viewAttachment(pid) {
    setBusyAttach(pid);
    try {
      const a = await api.permissionAttachment(pid);
      const bytes = Uint8Array.from(atob(a.attachment), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: a.attachment_mime }));
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      toast("err", em(e));
    } finally {
      setBusyAttach(null);
    }
  }

  const quota = data?.quota ?? 2;
  const employees = data?.employees ?? [];

  const slots = (used) => (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      {Array.from({ length: quota }).map((_, i) => (
        <span key={i} style={{ width: 9, height: 9, borderRadius: "50%", background: i < used ? S.warn : S.g200, display: "inline-block" }} />
      ))}
      <span style={{ fontSize: 12, color: S.g500, marginInlineStart: 4 }}>{used}/{quota}</span>
    </span>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("perm")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{t("permSub")}</p>
        </div>
        <FG label={t("month")}>
          <input style={{ ...inp, width: 170 }} type="month" value={month} onChange={(e) => setMonth(e.target.value || thisMonth())} />
        </FG>
      </div>

      <Card flush>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>{[t("employee"), t("slotsLabel"), t("details"), t("act")].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} cols={4} />
              ) : employees.length === 0 ? (
                <tr><td colSpan={4}><Empty text={t("noEmp")} /></td></tr>
              ) : employees.map((e) => (
                <tr key={e.employee_name} style={{ borderBottom: `1px solid ${S.g100}` }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>
                    {e.employee_name}
                    {e.department && <small style={{ display: "block", color: S.g400, fontWeight: 400 }}>{e.department}</small>}
                  </td>
                  <td style={{ padding: "12px 16px" }}>{slots(e.used)}</td>
                  <td style={{ padding: "12px 16px" }}>
                    {e.permissions.length === 0 ? (
                      <span style={{ color: S.g400 }}>{t("noPermMonth")}</span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {e.permissions.map((p) => (
                          <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontWeight: 600, color: S.g700, direction: "ltr" }}>{p.permission_date}</span>
                            {p.note && <span style={{ color: S.g500 }}>— {p.note}</span>}
                            {p.has_attachment && isManager && (
                              <button onClick={() => viewAttachment(p.id)} disabled={busyAttach === p.id} title={t("viewAttach")} style={chipBtn(S.info)}>
                                {IC.clip} <span>{t("attach")}</span>
                              </button>
                            )}
                            {p.has_attachment && !isManager && (
                              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: S.g400, fontSize: 12 }}>{IC.clip}</span>
                            )}
                            {isManager && (
                              <button onClick={() => setConfirmPerm(p)} title={t("del")} style={chipBtn(S.err)}>{t("del")}</button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <button
                      onClick={() => openAdd(e.employee_name)}
                      disabled={e.remaining <= 0}
                      title={e.remaining <= 0 ? t("permQuotaFull") : t("addPerm")}
                      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: S.r2, border: "none", cursor: e.remaining <= 0 ? "not-allowed" : "pointer", opacity: e.remaining <= 0 ? 0.5 : 1, background: S.pri, color: "#fff", fontFamily: "inherit", whiteSpace: "nowrap" }}
                    >
                      {IC.plus} <span>{t("addPerm")}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={modalEmp !== null} onClose={() => setModalEmp(null)} title={`${t("newPerm")} — ${modalEmp || ""}`}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
          <FG label={t("permDate")}>
            <input style={inp} type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </FG>
          <FG label={t("permNote")}>
            <textarea style={{ ...inp, resize: "vertical", minHeight: 60 }} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
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
          <BtnSec onClick={() => setModalEmp(null)}><span>{t("cancel")}</span></BtnSec>
          <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{saving ? "…" : t("save")}</span></BtnPri>
        </div>
      </Modal>

      <ConfirmModal
        open={confirmPerm !== null}
        onClose={() => setConfirmPerm(null)}
        onConfirm={removePerm}
        busy={deleting}
        title={t("confirmDel")}
        body={`${t("del")}: ${confirmPerm?.permission_date || ""} — ${t("irreversible")}`}
        confirmLabel={t("del")}
        cancelLabel={t("cancel")}
      />
    </div>
  );
}

