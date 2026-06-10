import { useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { BtnPri, FG, inp } from "../components";
import { AuthAlert as Alert, AuthShell as Shell, PasswordInput } from "../authui";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
