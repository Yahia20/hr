import { memo } from "react";
import PropTypes from "prop-types";
import { S, pbStyle } from "./tokens";
import { L } from "./i18n";

// memo: rendered once per table row; props are primitives.
export const PenBadge = memo(function PenBadge({ level, size = "sm", lang }) {
  const s = pbStyle[level] || pbStyle.Yellow;
  const lk = { Yellow: "yellow", Orange: "orange", Red: "red", Black: "black", Investigation: "invest" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, borderRadius: 999, fontWeight: 600, whiteSpace: "nowrap", padding: size === "sm" ? "3px 9px" : "5px 13px", fontSize: size === "sm" ? 11 : 12.5, background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: s.dot }} />
      {L[lang][lk[level]] || level}
    </span>
  );
});

PenBadge.propTypes = {
  level: PropTypes.oneOf(["Yellow", "Orange", "Red", "Black", "Investigation"]).isRequired,
  size: PropTypes.oneOf(["sm", "lg"]),
  lang: PropTypes.string.isRequired,
};

export const Card = ({ children, style: cs, flush }) => (
  <div style={{ background: S.w, borderRadius: S.r3, border: `1px solid ${S.g200}`, padding: flush ? 0 : 24, boxShadow: S.sh1, overflow: flush ? "hidden" : "visible", ...cs }}>{children}</div>
);

export const Empty = ({ icon, text, sub, action }) => (
  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "56px 0", color: S.g400, gap: 10 }}>
    {icon || (
      <div aria-hidden="true" style={{ width: 52, height: 52, borderRadius: "50%", background: S.g100, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22 }}>📋</div>
    )}
    <p style={{ fontSize: 14, fontWeight: 500, margin: 0 }}>{text}</p>
    {sub && <small style={{ fontSize: 12.5, color: S.g400 }}>{sub}</small>}
    {action && <div style={{ marginTop: 6 }}>{action}</div>}
  </div>
);

export const Skeleton = ({ w = "100%", h = 14, style: ss }) => (
  <span aria-hidden="true" className="hr-skeleton" style={{ display: "block", width: w, height: h, ...ss }} />
);

/** Shimmer placeholder rows for a table while data loads. */
export const SkeletonRows = ({ rows = 5, cols = 5 }) => (
  <>
    {Array.from({ length: rows }).map((_, r) => (
      <tr key={r} style={{ borderBottom: `1px solid ${S.g100}` }}>
        {Array.from({ length: cols }).map((__, c) => (
          <td key={c} style={{ padding: "14px 16px" }}><Skeleton w={c === 0 ? "70%" : "55%"} /></td>
        ))}
      </tr>
    ))}
  </>
);

export const KpiSkeleton = () => (
  <Card>
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Skeleton w={42} h={42} style={{ borderRadius: S.r2 }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <Skeleton w="45%" h={30} />
        <Skeleton w="65%" h={11} />
      </div>
    </div>
  </Card>
);

/** Client-side pagination footer: « prev | x–y of n | next » */
export const Pager = ({ page, pages, from, to, total, setPage, ar, label }) => {
  if (total === 0) return null;
  const btn = (disabled) => ({ width: 30, height: 30, borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: disabled ? S.g300 : S.g500, cursor: disabled ? "default" : "pointer", fontSize: 13, fontFamily: "inherit", display: "flex", alignItems: "center", justifyContent: "center" });
  return (
    <nav aria-label={label || "Pagination"} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderTop: `1px solid ${S.g100}` }}>
      <span style={{ fontSize: 12, color: S.g400 }}>{from}–{to} / {total}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <button onClick={() => setPage(page - 1)} disabled={page <= 1} aria-label="Previous page" style={btn(page <= 1)}>{ar ? "›" : "‹"}</button>
        <span style={{ fontSize: 12, color: S.g500, minWidth: 44, textAlign: "center" }}>{page} / {pages}</span>
        <button onClick={() => setPage(page + 1)} disabled={page >= pages} aria-label="Next page" style={btn(page >= pages)}>{ar ? "‹" : "›"}</button>
      </div>
    </nav>
  );
};

export const KpiCard = memo(function KpiCard({ icon, iconBg, value, label, sub }) {
  return (
  <Card>
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ width: 42, height: 42, borderRadius: S.r2, display: "flex", alignItems: "center", justifyContent: "center", background: iconBg }}>{icon}</div>
      <div>
        <div style={{ fontSize: 32, fontWeight: 800, color: S.g800, lineHeight: 1, letterSpacing: -1 }}>{value}</div>
        <div style={{ fontSize: 12, color: S.g400, marginTop: 4, fontWeight: 500 }}>{label}</div>
      </div>
      {sub && <div style={{ fontSize: 11.5, color: S.g400, borderTop: `1px solid ${S.g100}`, paddingTop: 12 }}>{sub}</div>}
    </div>
  </Card>
  );
});

KpiCard.propTypes = {
  icon: PropTypes.node,
  iconBg: PropTypes.string,
  value: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  label: PropTypes.string,
  sub: PropTypes.node,
};

export const BtnPri = ({ children, onClick, wide, disabled }) => (
  <button onClick={onClick} disabled={disabled} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: wide ? 12 : "9px 18px", borderRadius: S.r2, border: "none", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1, fontSize: wide ? 14 : 13, fontWeight: 600, transition: S.tr, fontFamily: "inherit", whiteSpace: "nowrap", background: S.pri, color: "#fff", boxShadow: "0 2px 8px rgba(47,184,158,.25)", width: wide ? "100%" : "auto", justifyContent: "center" }}>{children}</button>
);

export const BtnSec = ({ children, onClick, disabled }) => (
  <button onClick={onClick} disabled={disabled} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "9px 18px", borderRadius: S.r2, border: `1px solid ${S.g200}`, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1, fontSize: 13, fontWeight: 600, transition: S.tr, fontFamily: "inherit", whiteSpace: "nowrap", background: S.w, color: S.g600 }}>{children}</button>
);

export const BtnGhost = ({ children, onClick }) => (
  <button onClick={onClick} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "5px 12px", borderRadius: S.r2, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, transition: S.tr, fontFamily: "inherit", background: "transparent", color: S.g400 }}>{children}</button>
);

export const Th = ({ children, ar }) => (
  <th scope="col" style={{ padding: "11px 16px", fontWeight: 600, color: S.g400, fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".06em", borderBottom: `2px solid ${S.g100}`, whiteSpace: "nowrap", textAlign: ar ? "right" : "left", background: S.g50 }}>{children}</th>
);

export const FG = ({ label, children }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
    <label style={{ fontSize: 12, fontWeight: 600, color: S.g500 }}>{label}</label>
    {children}
  </div>
);

export const inp = { padding: "10px 14px", borderRadius: S.r2, border: `1.5px solid ${S.g200}`, fontSize: 13.5, color: S.g700, fontFamily: "inherit", outline: "none", background: S.w, width: "100%" };

export const chipBtn = (color) => ({
  display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 600,
  padding: "3px 9px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w,
  color, cursor: "pointer", fontFamily: "inherit",
});

Card.propTypes = { children: PropTypes.node, style: PropTypes.object, flush: PropTypes.bool };
Empty.propTypes = { icon: PropTypes.node, text: PropTypes.string, sub: PropTypes.string, action: PropTypes.node };
Skeleton.propTypes = { w: PropTypes.oneOfType([PropTypes.number, PropTypes.string]), h: PropTypes.oneOfType([PropTypes.number, PropTypes.string]), style: PropTypes.object };
SkeletonRows.propTypes = { rows: PropTypes.number, cols: PropTypes.number };
Pager.propTypes = {
  page: PropTypes.number.isRequired,
  pages: PropTypes.number.isRequired,
  from: PropTypes.number.isRequired,
  to: PropTypes.number.isRequired,
  total: PropTypes.number.isRequired,
  setPage: PropTypes.func.isRequired,
  ar: PropTypes.bool,
  label: PropTypes.string,
};
BtnPri.propTypes = { children: PropTypes.node, onClick: PropTypes.func, wide: PropTypes.bool, disabled: PropTypes.bool };
BtnSec.propTypes = { children: PropTypes.node, onClick: PropTypes.func, disabled: PropTypes.bool };
BtnGhost.propTypes = { children: PropTypes.node, onClick: PropTypes.func };
Th.propTypes = { children: PropTypes.node, ar: PropTypes.bool };
FG.propTypes = { label: PropTypes.string, children: PropTypes.node };
