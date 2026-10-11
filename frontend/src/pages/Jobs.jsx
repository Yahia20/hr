import { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, BtnPri, BtnSec, Th, FG, inp, chipBtn } from "../components";
import { Modal, ConfirmModal } from "../modal";
import { useToast } from "../toast";

// Full-width fields must include their padding, or they overflow grid cells.
const fld = { ...inp, boxSizing: "border-box" };

export const EDU_LEVELS = [["", "eduAny"], ["high_school", "eduHigh"], ["diploma", "eduDiploma"], ["bachelor", "eduBachelor"], ["master", "eduMaster"], ["phd", "eduPhd"]];
export const WEIGHT_KEYS = [["required_skills", "wRequired"], ["experience", "wExperience"], ["preferred_skills", "wPreferred"], ["education", "wEducation"], ["languages", "wLanguages"]];
const DEFAULT_WEIGHTS = { required_skills: 40, experience: 20, preferred_skills: 10, education: 10, languages: 10 };
const LIST_GATES = [["nationality_in", "gNationality"], ["city_in", "gCity"], ["language_required", "gLanguage"]];
const FLAG_GATES = [["min_years", "gMinYears"], ["min_education", "gMinEdu"], ["licence_required", "gLicence"], ["transferable_iqama_required", "gIqama"]];

const splitList = (s) => s.split(/[,،]/).map((x) => x.trim()).filter(Boolean);
const skillIds = (list) => (list || []).map((x) => (typeof x === "string" ? x : x.skill_id || x.id)).filter(Boolean);

const EMPTY_FORM = {
  title: "", department: "", location: "", employment_type: "", description: "", status: "open",
  min_years: 0, min_education: "", languages: "Arabic, English",
  required_skills: [], preferred_skills: [], gateLists: {}, gateFlags: {}, weights: { ...DEFAULT_WEIGHTS },
};

/** Job row/template → editable form state (list gates as comma text). */
function toForm(job) {
  const gates = job.gates || {};
  const gateLists = {}, gateFlags = {};
  for (const [k] of LIST_GATES) if (gates[k]) gateLists[k] = (Array.isArray(gates[k]) ? gates[k] : [gates[k]]).join(", ");
  for (const [k] of FLAG_GATES) if (gates[k]) gateFlags[k] = true;
  return {
    ...EMPTY_FORM,
    title: job.title || "", department: job.department || "", location: job.location || "",
    employment_type: job.employment_type || "", description: job.description || "", status: job.status || "open",
    min_years: job.min_years ?? 0, min_education: job.min_education || "",
    languages: (job.languages || []).join(", "),
    required_skills: skillIds(job.required_skills), preferred_skills: skillIds(job.preferred_skills),
    gateLists, gateFlags, weights: { ...DEFAULT_WEIGHTS, ...(job.weights || {}) },
  };
}

function toPayload(f) {
  const gates = {};
  for (const [k] of LIST_GATES) { const v = splitList(f.gateLists[k] || ""); if (v.length) gates[k] = v; }
  for (const [k] of FLAG_GATES) if (f.gateFlags[k]) gates[k] = true;
  return {
    title: f.title.trim(), department: f.department.trim(), location: f.location.trim(),
    employment_type: f.employment_type.trim(), description: f.description, status: f.status,
    min_years: Number(f.min_years) || 0, min_education: f.min_education,
    languages: splitList(f.languages), required_skills: f.required_skills, preferred_skills: f.preferred_skills,
    gates, weights: Object.fromEntries(WEIGHT_KEYS.map(([k]) => [k, Number(f.weights[k]) || 0])), semantic_criteria: [],
  };
}

/** Selected skills as removable chips + a grouped dropdown to add more. */
export function SkillPicker({ value, onChange, taxonomy, nameOf, placeholder }) {
  const groups = useMemo(() => {
    const g = {};
    for (const s of taxonomy) if (s.is_active !== false && !value.includes(s.id)) (g[s.category] ||= []).push(s);
    return Object.entries(g).sort(([a], [b]) => a.localeCompare(b));
  }, [taxonomy, value]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {value.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {value.map((id) => (
            <span key={id} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, padding: "4px 6px 4px 10px", borderRadius: 999, background: S.priL, color: S.priD }}>
              {nameOf(id)}
              <button type="button" aria-label={`× ${nameOf(id)}`} onClick={() => onChange(value.filter((x) => x !== id))} style={{ border: "none", background: "transparent", color: S.priD, cursor: "pointer", fontSize: 14, lineHeight: 1, padding: "0 4px", fontFamily: "inherit" }}>×</button>
            </span>
          ))}
        </div>
      )}
      <select style={fld} value="" onChange={(e) => e.target.value && onChange([...value, e.target.value])}>
        <option value="">{placeholder}</option>
        {groups.map(([cat, items]) => (
          <optgroup key={cat} label={cat.replace(/_/g, " ")}>
            {items.map((s) => <option key={s.id} value={s.id}>{s.canonical}</option>)}
          </optgroup>
        ))}
      </select>
    </div>
  );
}
SkillPicker.propTypes = {
  value: PropTypes.arrayOf(PropTypes.string).isRequired, onChange: PropTypes.func.isRequired,
  taxonomy: PropTypes.array.isRequired, nameOf: PropTypes.func.isRequired, placeholder: PropTypes.string,
};

const subHead = { fontSize: 12.5, fontWeight: 700, color: S.g700, margin: "6px 0 0" };

export default function Jobs({ lang, user, onOpenApplicants }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const toast = useToast();
  const isHr = user?.role === "hr_manager" || user?.role === "hr_officer";

  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [taxonomy, setTaxonomy] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | "new" | job id
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [deleting, setDeleting] = useState(null); // job pending delete confirmation

  const nameOf = useMemo(() => {
    const m = Object.fromEntries(taxonomy.map((s) => [s.id, s.canonical]));
    return (id) => m[id] || id.replace(/_/g, " ");
  }, [taxonomy]);
  const perJob = useMemo(() => Object.fromEntries((stats?.jobs || []).map((j) => [j.job_id, j])), [stats]);

  async function load() {
    setLoading(true);
    try {
      setJobs(await api.listJobs());
      if (isHr) setStats(await api.recruitmentStats());
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    if (isHr) {
      api.listTaxonomy().then(setTaxonomy).catch(() => {});
      api.jobTemplates().then(setTemplates).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openNew() {
    setErr(null);
    setForm(EMPTY_FORM);
    setEditing("new");
  }

  async function openEdit(id) {
    setErr(null);
    try {
      setForm(toForm(await api.getJob(id)));
      setEditing(id);
    } catch {
      toast("err", t("errGeneric"));
    }
  }

  function applyTemplate(id) {
    const tpl = templates.find((x) => x.id === id);
    setForm(tpl ? { ...toForm(tpl), department: form.department, location: form.location, employment_type: form.employment_type } : EMPTY_FORM);
  }

  const weightSum = WEIGHT_KEYS.reduce((n, [k]) => n + (Number(form.weights[k]) || 0), 0);

  async function save() {
    if (!form.title.trim()) { setErr(t("jobTitle")); return; }
    if (weightSum <= 0) { setErr(t("errWeights")); return; }
    setSaving(true);
    setErr(null);
    try {
      const payload = toPayload(form);
      const res = editing === "new" ? await api.createJob(payload) : await api.updateJob(editing, payload);
      toast("ok", res.rescored_applicants ? t("rescoredN").replace("{n}", res.rescored_applicants) : t("jobSaved"));
      setEditing(null);
      await load();
    } catch (e) {
      setErr(e?.message || t("errGeneric"));
    } finally {
      setSaving(false);
    }
  }

  async function removeJob() {
    const job = deleting;
    setBusyId(job.id);
    try {
      await api.deleteJob(job.id);
      toast("ok", t("jobDeleted"));
      setDeleting(null);
      await load();
    } catch (e) {
      toast("err", e?.message === "job_has_applicants" ? t("errJobHasApplicants") : e?.message || t("errGeneric"));
    } finally {
      setBusyId(null);
    }
  }

  async function rescore(job) {
    setBusyId(job.id);
    try {
      const res = await api.rescoreJob(job.id);
      toast("ok", t("rescoredN").replace("{n}", res.rescored_applicants));
      await load();
    } catch (e) {
      toast("err", e?.message || t("errGeneric"));
    } finally {
      setBusyId(null);
    }
  }

  async function toggleStatus(job) {
    setBusyId(job.id);
    try {
      const full = await api.getJob(job.id);
      await api.updateJob(job.id, { ...toPayload(toForm(full)), status: job.status === "open" ? "closed" : "open" });
      await load();
    } catch (e) {
      toast("err", e?.message || t("errGeneric"));
    } finally {
      setBusyId(null);
    }
  }

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const cell = { padding: "12px 16px" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("jobs")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{t("jobsSub")}</p>
        </div>
        {isHr ? (
          <BtnPri onClick={openNew}>{IC.plus} <span>{t("newJob")}</span></BtnPri>
        ) : (
          <span style={{ fontSize: 12, color: S.g400 }}>{t("readOnly")}</span>
        )}
      </div>

      <Card flush>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>{[t("jobTitle"), t("status"), t("viewApplicants"), t("avgScore"), t("reqSkills"), t("act")].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={4} cols={6} />
              ) : jobs.length === 0 ? (
                <tr><td colSpan={6}><Empty text={t("noJobs")} sub={isHr ? t("noJobsHint") : undefined} /></td></tr>
              ) : jobs.map((j) => {
                const st = perJob[j.id];
                const open = j.status === "open";
                return (
                  <tr key={j.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                    <td style={{ ...cell, fontWeight: 600, color: S.g700 }}>
                      {j.title}
                      <small style={{ display: "block", color: S.g400, fontWeight: 400 }}>{[j.department, j.location, j.employment_type].filter(Boolean).join(" · ")}</small>
                    </td>
                    <td style={cell}>
                      <span style={{ fontSize: 11.5, fontWeight: 600, padding: "3px 9px", borderRadius: 999, background: open ? S.okL : S.g100, color: open ? S.ok : S.g500 }}>{t(open ? "jobOpen" : "jobClosed")}</span>
                    </td>
                    <td style={{ ...cell, color: S.g600 }}>{st ? st.applicant_count : "—"}</td>
                    <td style={{ ...cell, color: S.g600 }}>{st?.avg_score != null ? Math.round(st.avg_score) : "—"}</td>
                    <td style={{ ...cell, color: S.g500, maxWidth: 280 }}>{skillIds(j.required_skills).map(nameOf).join(", ") || "—"}</td>
                    <td style={cell}>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button onClick={() => onOpenApplicants(j.id)} style={chipBtn(S.pri)}>{IC.cands} <span>{t("viewApplicants")}</span></button>
                        {isHr && <button onClick={() => openEdit(j.id)} style={chipBtn(S.info)}>{t("editDoc")}</button>}
                        {isHr && (
                          <button onClick={() => toggleStatus(j)} disabled={busyId === j.id} style={chipBtn(open ? S.warn : S.ok)}>{busyId === j.id ? "…" : t(open ? "closeJob" : "reopenJob")}</button>
                        )}
                        {isHr && st && st.applicant_count === 0 && (
                          <button onClick={() => setDeleting(j)} disabled={busyId === j.id} style={chipBtn(S.err)}>{t("del")}</button>
                        )}
                        {isHr && st?.applicant_count > 0 && (
                          <button onClick={() => rescore(j)} disabled={busyId === j.id} title={t("rescoreHint")} style={chipBtn(S.g600)}>{t("rescore")}</button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <ConfirmModal
        open={deleting !== null} onClose={() => setDeleting(null)} onConfirm={removeJob} busy={busyId !== null}
        title={t("confirmDel")}
        body={`${t("del")}: ${deleting?.title || ""} — ${t("irreversible")}`}
        confirmLabel={t("del")} cancelLabel={t("cancel")}
      />
      <Modal open={editing !== null} onClose={() => setEditing(null)} title={t(editing === "new" ? "newJob" : "editJob")} width={720}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
          {editing === "new" && templates.length > 0 && (
            <FG label={t("fromTemplate")}>
              <select style={fld} defaultValue="" onChange={(e) => applyTemplate(e.target.value)}>
                <option value="">{t("blankJob")}</option>
                {templates.map((tpl) => <option key={tpl.id} value={tpl.id}>{tpl.title}</option>)}
              </select>
            </FG>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
            <FG label={t("jobTitle")}><input style={fld} value={form.title} maxLength={200} onChange={(e) => set({ title: e.target.value })} /></FG>
            <FG label={t("dept")}><input style={fld} value={form.department} maxLength={120} onChange={(e) => set({ department: e.target.value })} /></FG>
            <FG label={t("location")}><input style={fld} value={form.location} maxLength={200} onChange={(e) => set({ location: e.target.value })} /></FG>
            <FG label={t("empType")}><input style={fld} value={form.employment_type} maxLength={80} onChange={(e) => set({ employment_type: e.target.value })} /></FG>
            <FG label={t("minYears")}><input style={fld} type="number" min="0" max="80" step="0.5" value={form.min_years} onChange={(e) => set({ min_years: e.target.value })} /></FG>
            <FG label={t("minEdu")}>
              <select style={fld} value={form.min_education} onChange={(e) => set({ min_education: e.target.value })}>
                {EDU_LEVELS.map(([v, k]) => <option key={v} value={v}>{t(k)}</option>)}
              </select>
            </FG>
          </div>
          <FG label={`${t("langsReq")} — ${t("commaHint")}`}><input style={fld} value={form.languages} onChange={(e) => set({ languages: e.target.value })} /></FG>
          <FG label={t("reqSkills")}>
            <SkillPicker value={form.required_skills} onChange={(v) => set({ required_skills: v })} taxonomy={taxonomy} nameOf={nameOf} placeholder={t("addSkill")} />
          </FG>
          <FG label={t("prefSkills")}>
            <SkillPicker value={form.preferred_skills} onChange={(v) => set({ preferred_skills: v })} taxonomy={taxonomy} nameOf={nameOf} placeholder={t("addSkill")} />
          </FG>
          <FG label={t("jobDesc")}>
            <textarea style={{ ...fld, resize: "vertical", minHeight: 70 }} value={form.description} maxLength={20000} onChange={(e) => set({ description: e.target.value })} />
          </FG>

          <div>
            <p style={subHead}>{t("gatesTitle")}</p>
            <p style={{ fontSize: 12, color: S.g400, margin: "2px 0 10px" }}>{t("gatesSub")}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
              {LIST_GATES.map(([k, label]) => (
                <FG key={k} label={`${t(label)} — ${t("commaHint")}`}>
                  <input style={fld} value={form.gateLists[k] || ""} onChange={(e) => set({ gateLists: { ...form.gateLists, [k]: e.target.value } })} />
                </FG>
              ))}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 18px", marginTop: 12 }}>
              {FLAG_GATES.map(([k, label]) => (
                <label key={k} style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, color: S.g600, cursor: "pointer" }}>
                  <input type="checkbox" checked={!!form.gateFlags[k]} onChange={(e) => set({ gateFlags: { ...form.gateFlags, [k]: e.target.checked } })} />
                  {t(label)}
                </label>
              ))}
            </div>
          </div>

          <div>
            <p style={subHead}>{t("weightsTitle")}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10, marginTop: 8 }}>
              {WEIGHT_KEYS.map(([k, label]) => (
                <FG key={k} label={t(label)}>
                  <input style={fld} type="number" min="0" max="100" value={form.weights[k]} onChange={(e) => set({ weights: { ...form.weights, [k]: e.target.value } })} />
                </FG>
              ))}
            </div>
            <div style={{ marginTop: 8, fontSize: 12.5, fontWeight: 600, color: weightSum > 0 ? S.g500 : S.err }}>{t("weightsTotal")}: {weightSum}</div>
          </div>
        </div>
        {err && <div role="alert" style={{ color: S.err, fontSize: 13, marginBottom: 12 }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <BtnSec onClick={() => setEditing(null)}><span>{t("cancel")}</span></BtnSec>
          <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{saving ? "…" : t("save")}</span></BtnPri>
        </div>
      </Modal>
    </div>
  );
}

Jobs.propTypes = {
  lang: PropTypes.string.isRequired,
  user: PropTypes.shape({ role: PropTypes.string }),
  onOpenApplicants: PropTypes.func.isRequired,
};
