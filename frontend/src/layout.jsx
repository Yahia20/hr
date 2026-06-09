import { memo } from "react";
import PropTypes from "prop-types";
import { S } from "./tokens";
import { IC } from "./icons";
import logo from "./assets/logo.png";

const ROLE_LABEL_KEY = { hr_manager: "roleManager", hr_officer: "roleOfficer", dept_head: "roleDeptHead", employee: "roleEmployee" };

export const Sidebar = memo(function Sidebar({ ar, t, mobile, collapsed, setCollapsed, navs, page, onNav }) {
  const mini = collapsed && !mobile;
  return (
    <aside aria-label={t("mainMenu")} style={{ position: "fixed", top: 0, bottom: 0, [ar ? "right" : "left"]: 0, width: mobile ? 256 : collapsed ? 68 : 256, background: S.w, [ar ? "borderLeft" : "borderRight"]: `1px solid ${S.g100}`, display: "flex", flexDirection: "column", transition: "width 0.22s cubic-bezier(.4,0,.2,1)", zIndex: 300, boxShadow: mobile ? S.sh2 : "2px 0 12px rgba(0,0,0,0.04)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: mini ? 0 : "0 20px", justifyContent: mini ? "center" : "flex-start", height: 60, borderBottom: `1px solid ${S.g100}`, flexShrink: 0 }}>
        <img src={logo} alt="Travel Gate" style={{ width: 38, height: 28, objectFit: "contain", flexShrink: 0 }} />
        {!mini && (
          <div style={{ overflow: "hidden", minWidth: 0 }}>
            <b style={{ display: "block", fontSize: 14, fontWeight: 700, color: S.g800, whiteSpace: "nowrap" }}>Travel Gate</b>
            <small style={{ display: "block", fontSize: 10.5, color: S.g400, whiteSpace: "nowrap" }}>{t("hrSys")}</small>
          </div>
        )}
      </div>
      {!mini && <div style={{ fontSize: 10, fontWeight: 700, color: S.g400, textTransform: "uppercase", letterSpacing: ".08em", padding: "10px 12px 4px" }}>{t("mainMenu")}</div>}
      <nav style={{ flex: 1, padding: "10px 8px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
        {navs.map((n) => {
          const act = page === n.id;
          return (
            <button key={n.id} onClick={() => onNav(n.id)} aria-current={act ? "page" : undefined} title={mini ? t(n.id) : undefined} style={{ display: "flex", alignItems: "center", gap: 10, padding: mini ? 11 : "10px 12px", justifyContent: mini ? "center" : "flex-start", borderRadius: S.r2, border: "none", cursor: "pointer", background: act ? S.priL : "transparent", color: act ? S.priD : S.g400, fontWeight: act ? 600 : 500, fontSize: 13, transition: S.tr, width: "100%", textAlign: ar ? "right" : "left", fontFamily: "inherit", position: "relative" }}>
              {act && <span style={{ position: "absolute", [ar ? "right" : "left"]: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 20, borderRadius: ar ? "2px 0 0 2px" : "0 2px 2px 0", background: S.pri }} />}
              <span style={{ color: act ? S.pri : "inherit", display: "flex" }}>{n.icon}</span>
              {!mini && <span style={{ whiteSpace: "nowrap" }}>{t(n.id)}</span>}
            </button>
          );
        })}
      </nav>
      {!mobile && (
        <div style={{ padding: 8, borderTop: `1px solid ${S.g100}`, flexShrink: 0 }}>
          <button onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Expand menu" : "Collapse menu"} style={{ width: "100%", padding: 9, borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: S.g400, fontFamily: "inherit" }}>
            {collapsed ? (ar ? IC.chevL : IC.chevR) : (ar ? IC.chevR : IC.chevL)}
          </button>
        </div>
      )}
    </aside>
  );
});

Sidebar.propTypes = {
  ar: PropTypes.bool.isRequired,
  t: PropTypes.func.isRequired,
  mobile: PropTypes.bool.isRequired,
  collapsed: PropTypes.bool.isRequired,
  setCollapsed: PropTypes.func.isRequired,
  navs: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, icon: PropTypes.node })).isRequired,
  page: PropTypes.string.isRequired,
  onNav: PropTypes.func.isRequired,
};

export const Topbar = memo(function Topbar({ ar, t, mobile, page, user, dark, onToggleDark, onToggleLang, onLogout, onOpenDrawer }) {
  const iconBtn = { width: 36, height: 36, borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: S.g400, fontFamily: "inherit", flexShrink: 0 };
  return (
    <header style={{ height: 60, background: S.w, borderBottom: `1px solid ${S.g100}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: mobile ? "0 14px" : "0 28px", position: "sticky", top: 0, zIndex: 100, boxShadow: S.sh0, flexShrink: 0, gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        {mobile && (
          <button onClick={onOpenDrawer} aria-label={t("menu")} style={iconBtn}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
          </button>
        )}
        <h1 style={{ fontSize: 16, fontWeight: 700, color: S.g800, margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t(page)}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={onToggleLang} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: S.rF, border: `1px solid ${S.g200}`, background: S.w, cursor: "pointer", fontSize: 12, color: S.g500, fontWeight: 500, fontFamily: "inherit", flexShrink: 0 }}>{IC.globe} {!mobile && <span>{t("lang")}</span>}</button>
        <button onClick={onToggleDark} aria-label={dark ? t("light") : t("dark")} title={dark ? t("light") : t("dark")} style={iconBtn}>
          {dark ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
          )}
        </button>
        {!mobile && (
          <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "4px 8px", borderRadius: S.rF }}>
            <div style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0, background: `linear-gradient(135deg,${S.pri},${S.acc})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 700 }}>{(user.name || "?").charAt(0).toUpperCase()}</div>
            <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.25 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: S.g700 }}>{user.name}</span>
              <span style={{ fontSize: 10.5, color: S.g400 }}>{t(ROLE_LABEL_KEY[user.role] || user.role)}</span>
            </div>
          </div>
        )}
        <button onClick={onLogout} title={t("logout")} aria-label={t("logout")} style={{ ...iconBtn, fontSize: 14 }}>{"⏻"}</button>
      </div>
    </header>
  );
});

Topbar.propTypes = {
  ar: PropTypes.bool.isRequired,
  t: PropTypes.func.isRequired,
  mobile: PropTypes.bool.isRequired,
  page: PropTypes.string.isRequired,
  user: PropTypes.shape({ name: PropTypes.string, role: PropTypes.string }).isRequired,
  dark: PropTypes.bool.isRequired,
  onToggleDark: PropTypes.func.isRequired,
  onToggleLang: PropTypes.func.isRequired,
  onLogout: PropTypes.func.isRequired,
  onOpenDrawer: PropTypes.func.isRequired,
};
