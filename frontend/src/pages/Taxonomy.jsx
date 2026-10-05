import { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { BtnPri, BtnSec, FG, inp, chipBtn } from "../components";
import { Modal } from "../modal";
import { useToast } from "../toast";

// Full-width fields must include their padding, or they overflow grid cells.
const fld = { ...inp, boxSizing: "border-box" };

const EMPTY = { id: "", canonical: "", category: "", aliases: "", is_active: true };
const CV_MIME = { pdf: "application/pdf", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", txt: "text/plain" };

/** Skills taxonomy editor + "test on a CV" (HR Manager, inside Settings). */
export default function TaxonomyEditor({ lang }) {
  const t = (k) => L[lang][k] || k;
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState(null); // null | "new" | id
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);

  const load = () => api.listTaxonomy().then(setItems).catch(() => toast("err", t("errGeneric")));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n) return items;
    return items.filter((s) => [s.id, s.canonical, s.category, ...s.aliases].some((v) => String(v).toLowerCase().includes(n)));
  }, [items, q]);

  function open(skill) {
    setErr(null);
    setForm(skill ? { ...skill, aliases: skill.aliases.join(", ") } : EMPTY);
    setEdit(skill ? skill.id : "new");
  }

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await api.saveTaxonomy({
        id: form.id.trim().toLowerCase(), canonical: form.canonical.trim(), category: form.category.trim(),
        aliases: form.aliases.split(/[,،]/).map((x) => x.trim()).filter(Boolean), is_active: form.is_active,
      });
      toast("ok", t("taxSaved"));
      setEdit(null);
      await load();
    } catch (e) {
      setErr(e?.message || t("errGeneric"));
    } finally {
      setSaving(false);
    }
  }

  async function onTestFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const mime = CV_MIME[(file.name.split(".").pop() || "").toLowerCase()];
    if (!mime) { toast("err", t("errCvType")); return; }
    setPreviewing(true);
    try {
      const b64 = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result).split(",")[1] || "");
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      setPreview({ name: file.name, ...(await api.parsePreview({ cv_attachment: b64, cv_name: file.name, cv_mime: mime })) });
    } catch (err2) {
      toast("err", err2?.message || t("errGeneric"));
    } finally {
      setPreviewing(false);
    }
  }

  const p = preview?.parsed;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ fontSize: 12, color: S.g400, margin: 0 }}>{t("taxHint")}</p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <input style={{ ...fld, flex: 1, minWidth: 180 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} />
        <BtnPri onClick={() => open(null)}>{IC.plus} <span>{t("newSkill")}</span></BtnPri>
      </div>
      <div style={{ maxHeight: 340, overflowY: "auto", border: `1px solid ${S.g100}`, borderRadius: S.r2 }}>
        {shown.map((s) => (
          <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderBottom: `1px solid ${S.g100}`, opacity: s.is_active ? 1 : 0.5 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: S.g700 }}>{s.canonical} <small style={{ color: S.g400, fontWeight: 400 }}>· {s.category.replace(/_/g, " ")}</small></div>
              <div style={{ fontSize: 12, color: S.g400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.aliases.join(", ")}</div>
            </div>
            <button onClick={() => open(s)} style={chipBtn(S.info)}>{t("editDoc")}</button>
          </div>
        ))}
      </div>

      <div style={{ borderTop: `1px solid ${S.g100}`, paddingTop: 14 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: S.g700 }}>{t("testCv")}</div>
        <div style={{ fontSize: 12, color: S.g400, margin: "2px 0 10px" }}>{t("testCvSub")}</div>
        <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: S.r2, border: `1.5px dashed ${S.g300}`, cursor: "pointer", background: S.g50, fontSize: 13, color: S.g500 }}>
          {IC.upload}
          <span style={{ flex: 1 }}>{previewing ? "…" : preview?.name || t("chooseCv")}</span>
          <input type="file" accept=".pdf,.docx,.txt" onChange={onTestFile} style={{ display: "none" }} />
        </label>
        {p && (
          <div style={{ marginTop: 12, fontSize: 13, color: S.g600, display: "flex", flexDirection: "column", gap: 6 }}>
            <div>{t("pagesLbl")}: {preview.extraction.pages} · {t("yearsExp")}: {p.years_experience ?? "—"} · {t("education")}: {p.education || "—"} · {t("wLanguages")}: {(p.languages || []).join(", ") || "—"}</div>
            {preview.extraction.needs_manual_review && <div style={{ color: S.warn, fontWeight: 600 }}>{t("needsReview")}</div>}
            {(preview.extraction.warnings || []).map((w) => <div key={w} style={{ fontSize: 12, color: S.g400 }}>{w}</div>)}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {(p.skills || []).map((s) => <span key={s.id} title={s.evidence?.[0]?.line} style={{ fontSize: 11.5, padding: "2px 8px", borderRadius: 999, background: S.priL, color: S.priD }}>{s.canonical}</span>)}
            </div>
          </div>
        )}
      </div>

      <Modal open={edit !== null} onClose={() => setEdit(null)} title={edit === "new" ? t("newSkill") : form.canonical} width={520}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
          <FG label={t("skillId")}>
            <input style={fld} value={form.id} disabled={edit !== "new"} maxLength={100} placeholder="e.g. hotel_booking" onChange={(e) => setForm({ ...form, id: e.target.value })} />
          </FG>
          <FG label={t("canonical")}><input style={fld} value={form.canonical} maxLength={200} onChange={(e) => setForm({ ...form, canonical: e.target.value })} /></FG>
          <FG label={t("category")}><input style={fld} value={form.category} maxLength={100} onChange={(e) => setForm({ ...form, category: e.target.value })} /></FG>
          <FG label={t("aliases")}>
            <textarea style={{ ...fld, resize: "vertical", minHeight: 70 }} value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} />
          </FG>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, color: S.g600, cursor: "pointer" }}>
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            {t("activeLbl")}
          </label>
        </div>
        {err && <div role="alert" style={{ color: S.err, fontSize: 13, marginBottom: 12 }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <BtnSec onClick={() => setEdit(null)}><span>{t("cancel")}</span></BtnSec>
          <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{saving ? "…" : t("save")}</span></BtnPri>
        </div>
      </Modal>
    </div>
  );
}

TaxonomyEditor.propTypes = { lang: PropTypes.string.isRequired };
