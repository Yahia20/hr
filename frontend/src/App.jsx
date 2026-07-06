import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { S } from "./tokens";
import { L } from "./i18n";
import { IC } from "./icons";
import { Card, Empty } from "./components";
import { Modal } from "./modal";
import { ToastProvider } from "./toast";
import { Sidebar, Topbar } from "./layout";
import ErrorBoundary from "./ErrorBoundary";
import { useHotkeys, useLocalStorage, useMediaQuery } from "./hooks";
import Dashboard from "./pages/Dashboard";
import Attendance from "./pages/Attendance";
import Permissions from "./pages/Permissions";
import LogViolation from "./pages/LogViolation";
import Employees from "./pages/Employees";
import Reports from "./pages/Reports";
import Users from "./pages/Users";
import Settings from "./pages/Settings";
import Login from "./pages/Login";

// Pages each role may open; the first entry is the role's landing page.
const ROLE_PAGES = {
  hr_manager: ["dash", "att", "perm", "log", "emp", "rep", "users", "set"],
  hr_officer: ["dash", "att", "perm", "log", "emp", "rep"],
  dept_head: ["rep", "att", "emp"],
  employee: ["att", "rep"],
};

const NAV_ICONS = { dash: IC.dash, att: IC.att, perm: IC.perm, log: IC.log, emp: IC.emp, rep: IC.rep, users: IC.emp, set: IC.set };

// Single-key shortcuts (suppressed while typing in a field).
const HOTKEY_PAGES = { d: "dash", a: "att", n: "log", e: "emp", r: "rep" };

function readResetToken() {
  return new URLSearchParams(window.location.search).get("reset_token") || null;
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

  const onLogin = useCallback((u) => {
    setUser(u);
    setPage((ROLE_PAGES[u.role] || ["rep"])[0]);
  }, []);

  // Restore the session from the httpOnly cookie on first load.
  useEffect(() => {
    api.me()
      .then(({ user }) => onLogin(user))
      .catch(() => {})
      .finally(() => setBooting(false));
    const h = () => setUser(null);
    window.addEventListener("hr-logout", h);
    return () => window.removeEventListener("hr-logout", h);
  }, [onLogin]);

  const ar = lang === "ar";
  const t = useCallback((k) => L[lang][k] || k, [lang]);
  const allowed = useMemo(() => (user ? ROLE_PAGES[user.role] || ["rep"] : []), [user]);

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
  }, [allowed]);
  useHotkeys(hotkeys, !!user);

  const nav = useCallback((id) => { setPage(id); setDrawerOpen(false); }, []);
  const logout = useCallback(async () => { await api.logout(); setUser(null); }, []);
  const toggleLang = useCallback(() => setLang((l) => (l === "ar" ? "en" : "ar")), [setLang]);
  const toggleDark = useCallback(() => setDark((d) => !d), [setDark]);
  const openDrawer = useCallback(() => setDrawerOpen(true), []);

  function clearResetToken() {
    setResetToken(null);
    window.history.replaceState(null, "", window.location.pathname);
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

  const navs = allowed.map((id) => ({ id, icon: NAV_ICONS[id] }));

  const PAGES = {
    dash: <Dashboard lang={lang} user={user} onNewV={() => nav("log")} onViewAll={() => nav("rep")} />,
    att: <Attendance lang={lang} user={user} />,
    perm: <Permissions lang={lang} user={user} />,
    log: <LogViolation lang={lang} user={user} />,
    emp: <Employees lang={lang} user={user} />,
    rep: <Reports lang={lang} user={user} />,
    users: <Users lang={lang} user={user} />,
    set: <Settings lang={lang} user={user} dark={dark} onToggleDark={toggleDark} onToggleLang={toggleLang} />,
  };

  let content;
  if (!allowed.includes(page) || !PAGES[page]) {
    content = <Card><Empty text={t("noData")} /></Card>;
  } else {
    content = PAGES[page];
  }

  const shortcuts = [
    ...Object.entries(HOTKEY_PAGES).filter(([, pg]) => allowed.includes(pg)).map(([k, pg]) => [k, { dash: "scDash", att: "scAtt", log: "scLog", emp: "scEmp", rep: "scRep" }[pg]]),
    ["/", "scSearch"],
    ["?", "scHelp"],
  ];

  return (
    <ToastProvider ar={ar}>
      <div style={{ fontFamily: ar ? S.fontAr : S.fontEn, background: S.g50, color: S.g700, minHeight: "100vh", fontSize: 14, lineHeight: 1.5, direction: ar ? "rtl" : "ltr", WebkitFontSmoothing: "antialiased" }}>
        {mobile && drawerOpen && (
          <div onClick={() => setDrawerOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(8,14,22,.45)", zIndex: 250, animation: "hr-fade-in .15s ease" }} />
        )}
        {(!mobile || drawerOpen) && (
          <Sidebar ar={ar} t={t} mobile={mobile} collapsed={collapsed} setCollapsed={setCollapsed} navs={navs} page={page} onNav={nav} />
        )}
        <div style={{ [ar ? "marginRight" : "marginLeft"]: mobile ? 0 : collapsed ? 68 : 256, transition: "margin .22s cubic-bezier(.4,0,.2,1)", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
          <Topbar ar={ar} t={t} mobile={mobile} page={page} user={user} dark={dark} onToggleDark={toggleDark} onToggleLang={toggleLang} onLogout={logout} onOpenDrawer={openDrawer} />
          <div style={{ padding: mobile ? 16 : 28, flex: 1 }}>
            {/* keyed by page so navigating away resets a tripped boundary */}
            <ErrorBoundary key={page} title={t("errGeneric")} message={t("errBoundaryMsg")} retryLabel={t("retry")}>
              {content}
            </ErrorBoundary>
          </div>
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
