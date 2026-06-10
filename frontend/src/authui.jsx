import { useState } from "react";
import PropTypes from "prop-types";
import { S } from "./tokens";
import { FG, inp } from "./components";
import logo from "./assets/logo.png";

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

/** Password field with a show/hide toggle. */
export function PasswordInput({ value, onChange, label, t, autoComplete }) {
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

PasswordInput.propTypes = {
  value: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  t: PropTypes.func.isRequired,
  autoComplete: PropTypes.string,
};

/** Centered branded card used by all pre-auth screens. */
export function AuthShell({ ar, t, title, sub, children }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: S.g50, padding: 20, direction: ar ? "rtl" : "ltr", fontFamily: ar ? S.fontAr : S.fontEn }}>
      <div style={{ width: "100%", maxWidth: 380, background: S.w, borderRadius: S.r3, border: `1px solid ${S.g200}`, padding: 32, boxShadow: S.sh1 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <img src={logo} alt="Travel Gate" style={{ width: 72, height: 54, objectFit: "contain" }} />
          <h1 style={{ fontSize: 18, fontWeight: 800, color: S.g800, margin: 0 }}>{title || t("hrSys")}</h1>
          <p style={{ fontSize: 12, color: S.g400, margin: 0, textAlign: "center" }}>{sub}</p>
        </div>
        {children}
      </div>
    </div>
  );
}

AuthShell.propTypes = {
  ar: PropTypes.bool.isRequired,
  t: PropTypes.func.isRequired,
  title: PropTypes.string,
  sub: PropTypes.string,
  children: PropTypes.node,
};

export const AuthAlert = ({ type, children }) => (
  <div role="alert" style={{ padding: "10px 14px", borderRadius: S.r2, marginBottom: 14, fontSize: 13, fontWeight: 600, textAlign: "center", background: type === "ok" ? S.okL : S.errL, color: type === "ok" ? S.ok : S.err }}>
    {children}
  </div>
);

AuthAlert.propTypes = {
  type: PropTypes.oneOf(["ok", "err"]).isRequired,
  children: PropTypes.node,
};
