import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { S } from "./tokens";
import { L } from "./i18n";
import { IC } from "./icons";
import { Card, Empty } from "./components";
import { Modal } from "./modal";
import { ToastProvider } from "./toast";
import { useHotkeys, useLocalStorage, useMediaQuery } from "./hooks";
import Dashboard from "./pages/Dashboard";
import LogViolation from "./pages/LogViolation";
import Employees from "./pages/Employees";
import Reports from "./pages/Reports";
import Users from "./pages/Users";
import Login from "./pages/Login";

const PLACEHOLDERS = {
  set: { icon: IC.setBig, title: "comingSoon", sub: "comingSoonSub" },
};

// Pages each role may open; the first entry is the role's landing page.
const ROLE_PAGES = {
  hr_manager: ["dash", "log", "emp", "rep", "users", "set"],
  hr_officer: ["dash", "log", "emp", "rep"],
  dept_head: ["rep", "emp"],
  employee: ["rep"],
};

// Single-key shortcuts (suppressed while typing in a field).
const HOTKEY_PAGES = { d: "dash", n: "log", e: "emp", r: "rep" };

function readResetToken() {
  const token = new URLSearchParams(window.location.search).get("reset_token");
  return token || null;
}

export default function HRSystem() {
  const [lang, setLang] = useLocalStorage("hr_lang", "en");
  const [dark, setDark] = useLocalStorage("hr_theme_dark", false);
  const [page, setPage] = useState("dash");
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [resetToken, setResetToken] = useState(readResetToken);
  const mobile = useMediaQuery("(max-width: 820px)");

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);

  // Restore the session from the httpOnly cookie on first load.
  useEffect(() => {
    api.me()
      .then(({ user }) => onLogin(user))
      .catch(() => {})
      .finally(() => setBooting(false));
    const h = () => setUser(null);
    window.addEventListener("hr-logout", h);
    return () => window.removeEventListener("hr-logout", h);
  }, []);

  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const sw = collapsed ? 68 : 256;
  const allowed = user ? ROLE_PAGES[user.role] || ["rep"] : [];

  const hotkeys = useMemo(() => {
    const map = {
      "?": () => setHelpOpen((v) => !v),
      "/": () => window.dispatchEvent(new Event("hr-focus-search")),
      Escape: () => { setHelpOpen(false); setDrawerOpen(false); },
    };
    for (const [key, pg] of Object.entries(HOTKEY_PAGES)) {
      if (allowed.includes(pg)) map[key] = () => setPage(pg);
    }
    return map;
  }, [allowed.join(",")]);
  useHotkeys(hotkeys, !!user);

  function onLogin(u) {
    setUser(u);
    setPage((ROLE_PAGES[u.role] || ["rep"])[0]);
  }

  function clearResetToken() {
    setResetToken(null);
    window.history.replaceState(null, "", window.location.pathname);
  }

  function nav(id) {
    setPage(id);
    setDrawerOpen(false);
  }

  if (booting) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, background: S.g50, fontFamily: S.fontEn }}>
        <div className="hr-skeleton" style={{ width: 56, height: 56, borderRadius: 14 }} />
        <div className="hr-skeleton" style={{ width: 160, height: 12 }} />
      </div>
    );
  }

  if (!user) {
    return <Login lang={lang} onSuccess={onLogin} resetToken={resetToken} onResetDone={clearResetToken} />;
  }

  const logout = async () => { await api.logout(); setUser(null); };

  const navs = [
    { id: "dash", icon: IC.dash },
    { id: "log", icon: IC.log },
    { id: "emp", icon: IC.emp },
    { id: "rep", icon: IC.rep },
    { id: "users", icon: IC.emp },
    { id: "set", icon: IC.set },
  ].filter((n) => allowed.includes(n.id));

  const sidebarVisible = mobile ? drawerOpen : true;
  const sidebarWidth = mobile ? 256 : sw;

  const sidebar = sidebarVisible && (
    <aside aria-label={t("mainMenu")} style={{ position: "fixed", top: 0, bottom: 0, [ar ? "right" : "left"]: 0, width: sidebarWidth, background: S.w, [ar ? "borderLeft" : "borderRight"]: `1px solid ${S.g100}`, display: "flex", flexDirection: "column", transition: "width 0.22s cubic-bezier(.4,0,.2,1)", zIndex: 300, boxShadow: mobile ? S.sh2 : "2px 0 12px rgba(0,0,0,0.04)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: collapsed && !mobile ? 0 : "0 20px", justifyContent: collapsed && !mobile ? "center" : "flex-start", height: 60, borderBottom: `1px solid ${S.g100}`, flexShrink: 0 }}>
        <div style={{ width: 36, height: 36, borderRadius: S.r2, flexShrink: 0, background: `linear-gradient(135deg,${S.pri} 0%,${S.priD} 100%)`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 13, fontWeight: 800, letterSpacing: "-.5px", boxShadow: "0 2px 8px rgba(47,184,158,.3)" }}>TG</div>
        {(!collapsed || mobile) && (
          <div style={{ overflow: "hidden", minWidth: 0 }}>
            <b style={{ display: "block", fontSize: 14, fontWeight: 700, color: S.g800, whiteSpace: "nowrap" }}>Travel Gate</b>
            <small style={{ display: "block", fontSize: 10.5, color: S.g400, whiteSpace: "nowrap" }}>{t("hrSys")}</small>
          </div>
        )}
      </div>
      {(!collapsed || mobile) && <div style={{ fontSize: 10, fontWeight: 700, color: S.g400, textTransform: "uppercase", letterSpacing: ".08em", padding: "10px 12px 4px" }}>{t("mainMenu")}</div>}
      <nav style={{ flex: 1, padding: "10px 8px", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
        {navs.map((n) => {
          const act = page === n.id;
          const mini = collapsed && !mobile;
          return (
            <button key={n.id} onClick={() => nav(n.id)} aria-current={act ? "page" : undefined} title={mini ? t(n.id) : undefined} style={{ display: "flex", alignItems: "center", gap: 10, padding: mini ? 11 : "10px 12px", justifyContent: mini ? "center" : "flex-start", borderRadius: S.r2, border: "none", cursor: "pointer", background: act ? S.priL : "transparent", color: act ? S.priD : S.g400, fontWeight: act ? 600 : 500, fontSize: 13, transition: S.tr, width: "100%", textAlign: ar ? "right" : "left", fontFamily: "inherit", position: "relative" }}>
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

  const iconBtn = { width: 36, height: 36, borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: S.g400, fontFamily: "inherit", flexShrink: 0 };

  const topbar = (
    <header style={{ height: 60, background: S.w, borderBottom: `1px solid ${S.g100}`, display: "flex", alignItems: "center", justifyContent: "space-between", padding: mobile ? "0 14px" : "0 28px", position: "sticky", top: 0, zIndex: 100, boxShadow: S.sh0, flexShrink: 0, gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        {mobile && (
          <button onClick={() => setDrawerOpen(true)} aria-label={t("menu")} style={iconBtn}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
          </button>
        )}
        <h1 style={{ fontSize: 16, fontWeight: 700, color: S.g800, margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t(page)}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={() => setLang(ar ? "en" : "ar")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: S.rF, border: `1px solid ${S.g200}`, background: S.w, cursor: "pointer", fontSize: 12, color: S.g500, fontWeight: 500, fontFamily: "inherit", flexShrink: 0 }}>{IC.globe} {!mobile && <span>{t("lang")}</span>}</button>
        <button onClick={() => setDark(!dark)} aria-label={dark ? t("light") : t("dark")} title={dark ? t("light") : t("dark")} style={iconBtn}>
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
              <span style={{ fontSize: 10.5, color: S.g400 }}>{t({ hr_manager: "roleManager", hr_officer: "roleOfficer", dept_head: "roleDeptHead", employee: "roleEmployee" }[user.role] || user.role)}</span>
            </div>
          </div>
        )}
        <button onClick={logout} title={t("logout")} aria-label={t("logout")} style={{ ...iconBtn, fontSize: 14 }}>{"⏻"}</button>
      </div>
    </header>
  );

  let content;
  if (!allowed.includes(page)) {
    content = <Card><Empty text={t("noData")} /></Card>;
  } else if (page === "dash") {
    content = <Dashboard lang={lang} user={user} onNewV={() => setPage("log")} onViewAll={() => setPage("rep")} />;
  } else if (page === "log") {
    content = <LogViolation lang={lang} user={user} />;
  } else if (page === "emp") {
    content = <Employees lang={lang} user={user} />;
  } else if (page === "rep") {
    content = <Reports lang={lang} user={user} />;
  } else if (page === "users") {
    content = <Users lang={lang} user={user} />;
  } else {
    const p = PLACEHOLDERS[page];
    content = (
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t(page)}</h2>
        <Card><Empty icon={p?.icon} text={t(p?.title || "comingSoon")} sub={p?.sub && t(p.sub)} /></Card>
      </div>
    );
  }

  const shortcuts = [
    ...Object.entries(HOTKEY_PAGES).filter(([, pg]) => allowed.includes(pg)).map(([k, pg]) => [k, { dash: "scDash", log: "scLog", emp: "scEmp", rep: "scRep" }[pg]]),
    ["/", "scSearch"],
    ["?", "scHelp"],
  ];

  return (
    <ToastProvider ar={ar}>
      <div style={{ fontFamily: ar ? S.fontAr : S.fontEn, background: S.g50, color: S.g700, minHeight: "100vh", fontSize: 14, lineHeight: 1.5, direction: ar ? "rtl" : "ltr", WebkitFontSmoothing: "antialiased" }}>
        {mobile && drawerOpen && (
          <div onClick={() => setDrawerOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(8,14,22,.45)", zIndex: 250, animation: "hr-fade-in .15s ease" }} />
        )}
        {sidebar}
        <div style={{ [ar ? "marginRight" : "marginLeft"]: mobile ? 0 : sw, transition: "margin .22s cubic-bezier(.4,0,.2,1)", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
          {topbar}
          <div style={{ padding: mobile ? 16 : 28, flex: 1 }}>{content}</div>
        </div>
        <Modal open={helpOpen} onClose={() => setHelpOpen(false)} title={t("shortcuts")}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
            {shortcuts.map(([k, label]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 13, color: S.g600 }}>
                <span>{t(label)}</span>
                <kbd style={{ padding: "2px 9px", borderRadius: 6, border: `1px solid ${S.g200}`, background: S.g50, fontSize: 12, fontWeight: 700, color: S.g700, fontFamily: "inherit" }}>{k}</kbd>
              </div>
            ))}
          </div>
          <div style={{ textAlign: "end" }}>
            <button onClick={() => setHelpOpen(false)} style={{ padding: "8px 16px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.g600, cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: "inherit" }}>{t("close")}</button>
          </div>
        </Modal>
      </div>
    </ToastProvider>
  );
}
