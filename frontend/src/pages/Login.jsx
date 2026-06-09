import { useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { BtnPri, FG, inp } from "../components";

export default function Login({ lang, onSuccess }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;

  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api.login(user, pass);
      onSuccess();
    } catch (ex) {
      setErr(ar ? "\u0628\u064A\u0627\u0646\u0627\u062A \u063A\u064A\u0631 \u0635\u062D\u064A\u062D\u0629" : "Invalid credentials");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: S.g50, padding: 20, direction: ar ? "rtl" : "ltr", fontFamily: ar ? "'Noto Sans Arabic','Segoe UI',sans-serif" : "'DM Sans','Segoe UI',sans-serif" }}>
      <form onSubmit={submit} style={{ width: "100%", maxWidth: 380, background: S.w, borderRadius: S.r3, border: `1px solid ${S.g200}`, padding: 32, boxShadow: S.sh1 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: `linear-gradient(135deg,${S.pri},${S.priD})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 18, fontWeight: 800, boxShadow: "0 4px 14px rgba(47,184,158,.35)" }}>TG</div>
          <h1 style={{ fontSize: 18, fontWeight: 800, color: S.g800, margin: 0 }}>{t("hrSys")}</h1>
          <p style={{ fontSize: 12, color: S.g400, margin: 0 }}>{ar ? "\u0633\u062C\u0644 \u0627\u0644\u062F\u062E\u0648\u0644 \u0644\u0644\u0645\u062A\u0627\u0628\u0639\u0629" : "Sign in to continue"}</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 18 }}>
          <FG label={ar ? "\u0627\u0633\u0645 \u0627\u0644\u0645\u0633\u062A\u062E\u062F\u0645" : "Username"}>
            <input style={inp} value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" autoFocus />
          </FG>
          <FG label={ar ? "\u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631" : "Password"}>
            <input style={inp} type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="current-password" />
          </FG>
        </div>
        {err && <div style={{ color: S.err, fontSize: 13, marginBottom: 14, textAlign: "center" }}>{err}</div>}
        <BtnPri wide disabled={busy}><span>{busy ? "\u2026" : (ar ? "\u062F\u062E\u0648\u0644" : "Sign in")}</span></BtnPri>
      </form>
    </div>
  );
}
