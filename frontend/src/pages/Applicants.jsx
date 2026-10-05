import { useEffect, useMemo, useRef, useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, BtnPri, BtnSec, Th, FG, inp, chipBtn } from "../components";
import { Modal, ConfirmModal } from "../modal";
import { useToast } from "../toast";
import { useFocusSearch, useMediaQuery } from "../hooks";
import { EDU_LEVELS, WEIGHT_KEYS } from "./Jobs";

// Full-width fields must include their padding, or they overflow grid cells.
const fld = { ...inp, boxSizing: "border-box" };

const STAGES = ["new", "screened", "shortlisted", "interview", "offer", "hired", "rejected"];
const STAGE_KEY = { new: "stNew", screened: "stScreened", shortlisted: "stShortlisted", interview: "stInterview", offer: "stOffer", hired: "stHired", rejected: "stRejected" };
// Mirrors the server's allowed transitions so the menu only offers legal moves.
const STAGE_NEXT = {
  new: ["screened", "rejected"], screened: ["shortlisted", "rejected"], shortlisted: ["interview", "rejected"],
  interview: ["offer", "rejected"], offer: ["hired", "rejected"], hired: ["rejected"], rejected: ["screened"],
};
const STAGE_COLOR = {
  new: [S.infoL, S.info], screened: [S.g100, S.g600], shortlisted: [S.priL, S.priD], interview: [S.warnL, S.warn],
  offer: [S.priL, S.priD], hired: [S.okL, S.ok], rejected: [S.errL, S.err],
};
const CV_MIME = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  txt: "text/plain",
};
const ERR = {
  duplicate_application: "errDuplicate", job_closed: "errJobClosed", invalid_stage_transition: "errStage",
  notice_required: "errNotice", cv_purged: "frozenNote", invalid_recipient: "errRecipient", stage_emails_disabled: "errEmailsOff",
  preview_outdated: "errPreviewOutdated", criteria_changed: "errCriteriaChanged",
};
const NOTIFY_KEY = { pending: "nsPending", sending: "nsSending", accepted: "nsAccepted", failed: "nsFailed", cancelled: "nsCancelled", unknown: "nsUnknown" };
const EMPTY_UPLOAD = { file: null, full_name: "", email: "", phone: "", nationality: "", city: "", source: "", notes: "", notice_attested: false, notice_channel: "email" };
const CHANNEL_KEY = { email: "chEmail", whatsapp: "chWhatsapp", in_person: "chInPerson", other: "chOther" };
const day = (iso) => (iso ? iso.slice(0, 10) : "");

/** The candidate-facing notice, both languages, with the retention period filled in. */
export function noticeText(lang, days) {
  return ["atsNoticeAr", "atsNoticeEn"].map((k) => L[lang][k].replace("{days}", days)).join("\n\n");
}

const scoreColor = (s) => (s >= 70 ? S.ok : s >= 45 ? S.warn : S.err);
const eduLabel = (t, v) => { const e = EDU_LEVELS.find(([k]) => k === v); return e && v ? t(e[1]) : "—"; };

/** Read a picked file as { name, b64, mime }; null when the type is not a CV. */
function readCv(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const mime = CV_MIME[ext];
  if (!mime) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, mime, b64: String(reader.result).split(",")[1] || "" });
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function StageChip({ stage, t }) {
  const [bg, fg] = STAGE_COLOR[stage] || [S.g100, S.g600];
  return <span style={{ fontSize: 11.5, fontWeight: 600, padding: "3px 9px", borderRadius: 999, background: bg, color: fg, whiteSpace: "nowrap" }}>{t(STAGE_KEY[stage] || stage)}</span>;
}
StageChip.propTypes = { stage: PropTypes.string.isRequired, t: PropTypes.func.isRequired };

function ScoreBar({ value }) {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 110 }}>
      <div style={{ flex: 1, height: 6, borderRadius: 999, background: S.g100, overflow: "hidden" }}>
        <div style={{ width: `${v}%`, height: "100%", background: scoreColor(v) }} />
      </div>
      <span style={{ fontWeight: 700, color: S.g700, minWidth: 24, textAlign: "end" }}>{v}</span>
    </div>
  );
}
ScoreBar.propTypes = { value: PropTypes.number };

/** 0–4 anchored criterion score as four pips. */
function Pips({ n }) {
  return (
    <span aria-label={`${n}/4`} style={{ display: "inline-flex", gap: 3 }}>
      {[0, 1, 2, 3].map((i) => <span key={i} style={{ width: 14, height: 6, borderRadius: 3, background: i < n ? scoreColor(n * 25) : S.g200 }} />)}
    </span>
  );
}
Pips.propTypes = { n: PropTypes.number.isRequired };

export default function Applicants({ lang, user, initialJob }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const toast = useToast();
  const isHr = user?.role === "hr_manager" || user?.role === "hr_officer";
  const isManager = user?.role === "hr_manager";
  const mobile = useMediaQuery("(max-width: 820px)");
  const searchRef = useRef(null);
  useFocusSearch(searchRef);

  const [jobs, setJobs] = useState([]);
  const [jobId, setJobId] = useState(initialJob);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stage, setStage] = useState("");
  const [q, setQ] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [upload, setUpload] = useState(EMPTY_UPLOAD);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [drawerTick, setDrawerTick] = useState(0);
  const [stageReq, setStageReq] = useState(null); // { applicant, stage }
  const [policy, setPolicy] = useState(null);

  const em = (e) => (ERR[e?.message] ? t(ERR[e.message]) : e?.message || t("errGeneric"));
  const job = jobs.find((j) => j.id === jobId);

  useEffect(() => {
    api.listJobs()
      .then((list) => {
        setJobs(list);
        setJobId((cur) => (list.some((j) => j.id === cur) ? cur : (list.find((j) => j.status === "open") || list[0])?.id ?? null));
      })
      .catch(() => toast("err", t("errGeneric")))
      .finally(() => setLoading(false));
    api.recruitmentPolicy().then(setPolicy).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load() {
    if (!jobId) { setRows([]); return; }
    setLoading(true);
    try {
      setRows(await api.listApplicants(jobId, { stage }));
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, stage]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) => [r.full_name, r.email, r.phone, r.city, r.source].some((v) => String(v || "").toLowerCase().includes(needle)));
  }, [rows, q]);

  async function onPick(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { setUploadErr(ar ? "الحجم أكبر من 5MB" : "File exceeds 5MB"); return; }
    const cv = await readCv(file).catch(() => null);
    if (!cv) { setUploadErr(t("errCvType")); return; }
    setUploadErr(null);
    setUpload((u) => ({ ...u, file: cv }));
  }

  async function submitUpload() {
    if (!upload.file) { setUploadErr(t("chooseCv")); return; }
    if (!upload.notice_attested) { setUploadErr(t("errNotice")); return; }
    setUploading(true);
    setUploadErr(null);
    try {
      const { file, ...fields } = upload;
      // The period stated in the notice this page produced is the promise the deletion clock is capped at.
      const created = await api.uploadApplicant(jobId, {
        ...fields, cv_attachment: file.b64, cv_name: file.name, cv_mime: file.mime,
        notice_retention_days: policy?.retention_days,
      });
      toast("ok", t("cvUploaded"));
      setUploadOpen(false);
      setUpload(EMPTY_UPLOAD);
      await load();
      setOpenId(created.id);
    } catch (e) {
      setUploadErr(em(e));
    } finally {
      setUploading(false);
    }
  }

  function closeUpload() {
    setUploadOpen(false);
    setUpload(EMPTY_UPLOAD); // drop the CV bytes from memory as soon as the dialog closes
  }

  async function copyNotice() {
    try {
      await navigator.clipboard.writeText(noticeText(lang, policy.retention_days));
      toast("ok", t("noticeCopied"));
    } catch {
      toast("err", t("errGeneric"));
    }
  }

  const cell = { padding: "12px 16px" };
  const cols = ["#", t("candName"), t("score"), t("stage"), t("years"), t("education"), ""];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("cands")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{t("candsSub")}</p>
        </div>
        {isHr && job && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {isManager && <BtnSec onClick={() => api.exportApplicants(job.id).then(() => toast("ok", t("exportOk"))).catch(() => toast("err", t("errGeneric")))}>{IC.dl} <span>{t("export")}</span></BtnSec>}
            <BtnPri onClick={() => { setUpload(EMPTY_UPLOAD); setUploadErr(null); setUploadOpen(true); }} disabled={job.status !== "open"}>{IC.plus} <span>{t("uploadCv")}</span></BtnPri>
          </div>
        )}
      </div>

      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
          <FG label={t("selectJob")}>
            <select style={fld} value={jobId ?? ""} onChange={(e) => setJobId(e.target.value ? Number(e.target.value) : null)}>
              {jobs.length === 0 && <option value="">{t("noJobs")}</option>}
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}{j.status === "closed" ? ` (${t("jobClosed")})` : ""}</option>)}
            </select>
          </FG>
          <FG label={t("stage")}>
            <select style={fld} value={stage} onChange={(e) => setStage(e.target.value)}>
              <option value="">{t("allStages")}</option>
              {STAGES.map((s) => <option key={s} value={s}>{t(STAGE_KEY[s])}</option>)}
            </select>
          </FG>
          <FG label={t("search").replace("...", "")}>
            <input ref={searchRef} style={fld} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} />
          </FG>
        </div>
      </Card>

      <Card flush>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr>{cols.map((h, i) => <Th key={i} ar={ar}>{h}</Th>)}</tr></thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} cols={cols.length} />
              ) : !jobId ? (
                <tr><td colSpan={cols.length}><Empty text={t("noJobs")} /></td></tr>
              ) : shown.length === 0 ? (
                <tr><td colSpan={cols.length}><Empty text={t("noApplicants")} sub={isHr ? t("noApplicantsHint") : undefined} /></td></tr>
              ) : shown.map((r, i) => (
                <tr key={r.id} onClick={() => setOpenId(r.id)} style={{ borderBottom: `1px solid ${S.g100}`, cursor: "pointer", background: openId === r.id ? S.g50 : undefined }}>
                  <td style={{ ...cell, color: S.g400, fontWeight: 600 }}>{i + 1}</td>
                  <td style={{ ...cell, fontWeight: 600, color: S.g700 }}>
                    <button onClick={(e) => { e.stopPropagation(); setOpenId(r.id); }} style={{ border: "none", background: "transparent", padding: 0, font: "inherit", color: "inherit", cursor: "pointer", textAlign: "inherit" }}>{r.full_name || r.email || `#${r.id}`}</button>
                    <small style={{ display: "block", color: S.g400, fontWeight: 400, direction: "ltr", textAlign: ar ? "right" : "left" }}>{r.email}</small>
                  </td>
                  <td style={cell}><ScoreBar value={r.score} /></td>
                  <td style={cell} onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <StageChip stage={r.stage} t={t} />
                      {isHr && (
                        <select aria-label={t("moveTo")} value="" onChange={(e) => e.target.value && setStageReq({ applicant: r, stage: e.target.value })} style={{ ...fld, width: 34, padding: "4px 2px", fontSize: 12 }}>
                          <option value="">⋯</option>
                          {(STAGE_NEXT[r.stage] || []).filter((s) => !r.cv_purged_at || s === "rejected").map((s) => <option key={s} value={s}>{t(STAGE_KEY[s])}</option>)}
                        </select>
                      )}
                    </div>
                  </td>
                  <td style={{ ...cell, color: S.g600 }}>{r.years_experience ?? "—"}</td>
                  <td style={{ ...cell, color: S.g600 }}>{eduLabel(t, r.education)}</td>
                  <td style={cell}>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {r.gate_failures?.length > 0 && <span title={r.gate_failures.join(", ")} style={{ ...chipBtn(S.err), cursor: "default" }}>{IC.warn2} {t("gateFailed")}</span>}
                      {r.needs_manual_review && <span style={{ ...chipBtn(S.warn), cursor: "default" }}>{t("needsReview")}</span>}
                      {r.score_stale && <span title={t("scoreStale")} style={{ ...chipBtn(S.g500), cursor: "default" }}>{t("staleShort")}</span>}
                      {r.cv_purged_at && <span style={{ ...chipBtn(S.g500), cursor: "default" }}>{t("cvRemovedShort")}</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={uploadOpen} onClose={closeUpload} title={`${t("uploadCv")} — ${job?.title || ""}`} width={560}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
          <FG label={t("uploadCvSub")}>
            <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", borderRadius: S.r2, border: `1.5px dashed ${S.g300}`, cursor: "pointer", background: S.g50, fontSize: 13, color: S.g500 }}>
              {IC.upload}
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{upload.file?.name || t("chooseCv")}</span>
              <input type="file" accept=".pdf,.docx,.txt" onChange={onPick} style={{ display: "none" }} />
            </label>
          </FG>
          <p style={{ fontSize: 12, color: S.g400, margin: 0 }}>{t("blankFromCv")}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
            {[["full_name", "candName", 200], ["email", "email", 254], ["phone", "phone", 80], ["nationality", "nationality", 120], ["city", "city", 120], ["source", "source", 120]].map(([k, label, max]) => (
              <FG key={k} label={t(label)}>
                <input style={fld} value={upload[k]} maxLength={max} onChange={(e) => setUpload({ ...upload, [k]: e.target.value })} />
              </FG>
            ))}
          </div>
          <FG label={t("notes")}>
            <textarea style={{ ...fld, resize: "vertical", minHeight: 56 }} value={upload.notes} maxLength={5000} onChange={(e) => setUpload({ ...upload, notes: e.target.value })} />
          </FG>
          <div style={{ border: `1px solid ${upload.notice_attested ? S.g200 : S.warn}`, borderRadius: S.r2, padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            <label style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 13, color: S.g700, cursor: "pointer" }}>
              <input type="checkbox" checked={upload.notice_attested} onChange={(e) => setUpload({ ...upload, notice_attested: e.target.checked })} style={{ marginTop: 3 }} />
              <span>{t("noticeAttest")}</span>
            </label>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 160 }}>
                <FG label={t("noticeChannel")}>
                  <select style={fld} value={upload.notice_channel} onChange={(e) => setUpload({ ...upload, notice_channel: e.target.value })}>
                    {Object.entries(CHANNEL_KEY).map(([v, k]) => <option key={v} value={v}>{t(k)}</option>)}
                  </select>
                </FG>
              </div>
              <BtnSec onClick={copyNotice} disabled={!policy}><span>{t("copyNotice")}</span></BtnSec>
            </div>
          </div>
        </div>
        {uploadErr && <div role="alert" style={{ color: S.err, fontSize: 13, marginBottom: 12 }}>{uploadErr}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <BtnSec onClick={closeUpload}><span>{t("cancel")}</span></BtnSec>
          <BtnPri onClick={submitUpload} disabled={uploading}>{IC.check} <span>{uploading ? "…" : t("uploadCv")}</span></BtnPri>
        </div>
      </Modal>

      {openId != null && (
        <ApplicantDrawer
          key={openId} id={openId} tick={drawerTick} lang={lang} t={t} ar={ar} mobile={mobile}
          isHr={isHr} isManager={isManager} em={em}
          onClose={() => setOpenId(null)} onChanged={load}
          onDeleted={() => { setOpenId(null); load(); }}
          onRequestMove={(applicant, next) => setStageReq({ applicant, stage: next })}
        />
      )}

      {stageReq && (
        <StageDialog
          req={stageReq} policy={policy} t={t} lang={lang} em={em}
          onClose={() => setStageReq(null)}
          onDone={() => { setStageReq(null); load(); setDrawerTick((n) => n + 1); }}
        />
      )}
    </div>
  );
}

Applicants.propTypes = {
  lang: PropTypes.string.isRequired,
  user: PropTypes.shape({ role: PropTypes.string }),
  initialJob: PropTypes.number,
};

const TABS = [["eval", "tabEval"], ["profile", "tabProfile"], ["cv", "attach"], ["interview", "tabInterview"], ["history", "history"]];

/** One confirmation flow for every stage move: note, and an opt-in candidate email with a preview. */
function StageDialog({ req, policy, t, lang, em, onClose, onDone }) {
  const toast = useToast();
  const { applicant, stage } = req;
  const canEmail = !!policy?.stage_emails_enabled && (policy.email_stages || []).includes(stage) && !applicant.cv_purged_at;
  const [note, setNote] = useState("");
  const [notify, setNotify] = useState(false);
  const [mailLang, setMailLang] = useState(lang);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Drop the old preview immediately and ignore late answers, so HR can only
    // confirm the message actually on screen (the server checks its hash too).
    setPreview(null);
    if (!notify) return undefined;
    let live = true;
    api.stageEmailPreview(applicant.id, stage, mailLang)
      .then((p) => { if (live) setPreview(p); })
      .catch((e) => live && toast("err", em(e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notify, mailLang]);

  async function confirm() {
    setBusy(true);
    try {
      await api.moveStage(applicant.id, stage, note, notify ? { notify: true, notify_language: mailLang, preview_hash: preview.hash } : {});
      toast("ok", t(notify ? "emailQueued" : "stageMoved"));
      onDone();
    } catch (e) {
      toast("err", em(e));
    } finally {
      setBusy(false);
    }
  }

  const blocked = notify && preview && !preview.valid_recipient;
  return (
    <Modal open onClose={onClose} title={`${t("moveStageTitle")}: ${t(STAGE_KEY[stage])} — ${applicant.full_name || applicant.email || ""}`} width={560}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
        <FG label={t("stageNote")}>
          <textarea style={{ ...fld, resize: "vertical", minHeight: 50 }} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </FG>
        {canEmail && (
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: S.g700, cursor: "pointer" }}>
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
            {t("emailCandidate")}
          </label>
        )}
        {notify && (
          <>
            <FG label={t("emailLang")}>
              <select style={fld} value={mailLang} onChange={(e) => setMailLang(e.target.value)}>
                <option value="ar">{t("langAr")}</option>
                <option value="en">{t("langEn")}</option>
              </select>
            </FG>
            {preview && (
              <div style={{ ...box, background: S.g50, fontSize: 13 }}>
                <div style={{ color: preview.valid_recipient ? S.g600 : S.err, direction: "ltr", textAlign: "start" }}>{t("emailTo")}: {preview.to || "—"}</div>
                {!preview.valid_recipient && <div role="alert" style={{ color: S.err, marginTop: 4 }}>{t("errRecipient")}</div>}
                <div style={{ fontWeight: 700, color: S.g800, marginTop: 8 }} dir={mailLang === "ar" ? "rtl" : "ltr"}>{preview.subject}</div>
                <div style={{ whiteSpace: "pre-wrap", color: S.g600, marginTop: 6 }} dir={mailLang === "ar" ? "rtl" : "ltr"}>{preview.body}</div>
              </div>
            )}
          </>
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
        <BtnSec onClick={onClose}><span>{t("cancel")}</span></BtnSec>
        <BtnPri onClick={confirm} disabled={busy || blocked || (notify && !preview)}>{IC.check} <span>{busy ? "…" : t("confirmMove")}</span></BtnPri>
      </div>
    </Modal>
  );
}
StageDialog.propTypes = {
  req: PropTypes.shape({ applicant: PropTypes.object.isRequired, stage: PropTypes.string.isRequired }).isRequired,
  policy: PropTypes.object, t: PropTypes.func.isRequired, lang: PropTypes.string.isRequired, em: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired, onDone: PropTypes.func.isRequired,
};

function ApplicantDrawer({ id, tick, t, ar, mobile, isHr, isManager, em, onClose, onChanged, onDeleted, onRequestMove }) {
  const toast = useToast();
  const [a, setA] = useState(null);
  const [tab, setTab] = useState("eval");
  const [confirmDel, setConfirmDel] = useState(false);
  const [eraseAll, setEraseAll] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purgeReason, setPurgeReason] = useState("withdrawn");

  async function reload() {
    try {
      setA(await api.getApplicant(id));
    } catch (e) {
      toast("err", em(e));
      onClose();
    }
  }
  // While a candidate email is still queued or sending, re-read every few seconds so
  // History shows the final status (accepted / failed / cancelled) without a manual reload.
  const emailInFlight = (a?.history || []).some((h) => h.notify_status === "pending" || h.notify_status === "sending");
  useEffect(() => {
    if (!emailInFlight) return undefined;
    const timer = setTimeout(reload, 4000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a, emailInFlight]);

  useEffect(() => {
    reload();
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, tick]);

  async function changed() {
    await reload();
    onChanged();
  }

  async function purge() {
    setDeleting(true);
    try {
      await api.purgeCv(id, purgeReason);
      toast("ok", t("cvRemovedOk"));
      setPurgeOpen(false);
      await changed();
    } catch (e) {
      toast("err", em(e));
    } finally {
      setDeleting(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await api.deleteApplicant(id, eraseAll ? { reason: "erasure_request", allForEmail: true } : {});
      toast("ok", t("delOk"));
      setConfirmDel(false);
      onDeleted();
    } catch (e) {
      toast("err", em(e));
    } finally {
      setDeleting(false);
    }
  }

  const side = ar ? { left: 0 } : { right: 0 };
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(8,14,22,.35)", zIndex: 800, animation: "hr-fade-in .15s ease" }} />
      <aside role="dialog" aria-modal="true" aria-label={a?.full_name || t("cands")} style={{ position: "fixed", top: 0, bottom: 0, ...side, width: mobile ? "100vw" : 600, maxWidth: "100vw", background: S.w, borderInlineStart: `1px solid ${S.g200}`, boxShadow: S.sh2, zIndex: 801, display: "flex", flexDirection: "column" }}>
        {!a ? (
          <div style={{ padding: 24, color: S.g400 }}>{t("loading")}</div>
        ) : (
          <>
            <div style={{ padding: "20px 24px 0", borderBottom: `1px solid ${S.g100}` }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: S.g800 }}>{a.full_name || a.email || `#${a.id}`}</h3>
                  <div style={{ fontSize: 12.5, color: S.g400, marginTop: 3, direction: "ltr", textAlign: ar ? "right" : "left" }}>{[a.email, a.phone].filter(Boolean).join(" · ")}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1, color: scoreColor(a.score) }}>{Math.round(a.score)}</div>
                    <div style={{ fontSize: 10.5, color: S.g400, fontWeight: 600 }}>{t("score")}</div>
                  </div>
                  <button onClick={onClose} aria-label={t("close")} style={{ border: "none", background: S.g100, color: S.g500, width: 30, height: 30, borderRadius: S.r2, cursor: "pointer", fontSize: 16, fontFamily: "inherit" }}>×</button>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
                <StageChip stage={a.stage} t={t} />
                {isHr && (STAGE_NEXT[a.stage] || []).filter((s) => !a.cv_purged_at || s === "rejected").map((s) => (
                  <button key={s} onClick={() => onRequestMove(a, s)} style={chipBtn(s === "rejected" ? S.err : S.pri)}>→ {t(STAGE_KEY[s])}</button>
                ))}
                {a.needs_manual_review && <span style={{ ...chipBtn(S.warn), cursor: "default" }}>{t("needsReview")}</span>}
                {isManager && (
                  <span style={{ display: "inline-flex", gap: 6, marginInlineStart: "auto" }}>
                    {!a.cv_purged_at && <button onClick={() => setPurgeOpen(true)} style={chipBtn(S.warn)}>{t("removeCv")}</button>}
                    <button onClick={() => { setEraseAll(false); setConfirmDel(true); }} style={chipBtn(S.err)}>{t("del")}</button>
                  </span>
                )}
              </div>
              {(a.erase_after || a.cv_purged_at || a.score_stale) && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10, fontSize: 12 }}>
                  {a.cv_purged_at && <span style={{ color: S.warn, fontWeight: 600 }}>{t("cvRemovedOn").replace("{d}", day(a.cv_purged_at))} — {t("frozenNote")}</span>}
                  {a.erase_after && <span style={{ color: S.g500 }}>{t("eraseOn").replace("{d}", day(a.erase_after))}</span>}
                  {a.score_stale && <span style={{ color: S.g500 }}>{t("scoreStale")}</span>}
                </div>
              )}
              <div role="tablist" style={{ display: "flex", gap: 2, overflowX: "auto" }}>
                {TABS.map(([k, label]) => (
                  <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} style={{ padding: "8px 12px", border: "none", borderBottom: `2px solid ${tab === k ? S.pri : "transparent"}`, background: "transparent", color: tab === k ? S.priD : S.g400, fontWeight: 600, fontSize: 12.5, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap" }}>{t(label)}</button>
                ))}
              </div>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
              {tab === "eval" && <EvalTab a={a} t={t} />}
              {tab === "profile" && <ProfileTab a={a} t={t} isHr={isHr && !a.cv_purged_at} em={em} onSaved={changed} />}
              {tab === "cv" && <CvTab a={a} t={t} isManager={isManager} em={em} />}
              {tab === "interview" && <InterviewTab a={a} t={t} em={em} onSaved={changed} canAdd={!a.cv_purged_at} />}
              {tab === "history" && <HistoryTab a={a} t={t} />}
            </div>
          </>
        )}
      </aside>
      <ConfirmModal
        open={confirmDel} onClose={() => setConfirmDel(false)} onConfirm={remove} busy={deleting}
        title={t("confirmDel")}
        body={(
          <>
            {`${t("del")}: ${a?.full_name || a?.email || ""} — ${t("irreversible")}`}
            {a?.email && (
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, color: S.g700, cursor: "pointer" }}>
                <input type="checkbox" checked={eraseAll} onChange={(e) => setEraseAll(e.target.checked)} />
                {t("erasureAll")}
              </label>
            )}
          </>
        )}
        confirmLabel={t("del")} cancelLabel={t("cancel")}
      />
      <Modal open={purgeOpen} onClose={() => setPurgeOpen(false)} title={t("removeCvTitle")} width={480}>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: S.g500, lineHeight: 1.6 }}>{t("removeCvBody")}</p>
        <FG label={t("removeReason")}>
          <select style={fld} value={purgeReason} onChange={(e) => setPurgeReason(e.target.value)}>
            <option value="withdrawn">{t("reasonWithdrawn")}</option>
            <option value="manual">{t("reasonManual")}</option>
          </select>
        </FG>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
          <BtnSec onClick={() => setPurgeOpen(false)}><span>{t("cancel")}</span></BtnSec>
          <button onClick={purge} disabled={deleting} style={{ ...chipBtn("#fff"), background: S.err, border: "none", padding: "9px 18px", fontSize: 13 }}>{deleting ? "…" : t("removeCv")}</button>
        </div>
      </Modal>
    </>
  );
}

ApplicantDrawer.propTypes = {
  id: PropTypes.number.isRequired, tick: PropTypes.number, t: PropTypes.func.isRequired, ar: PropTypes.bool, mobile: PropTypes.bool,
  isHr: PropTypes.bool, isManager: PropTypes.bool, em: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired, onChanged: PropTypes.func.isRequired, onDeleted: PropTypes.func.isRequired,
  onRequestMove: PropTypes.func.isRequired,
};

const CRIT_LABEL = Object.fromEntries(WEIGHT_KEYS);
const box = { border: `1px solid ${S.g100}`, borderRadius: S.r2, padding: 14 };

function EvalTab({ a, t }) {
  const failed = a.gate_failures || [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {failed.length > 0 && (
        <div role="alert" style={{ ...box, borderColor: S.err, background: S.errL, color: S.err, fontSize: 13 }}>
          <strong>{t("gatesFailedList")}:</strong> {failed.join(", ")}
        </div>
      )}
      {(a.score_breakdown || []).map((c) => (
        <div key={c.criterion} style={box}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <span style={{ fontWeight: 700, color: S.g700, fontSize: 13.5 }}>{t(CRIT_LABEL[c.criterion] || c.criterion)}</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12, color: S.g400 }}>
              <Pips n={c.score_0_4} /> {c.score_0_4}/4 · ×{c.weight}
            </span>
          </div>
          {c.evidence?.length > 0 ? (
            <ul style={{ margin: "10px 0 0", paddingInlineStart: 18, display: "flex", flexDirection: "column", gap: 4 }}>
              {c.evidence.slice(0, 8).map((e, i) => (
                <li key={i} style={{ fontSize: 12.5, color: S.g600 }}>
                  <strong style={{ color: S.g700 }}>{e.term}</strong> — <span style={{ color: S.g500 }}>{e.line}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ margin: "8px 0 0", fontSize: 12.5, color: S.g400 }}>{t(a.cv_purged_at ? "cvRemovedShort" : "noEvidence")}</p>
          )}
          {c.missing?.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 10, alignItems: "center" }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: S.err }}>{t("missing")}:</span>
              {c.missing.map((m) => <span key={m} style={{ fontSize: 11.5, padding: "2px 8px", borderRadius: 999, background: S.errL, color: S.err }}>{m}</span>)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
EvalTab.propTypes = { a: PropTypes.object.isRequired, t: PropTypes.func.isRequired };

function ProfileTab({ a, t, isHr, em, onSaved }) {
  const toast = useToast();
  const p = a.parsed || {};
  const c = a.corrections || {};
  const [f, setF] = useState({
    years_experience: c.years_experience ?? "",
    education: c.education ?? "",
    languages: (c.languages || []).join(", "),
    nationality: c.nationality ?? "",
    city: c.city ?? "",
    notes: a.notes || "",
  });
  const [saving, setSaving] = useState(false);

  async function save() {
    const corrections = {};
    if (f.years_experience !== "") corrections.years_experience = Number(f.years_experience);
    if (f.education) corrections.education = f.education;
    const langs = f.languages.split(/[,،]/).map((x) => x.trim()).filter(Boolean);
    if (langs.length) corrections.languages = langs;
    if (f.nationality.trim()) corrections.nationality = f.nationality.trim();
    if (f.city.trim()) corrections.city = f.city.trim();
    setSaving(true);
    try {
      await api.patchApplicant(a.id, { corrections, notes: f.notes });
      toast("ok", t("rescored"));
      await onSaved();
    } catch (e) {
      toast("err", em(e));
    } finally {
      setSaving(false);
    }
  }

  const read = [
    [t("yearsExp"), p.years_experience ?? "—"],
    [t("education"), p.education ? eduLabel(t, p.education) : "—"],
    [t("wLanguages"), (p.languages || []).join(", ") || "—"],
    [t("nationality"), a.nationality || p.nationality || "—"],
    [t("city"), a.city || p.city || "—"],
    [t("source"), a.source || "—"],
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={box}>
        <div style={{ fontSize: 12, fontWeight: 700, color: S.g400, marginBottom: 8, textTransform: "uppercase", letterSpacing: ".05em" }}>{t("readFromCv")}</div>
        <dl style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "6px 16px", margin: 0, fontSize: 13 }}>
          {read.map(([k, v]) => [<dt key={`${k}t`} style={{ color: S.g400 }}>{k}</dt>, <dd key={`${k}d`} style={{ margin: 0, color: S.g700 }}>{v}</dd>])}
        </dl>
        {(p.skills || []).length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 10 }}>
            {p.skills.map((s) => <span key={s.id} style={{ fontSize: 11.5, padding: "2px 8px", borderRadius: 999, background: S.priL, color: S.priD }}>{s.canonical}</span>)}
          </div>
        )}
      </div>
      {isHr && (
        <div style={box}>
          <div style={{ fontWeight: 700, color: S.g700, fontSize: 13.5 }}>{t("hrCorrections")}</div>
          <p style={{ fontSize: 12, color: S.g400, margin: "2px 0 12px" }}>{t("hrCorrectionsSub")}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
            <FG label={t("yearsExp")}><input style={fld} type="number" min="0" max="80" step="0.5" value={f.years_experience} onChange={(e) => setF({ ...f, years_experience: e.target.value })} /></FG>
            <FG label={t("education")}>
              <select style={fld} value={f.education} onChange={(e) => setF({ ...f, education: e.target.value })}>
                {EDU_LEVELS.map(([v, k]) => <option key={v} value={v}>{v ? t(k) : "—"}</option>)}
              </select>
            </FG>
            <FG label={t("nationality")}><input style={fld} value={f.nationality} maxLength={120} onChange={(e) => setF({ ...f, nationality: e.target.value })} /></FG>
            <FG label={t("city")}><input style={fld} value={f.city} maxLength={120} onChange={(e) => setF({ ...f, city: e.target.value })} /></FG>
          </div>
          <div style={{ marginTop: 10 }}>
            <FG label={`${t("wLanguages")} — ${t("commaHint")}`}><input style={fld} value={f.languages} onChange={(e) => setF({ ...f, languages: e.target.value })} /></FG>
          </div>
          <div style={{ marginTop: 10 }}>
            <FG label={t("notes")}><textarea style={{ ...fld, resize: "vertical", minHeight: 56 }} value={f.notes} maxLength={5000} onChange={(e) => setF({ ...f, notes: e.target.value })} /></FG>
          </div>
          <div style={{ marginTop: 12 }}>
            <BtnPri onClick={save} disabled={saving}>{IC.check} <span>{saving ? "…" : t("saveRescore")}</span></BtnPri>
          </div>
        </div>
      )}
    </div>
  );
}
ProfileTab.propTypes = { a: PropTypes.object.isRequired, t: PropTypes.func.isRequired, isHr: PropTypes.bool, em: PropTypes.func.isRequired, onSaved: PropTypes.func.isRequired };

function CvTab({ a, t, isManager, em }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true);
    try {
      const cv = await api.applicantCv(a.id);
      const bytes = Uint8Array.from(atob(cv.cv_attachment), (ch) => ch.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: cv.cv_mime }));
      const link = document.createElement("a");
      link.href = url;
      link.download = cv.cv_name || `cv_${a.id}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      toast("err", em(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ ...box, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8, color: S.g600, fontSize: 13 }}>{IC.clip} {a.cv_name || "—"}</span>
      {a.cv_purged_at ? (
        <span style={{ fontSize: 12, color: S.g400 }}>{t("cvRemovedOn").replace("{d}", day(a.cv_purged_at))}</span>
      ) : isManager ? (
        <BtnSec onClick={open} disabled={busy || !a.has_cv}>{IC.dl} <span>{busy ? "…" : t("downloadCv")}</span></BtnSec>
      ) : (
        <span style={{ fontSize: 12, color: S.g400 }}>{t("cvManagerOnly")}</span>
      )}
    </div>
  );
}
CvTab.propTypes = { a: PropTypes.object.isRequired, t: PropTypes.func.isRequired, isManager: PropTypes.bool, em: PropTypes.func.isRequired };

function InterviewTab({ a, t, em, onSaved, canAdd }) {
  const toast = useToast();
  const [result, setResult] = useState("cleared");
  const [ratings, setRatings] = useState([{ skill: "", score_1_5: 3 }]);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api.addFeedback(a.id, { result, comment, ratings: ratings.filter((r) => r.skill.trim()).map((r) => ({ skill: r.skill.trim(), score_1_5: Number(r.score_1_5) })) });
      toast("ok", t("fbSaved"));
      setRatings([{ skill: "", score_1_5: 3 }]);
      setComment("");
      await onSaved();
    } catch (e) {
      toast("err", em(e));
    } finally {
      setSaving(false);
    }
  }
  const setRating = (i, patch) => setRatings((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {(a.feedback || []).length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: S.g400 }}>{t("noFeedback")}</p>
      ) : a.feedback.map((fb) => (
        <div key={fb.id} style={box}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 12.5 }}>
            <span style={{ fontWeight: 700, color: fb.result === "cleared" ? S.ok : S.err }}>{t(fb.result === "cleared" ? "cleared" : "fbRejected")}</span>
            <span style={{ color: S.g400 }}>{fb.interviewer} · {fb.created_at}</span>
          </div>
          {fb.ratings?.length > 0 && (
            <div style={{ fontSize: 12.5, color: S.g600, marginTop: 6 }}>
              {fb.ratings.map((r) => `${r.skill}: ${r.score_1_5}/5`).join(" · ")} — {t("avgRating")} {fb.avg_rating}
            </div>
          )}
          {fb.comment && <p style={{ margin: "6px 0 0", fontSize: 13, color: S.g700, whiteSpace: "pre-wrap" }}>{fb.comment}</p>}
        </div>
      ))}
      {canAdd && <div style={box}>
        <div style={{ fontWeight: 700, color: S.g700, fontSize: 13.5, marginBottom: 10 }}>{t("addFeedback")}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <FG label={t("fbResult")}>
            <select style={fld} value={result} onChange={(e) => setResult(e.target.value)}>
              <option value="cleared">{t("cleared")}</option>
              <option value="rejected">{t("fbRejected")}</option>
            </select>
          </FG>
          <FG label={t("ratings")}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {ratings.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 6 }}>
                  <input style={fld} placeholder={t("ratingSkill")} value={r.skill} maxLength={120} onChange={(e) => setRating(i, { skill: e.target.value })} />
                  <select style={{ ...fld, width: 70 }} value={r.score_1_5} onChange={(e) => setRating(i, { score_1_5: e.target.value })}>
                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
              ))}
              <button type="button" onClick={() => setRatings([...ratings, { skill: "", score_1_5: 3 }])} style={{ ...chipBtn(S.pri), alignSelf: "flex-start" }}>{IC.plus} {t("addRating")}</button>
            </div>
          </FG>
          <FG label={t("fbComment")}>
            <textarea style={{ ...fld, resize: "vertical", minHeight: 60 }} value={comment} maxLength={5000} onChange={(e) => setComment(e.target.value)} />
          </FG>
          <div><BtnPri onClick={save} disabled={saving}>{IC.check} <span>{saving ? "…" : t("save")}</span></BtnPri></div>
        </div>
      </div>}
    </div>
  );
}
InterviewTab.propTypes = { a: PropTypes.object.isRequired, t: PropTypes.func.isRequired, em: PropTypes.func.isRequired, onSaved: PropTypes.func.isRequired, canAdd: PropTypes.bool };

function HistoryTab({ a, t }) {
  const items = a.history || [];
  if (items.length === 0) return <p style={{ margin: 0, fontSize: 13, color: S.g400 }}>{t("noStageHistory")}</p>;
  return (
    <ol style={{ margin: 0, paddingInlineStart: 18, display: "flex", flexDirection: "column", gap: 10 }}>
      {items.map((h) => (
        <li key={h.id} style={{ fontSize: 13, color: S.g600 }}>
          <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            <StageChip stage={h.old_stage} t={t} /> → <StageChip stage={h.new_stage} t={t} />
          </span>
          <div style={{ fontSize: 12, color: S.g400, marginTop: 3 }}>{h.changed_at} · {t("by")} {h.changed_by}</div>
          {NOTIFY_KEY[h.notify_status] && (
            <div style={{ fontSize: 12, marginTop: 2, color: h.notify_status === "accepted" ? S.ok : h.notify_status === "pending" || h.notify_status === "sending" ? S.g500 : S.err }}>
              {t(NOTIFY_KEY[h.notify_status])}{h.notified_at ? ` · ${h.notified_at.replace("T", " ").replace("Z", " UTC")}` : ""}
            </div>
          )}
          {h.note && <div style={{ fontSize: 12.5, color: S.g600, marginTop: 2 }}>{h.note}</div>}
        </li>
      ))}
    </ol>
  );
}
HistoryTab.propTypes = { a: PropTypes.object.isRequired, t: PropTypes.func.isRequired };
