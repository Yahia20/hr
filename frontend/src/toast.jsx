import { createContext, useCallback, useContext, useRef, useState } from "react";
import PropTypes from "prop-types";
import { S } from "./tokens";

const ToastCtx = createContext(null);

const TYPE_STYLE = {
  ok:   { bg: S.okL, color: S.ok, icon: "✓" },
  err:  { bg: S.errL, color: S.err, icon: "✕" },
  warn: { bg: S.warnL, color: S.warn, icon: "!" },
  info: { bg: S.infoL, color: S.info, icon: "i" },
};

export function ToastProvider({ children, ar }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((type, text, ttl = 3800) => {
    const id = ++idRef.current;
    setToasts((ts) => [...ts.slice(-3), { id, type, text }]);
    if (ttl) setTimeout(() => dismiss(id), ttl);
  }, [dismiss]);

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        style={{ position: "fixed", bottom: 20, [ar ? "left" : "right"]: 20, zIndex: 1000, display: "flex", flexDirection: "column", gap: 8, maxWidth: 360 }}
      >
        {toasts.map((t) => {
          const st = TYPE_STYLE[t.type] || TYPE_STYLE.info;
          return (
            <div
              key={t.id}
              role="status"
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", borderRadius: S.r2, background: S.w, border: `1px solid ${S.g200}`, boxShadow: S.sh2, animation: "hr-toast-in .22s cubic-bezier(.4,0,.2,1)", fontSize: 13, color: S.g700 }}
            >
              <span aria-hidden="true" style={{ width: 22, height: 22, borderRadius: "50%", flexShrink: 0, background: st.bg, color: st.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800 }}>{st.icon}</span>
              <span style={{ flex: 1 }}>{t.text}</span>
              <button onClick={() => dismiss(t.id)} aria-label="Dismiss" style={{ border: "none", background: "transparent", color: S.g400, cursor: "pointer", fontSize: 14, padding: 2, lineHeight: 1, fontFamily: "inherit" }}>×</button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

/** toast(type, text) — type: "ok" | "err" | "warn" | "info" */
export function useToast() {
  return useContext(ToastCtx) || (() => {});
}

ToastProvider.propTypes = { children: PropTypes.node, ar: PropTypes.bool };
