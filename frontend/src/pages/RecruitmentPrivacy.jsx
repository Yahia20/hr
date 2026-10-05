import { useEffect, useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { BtnPri, BtnSec, FG, inp } from "../components";
import { ConfirmModal } from "../modal";
import { useToast } from "../toast";

const fld = { ...inp, boxSizing: "border-box" };
const STAGE_KEY = { interview: "stInterview", offer: "stOffer", rejected: "stRejected" };

/** Retention period + sweep controls, and the opt-in candidate stage emails (HR Manager, inside Settings). */
export default function RecruitmentPrivacy({ lang }) {
  const t = (k) => L[lang][k] || k;
  const toast = useToast();
  const [ret, setRet] = useState(null);
  const [days, setDays] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [mail, setMail] = useState(null);
  const [mailSaving, setMailSaving] = useState(false);

  const loadRet = () => api.getRetention().then((r) => { setRet(r); setDays(String(r.days)); }).catch(() => toast("err", t("errGeneric")));
  useEffect(() => {
    loadRet();
    api.getEmailSettings().then(setMail).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveDays() {
    setBusy(true);
    try {
      const r = await api.setRetention(Number(days));
      setRet(r);
      toast("ok", t("savedOk"));
    } catch (e) {
      toast("err", e?.message || t("errGeneric"));
    } finally {
      setBusy(false);
    }
  }

  async function run(dryRun) {
    setBusy(true);
    try {
      const r = await api.runRetention(dryRun);
      toast("ok", dryRun ? t("retPreviewN").replace("{n}", r.due) : t("retDeletedN").replace("{n}", r.deleted));
      setConfirmRun(false);
      if (!dryRun) await loadRet();
    } catch (e) {
      toast("err", e?.message || t("errGeneric"));
    } finally {
      setBusy(false);
    }
  }

  async function saveMail() {
    setMailSaving(true);
    try {
      const r = await api.setEmailSettings({ enabled: mail.enabled, templates: mail.templates });
      setMail({ ...mail, ...r });
      toast("ok", t("savedOk"));
    } catch (e) {
      toast("err", e?.message || t("errGeneric"));
    } finally {
      setMailSaving(false);
    }
  }

  const setTpl = (stage, lng, key, value) => setMail((m) => ({
    ...m, templates: { ...m.templates, [stage]: { ...m.templates[stage], [lng]: { ...m.templates[stage][lng], [key]: value } } },
  }));
  const last = ret?.last_run?.last_attempt;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {ret && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <FG label={t("retDays")}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input style={{ ...fld, width: 120 }} type="number" min={ret.min_days} max={ret.max_days} value={days} onChange={(e) => setDays(e.target.value)} />
              <BtnPri onClick={saveDays} disabled={busy || String(ret.days) === days}>{IC.check} <span>{t("save")}</span></BtnPri>
            </div>
          </FG>
          <div style={{ fontSize: 12, color: S.g400 }}>{t("retDaysSub")}</div>
          <div style={{ fontSize: 13, color: S.g600 }}>
            {t("retDue")}: <strong>{ret.due_now}</strong>
            {last && <span style={{ color: S.g400 }}> · {t("retLastRun")}: {last.at?.replace("T", " ").replace("Z", " UTC")} ({last.deleted}/{last.due}{last.failed ? `, ${last.failed} ✕` : ""})</span>}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <BtnSec onClick={() => run(true)} disabled={busy}><span>{t("retPreview")}</span></BtnSec>
            <BtnSec onClick={() => setConfirmRun(true)} disabled={busy || ret.due_now === 0}><span>{t("retRunNow")}</span></BtnSec>
          </div>
        </div>
      )}

      {mail && (
        <div style={{ borderTop: `1px solid ${S.g100}`, paddingTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
            <input type="checkbox" checked={mail.enabled} onChange={(e) => setMail({ ...mail, enabled: e.target.checked })} style={{ marginTop: 3 }} />
            <span>
              <span style={{ display: "block", fontSize: 13.5, fontWeight: 600, color: S.g700 }}>{t("stageEmails")}</span>
              <span style={{ display: "block", fontSize: 12, color: S.g400, marginTop: 2 }}>{t("stageEmailsSub")}</span>
            </span>
          </label>
          {!mail.email_configured && <div style={{ fontSize: 12, color: S.warn }}>{t("emailNotConfigured")}</div>}
          <div style={{ fontSize: 12, color: S.g400 }}>{t("tplHint")}</div>
          {mail.stages.map((stage) => (
            <div key={stage} style={{ border: `1px solid ${S.g100}`, borderRadius: S.r2, padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: S.g700 }}>{t(STAGE_KEY[stage])}</div>
              {["ar", "en"].map((lng) => (
                <div key={lng} dir={lng === "ar" ? "rtl" : "ltr"} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <FG label={`${t("tplSubject")} (${t(lng === "ar" ? "langAr" : "langEn")})`}>
                    <input style={fld} value={mail.templates[stage][lng].subject} maxLength={200} onChange={(e) => setTpl(stage, lng, "subject", e.target.value)} />
                  </FG>
                  <FG label={t("tplBody")}>
                    <textarea style={{ ...fld, resize: "vertical", minHeight: 90 }} value={mail.templates[stage][lng].body} maxLength={5000} onChange={(e) => setTpl(stage, lng, "body", e.target.value)} />
                  </FG>
                </div>
              ))}
            </div>
          ))}
          <div><BtnPri onClick={saveMail} disabled={mailSaving}>{IC.check} <span>{mailSaving ? "…" : t("save")}</span></BtnPri></div>
        </div>
      )}

      <ConfirmModal
        open={confirmRun} onClose={() => setConfirmRun(false)} onConfirm={() => run(false)} busy={busy}
        title={t("retRunNow")} body={t("retRunConfirm")} confirmLabel={t("del")} cancelLabel={t("cancel")}
      />
    </div>
  );
}

RecruitmentPrivacy.propTypes = { lang: PropTypes.string.isRequired };
