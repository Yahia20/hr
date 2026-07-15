import { useEffect, useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, BtnPri, BtnSec, inp } from "../components";
import { useToast } from "../toast";

const ROLE_LABEL_KEY = { hr_manager: "roleManager", hr_officer: "roleOfficer", dept_head: "roleDeptHead", employee: "roleEmployee" };

function Switch({ on, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onChange}
      style={{
        width: 42, height: 24, borderRadius: 999, border: "none", cursor: "pointer", flexShrink: 0,
        padding: 0, position: "relative", transition: S.tr,
        background: on ? S.pri : S.g300,
      }}
    >
      <span style={{
        position: "absolute", top: 3, insetInlineStart: on ? 21 : 3, width: 18, height: 18,
        borderRadius: "50%", background: "#fff", transition: "inset-inline-start .18s cubic-bezier(.4,0,.2,1)",
        boxShadow: "0 1px 3px rgba(0,0,0,.3)",
      }} />
    </button>
  );
}
Switch.propTypes = { on: PropTypes.bool.isRequired, onChange: PropTypes.func.isRequired, label: PropTypes.string };

function Section({ icon, title, sub, children }) {
  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
        <div style={{ width: 38, height: 38, borderRadius: S.r2, background: S.priL, color: S.pri, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{icon}</div>
        <div>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: S.g800, margin: 0 }}>{title}</h3>
          {sub && <p style={{ fontSize: 12.5, color: S.g400, margin: "2px 0 0" }}>{sub}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}
Section.propTypes = { icon: PropTypes.node, title: PropTypes.string, sub: PropTypes.string, children: PropTypes.node };

function Row({ title, sub, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "12px 0", borderTop: `1px solid ${S.g100}` }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: S.g700 }}>{title}</div>
        {sub && <div style={{ fontSize: 12, color: S.g400, marginTop: 2 }}>{sub}</div>}
      </div>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}
Row.propTypes = { title: PropTypes.string, sub: PropTypes.string, children: PropTypes.node };

export default function Settings({ lang, user, dark, onToggleDark, onToggleLang }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const toast = useToast();
  const isManager = user?.role === "hr_manager";

  const [settings, setSettings] = useState(null);
  const [testing, setTesting] = useState(false);
  const [testTo, setTestTo] = useState(user?.email || "");

  const [rem, setRem] = useState(null);
  const [remTo, setRemTo] = useState("");
  const [remSaving, setRemSaving] = useState(false);
  const [remSending, setRemSending] = useState(false);

  useEffect(() => {
    if (!isManager) return;
    api.getSettings().then(setSettings).catch(() => setSettings(null));
    api.getReminders().then((r) => { setRem(r); setRemTo(r.recipients || ""); }).catch(() => setRem(null));
  }, [isManager]);

  async function saveRem(enabled) {
    setRemSaving(true);
    try {
      const next = await api.setReminders({ recipients: remTo, enabled: enabled ?? rem?.enabled ?? true });
      setRem(next);
      setRemTo(next.recipients || "");
      toast("ok", t("savedOk"));
    } catch (e) {
      toast("err", e.message || t("errGeneric"));
    } finally {
      setRemSaving(false);
    }
  }

  const REM_MSG = { ok: "docRemSent", nothing_due: "docRemNothingDue", no_recipients: "docRemNoRecipients", email_not_configured: "smtpMissing" };
  async function sendRemNow() {
    setRemSending(true);
    try {
      const res = await api.runReminders();
      if (res.sent) toast("ok", `${t("docRemSent")} (${res.count})`);
      else toast(res.reason === "nothing_due" ? "ok" : "err", t(REM_MSG[res.reason] || "errGeneric"));
      api.getReminders().then((r) => { setRem(r); }).catch(() => {});
    } catch (e) {
      toast("err", e.message || t("errGeneric"));
    } finally {
      setRemSending(false);
    }
  }

  async function sendTest() {
    setTesting(true);
    try {
      const res = await api.sendTestEmail(testTo.trim());
      if (res.sent) toast("ok", `${t("testSent")} → ${res.to}`);
      else toast("err", t("smtpMissing"));
    } catch (e) {
      toast("err", e.message || t("errGeneric"));
    } finally {
      setTesting(false);
    }
  }

  const TRANSPORT_LABEL = { brevo: "Brevo (HTTP API)", resend: "Resend (HTTP API)", smtp: "SMTP", none: t("notConfigured") };

  const initial = (user?.name || "?").charAt(0).toUpperCase();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22, maxWidth: 720 }}>
      <div>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("set")}</h2>
        <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{t("setSub")}</p>
      </div>

      {/* Profile */}
      <Section icon={IC.user} title={t("profile")} sub={t("profileSub")}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 52, height: 52, borderRadius: "50%", flexShrink: 0, background: `linear-gradient(135deg,${S.pri},${S.acc})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 20, fontWeight: 700 }}>{initial}</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: S.g800 }}>{user?.name}</div>
            <div style={{ fontSize: 12.5, color: S.g400 }}>{user?.email}</div>
            <div style={{ display: "inline-block", marginTop: 5, fontSize: 11, fontWeight: 600, color: S.pri, background: S.priL, padding: "2px 9px", borderRadius: 999 }}>{t(ROLE_LABEL_KEY[user?.role] || user?.role)}</div>
          </div>
        </div>
      </Section>

      {/* Appearance */}
      <Section icon={IC.moon} title={t("appearance")} sub={t("appearanceSub")}>
        <Row title={t("dark")} sub={t("darkSub")}>
          <Switch on={!!dark} onChange={onToggleDark} label={t("dark")} />
        </Row>
        <Row title={t("defaultArabic")} sub={t("defaultArabicSub")}>
          <Switch on={ar} onChange={onToggleLang} label={t("defaultArabic")} />
        </Row>
      </Section>

      {/* Email & notifications — managers only */}
      {isManager && (
        <Section icon={IC.mail} title={t("emailNotif")} sub={t("emailNotifSub")}>
          <Row title={t("smtpStatus")} sub={settings ? TRANSPORT_LABEL[settings.transport] : ""}>
            <span style={{ fontSize: 12, fontWeight: 700, padding: "4px 11px", borderRadius: 999, background: settings?.email_configured ? S.okL : S.warnL, color: settings?.email_configured ? S.ok : S.warn }}>
              {settings == null ? "…" : settings.email_configured ? t("configured") : t("notConfigured")}
            </span>
          </Row>
          {settings?.email_from && (
            <Row title={t("smtpFrom")}>
              <span style={{ fontSize: 12.5, color: S.g500 }}>{settings.email_from}</span>
            </Row>
          )}
          <Row title={t("violationEmails")} sub={t("violationEmailsSub")}>
            <span style={{ fontSize: 12.5, color: S.g500 }}>{t("autoOn")}</span>
          </Row>
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: S.g500 }}>{t("sendTestTo")}</label>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input style={{ ...inp, maxWidth: 280 }} type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder={user?.email || ""} />
              <BtnPri onClick={sendTest} disabled={testing || !settings?.email_configured || !testTo.trim()}>
                {IC.mail} <span>{testing ? "…" : t("sendTest")}</span>
              </BtnPri>
            </div>
            {settings != null && !settings.email_configured && (
              <p style={{ fontSize: 12, color: S.g400 }}>{t("smtpEnvHint")}</p>
            )}
          </div>
        </Section>
      )}

      {/* Document expiry reminders — managers only */}
      {isManager && (
        <Section icon={IC.bell} title={t("docRemTitle")} sub={t("docRemSub")}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: S.g500 }}>{t("docRemRecipients")}</label>
            <textarea
              style={{ ...inp, resize: "vertical", minHeight: 52, direction: "ltr" }}
              value={remTo}
              onChange={(e) => setRemTo(e.target.value)}
              placeholder="name@example.com, name2@example.com"
            />
            <div>
              <BtnPri onClick={() => saveRem()} disabled={remSaving}>{IC.check} <span>{remSaving ? "…" : t("save")}</span></BtnPri>
            </div>
          </div>
          <Row title={t("docRemEnabled")} sub={t("docRemEnabledSub")}>
            <Switch on={!!rem?.enabled} onChange={() => saveRem(!rem?.enabled)} label={t("docRemEnabled")} />
          </Row>
          <Row title={t("docRemSendNow")} sub={rem?.last_sent ? `${t("docRemLastSent")}: ${rem.last_sent}` : t("docRemNever")}>
            <BtnSec onClick={sendRemNow} disabled={remSending || !remTo.trim()}>{IC.mail} <span>{remSending ? "…" : t("docRemSendNow")}</span></BtnSec>
          </Row>
          {rem != null && !rem.email_configured && (
            <p style={{ fontSize: 12, color: S.g400, marginTop: 6 }}>{t("smtpEnvHint")}</p>
          )}
        </Section>
      )}
    </div>
  );
}

Settings.propTypes = {
  lang: PropTypes.string.isRequired,
  user: PropTypes.shape({ name: PropTypes.string, email: PropTypes.string, role: PropTypes.string }),
  dark: PropTypes.bool,
  onToggleDark: PropTypes.func.isRequired,
  onToggleLang: PropTypes.func.isRequired,
};
