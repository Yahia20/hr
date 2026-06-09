import { useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { BtnPri, FG, inp } from "../components";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const eyeOpen = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
  </svg>
);
const eyeOff = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

function PasswordInput({ value, onChange, label, t, autoComplete }) {
  const [show, setShow] = useState(false);
  return (
    <FG label={label}>
      <div style={{ position: "relative" }}>
        <input
          style={{ ...inp, paddingInlineEnd: 42 }}
          type={show ? "text" : "password"}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          required
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          aria-label={show ? t("hidePwd") : t("showPwd")}
          title={show ? t("hidePwd") : t("showPwd")}
          style={{ position: "absolute", insetInlineEnd: 8, top: "50%", transform: "translateY(-50%)", border: "none", background: "transparent", cursor: "pointer", color: S.g400, padding: 6, display: "flex" }}
        >
          {show ? eyeOff : eyeOpen}
        </button>
      </div>
    </FG>
  );
}

function Shell({ ar, t, title, sub, children }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: S.g50, padding: 20, direction: ar ? "rtl" : "ltr", fontFamily: ar ? "'Noto Sans Arabic','Segoe UI',sans-serif" : "'DM Sans','Segoe UI',sans-serif" }}>
      <div style={{ width: "100%", maxWidth: 380, background: S.w, borderRadius: S.r3, border: `1px solid ${S.g200}`, padding: 32, boxShadow: S.sh1 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: `linear-gradient(135deg,${S.pri},${S.priD})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 18, fontWeight: 800, boxShadow: "0 4px 14px rgba(47,184,158,.35)" }}>TG</div>
          <h1 style={{ fontSize: 18, fontWeight: 800, color: S.g800, margin: 0 }}>{title || t("hrSys")}</h1>
          <p style={{ fontSize: 12, color: S.g400, margin: 0, textAlign: "center" }}>{sub}</p>
        </div>
        {children}
      </div>
    </div>
  );
}

const Alert = ({ type, children }) => (
  <div role="alert" style={{ padding: "10px 14px", borderRadius: S.r2, marginBottom: 14, fontSize: 13, fontWeight: 600, textAlign: "center", background: type === "ok" ? S.okL : S.errL, color: type === "ok" ? S.ok : S.err }}>
    {children}
  </div>
);

export default function Login({ lang, onSuccess, resetToken, onResetDone }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;

  // mode: "login" | "forgot" | "reset" (reset is forced by a token in the URL)
  const [mode, setMode] = useState(resetToken ? "reset" : "login");
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [remember, setRemember] = useState(false);
  const [err, setErr] = useState(null);
  const [okMsg, setOkMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  function fail(ex) {
    if (ex.status === 401) setErr(t("errInvalidLogin"));
    else if (ex.status === 429) setErr(t("errLocked"));
    else if (ex.status === 400) setErr(mode === "reset" ? t("errResetInvalid") : ex.message);
    else if (ex.status === 422) setErr(t("emailInvalid"));
    else setErr(t("errNetwork"));
  }

  async function submitLogin(e) {
    e.preventDefault();
    setErr(null); setOkMsg(null);
    if (!EMAIL_RE.test(email)) { setErr(t("emailInvalid")); return; }
    setBusy(true);
    try {
      const { user } = await api.login(email.trim(), pass, remember);
      onSuccess(user);
    } catch (ex) {
      fail(ex);
    } finally {
      setBusy(false);
    }
  }

  async function submitForgot(e) {
    e.preventDefault();
    setErr(null); setOkMsg(null);
    if (!EMAIL_RE.test(email)) { setErr(t("emailInvalid")); return; }
    setBusy(true);
    try {
      await api.forgotPassword(email.trim());
      setOkMsg(t("resetSent"));
    } catch (ex) {
      fail(ex);
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(e) {
    e.preventDefault();
    setErr(null); setOkMsg(null);
    if (pass.length < 8) { setErr(t("pwdTooShort")); return; }
    if (pass !== pass2) { setErr(t("pwdMismatch")); return; }
    setBusy(true);
    try {
      await api.resetPassword(resetToken, pass);
      setOkMsg(t("resetDone"));
      setTimeout(() => onResetDone(), 1500);
    } catch (ex) {
      fail(ex);
    } finally {
      setBusy(false);
    }
  }

  const linkStyle = { border: "none", background: "transparent", color: S.pri, fontSize: 12.5, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", padding: 0 };

  if (mode === "reset") {
    return (
      <Shell ar={ar} t={t} title={t("resetPwd")} sub={t("hrSys")}>
        <form onSubmit={submitReset}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
            <PasswordInput value={pass} onChange={(e) => setPass(e.target.value)} label={t("newPwd")} t={t} autoComplete="new-password" />
            <PasswordInput value={pass2} onChange={(e) => setPass2(e.target.value)} label={t("confirmPwd")} t={t} autoComplete="new-password" />
          </div>
          {err && <Alert type="err">{err}</Alert>}
          {okMsg && <Alert type="ok">{okMsg}</Alert>}
          <BtnPri wide disabled={busy}><span>{busy ? t("loading") : t("resetPwd")}</span></BtnPri>
          <div style={{ textAlign: "center", marginTop: 14 }}>
            <button type="button" style={linkStyle} onClick={onResetDone}>{t("backToLogin")}</button>
          </div>
        </form>
      </Shell>
    );
  }

  if (mode === "forgot") {
    return (
      <Shell ar={ar} t={t} title={t("resetPwd")} sub={t("hrSys")}>
        <form onSubmit={submitForgot}>
          <div style={{ marginBottom: 18 }}>
            <FG label={t("email")}>
              <input style={inp} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus required />
            </FG>
          </div>
          {err && <Alert type="err">{err}</Alert>}
          {okMsg && <Alert type="ok">{okMsg}</Alert>}
          <BtnPri wide disabled={busy}><span>{busy ? t("loading") : t("sendResetLink")}</span></BtnPri>
          <div style={{ textAlign: "center", marginTop: 14 }}>
            <button type="button" style={linkStyle} onClick={() => { setMode("login"); setErr(null); setOkMsg(null); }}>{t("backToLogin")}</button>
          </div>
        </form>
      </Shell>
    );
  }

  return (
    <Shell ar={ar} t={t} sub={t("signInSub")}>
      <form onSubmit={submitLogin}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 14 }}>
          <FG label={t("email")}>
            <input style={inp} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus required />
          </FG>
          <PasswordInput value={pass} onChange={(e) => setPass(e.target.value)} label={t("password")} t={t} autoComplete="current-password" />
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12.5, color: S.g500, cursor: "pointer" }}>
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} style={{ accentColor: S.pri, width: 14, height: 14, cursor: "pointer" }} />
            {t("rememberMe")}
          </label>
          <button type="button" style={linkStyle} onClick={() => { setMode("forgot"); setErr(null); setOkMsg(null); }}>{t("forgotPwd")}</button>
        </div>
        {err && <Alert type="err">{err}</Alert>}
        <BtnPri wide disabled={busy}><span>{busy ? t("loading") : t("signIn")}</span></BtnPri>
      </form>
    </Shell>
  );
}
