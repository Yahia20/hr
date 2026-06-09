import { useEffect, useRef } from "react";
import { S } from "./tokens";
import { BtnSec } from "./components";

export function Modal({ open, onClose, title, children, labelledBy = "hr-modal-title" }) {
  const boxRef = useRef(null);
  const restoreRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement;
    // focus the first focusable control inside the dialog
    const first = boxRef.current?.querySelector("button, [href], input, select, textarea");
    (first || boxRef.current)?.focus();

    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      // keep Tab cycling inside the dialog
      const els = boxRef.current?.querySelectorAll("button, [href], input, select, textarea");
      if (!els || els.length === 0) return;
      const list = Array.from(els).filter((el) => !el.disabled);
      const firstEl = list[0];
      const lastEl = list[list.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      restoreRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{ position: "fixed", inset: 0, background: "rgba(8,14,22,.5)", zIndex: 900, display: "flex", alignItems: "center", justifyContent: "center", padding: 20, animation: "hr-fade-in .15s ease" }}
    >
      <div
        ref={boxRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        style={{ width: "100%", maxWidth: 420, background: S.w, borderRadius: S.r3, border: `1px solid ${S.g200}`, boxShadow: S.sh2, padding: 24, animation: "hr-pop-in .18s cubic-bezier(.4,0,.2,1)", outline: "none" }}
      >
        <h3 id={labelledBy} style={{ margin: "0 0 10px", fontSize: 15, fontWeight: 700, color: S.g800 }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}

/** Confirmation dialog for destructive actions. */
export function ConfirmModal({ open, onClose, onConfirm, title, body, confirmLabel, cancelLabel, busy }) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <p style={{ margin: "0 0 18px", fontSize: 13, color: S.g500, lineHeight: 1.6 }}>{body}</p>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
        <BtnSec onClick={onClose}><span>{cancelLabel}</span></BtnSec>
        <button
          onClick={onConfirm}
          disabled={busy}
          style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "9px 18px", borderRadius: S.r2, border: "none", cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1, fontSize: 13, fontWeight: 600, fontFamily: "inherit", background: S.err, color: "#fff", boxShadow: "0 2px 8px rgba(220,38,38,.25)" }}
        >
          {busy ? "…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
