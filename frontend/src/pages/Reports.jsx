import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, KpiCard, BtnPri, BtnSec, Th, FG, PenBadge, inp } from "../components";

const PENALTIES = ["Yellow", "Orange", "Red", "Black", "Investigation"];

export default function Reports({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isHR = user?.role === "hr_manager" || user?.role === "hr_officer";
  const canDelete = user?.role === "hr_manager";

  const [employees, setEmployees] = useState([]);
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState({ employee: "", date_from: "", date_to: "", penalty: "" });
  const [filterOpen, setFilterOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  async function load() {
    setLoading(true); setErr(null);
    try {
      const r = await api.listViolations(filters);
      setRows(r);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user?.role === "employee") return; // scoped server-side; no employee list access
    api.listEmployees().then(setEmployees).catch(() => {});
  }, []);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters.employee, filters.date_from, filters.date_to, filters.penalty]);

  async function remove(id) {
    if (!confirm(`${t("del")} #${id}?`)) return;
    await api.deleteViolation(id);
    await load();
  }

  const totals = useMemo(() => {
    const ded = rows.reduce((s, r) => s + (r.deduction_days || 0), 0);
    const freezes = rows.filter((r) => (r.freeze_months || 0) > 0).length;
    const employeesSet = new Set(rows.map((r) => r.employee_name));
    return { count: rows.length, ded, freezes, emp: employeesSet.size };
  }, [rows]);

  const byColor = useMemo(() => {
    const m = {};
    rows.forEach((r) => { m[r.penalty_color] = (m[r.penalty_color] || 0) + 1; });
    return m;
  }, [rows]);

  const topInc = useMemo(() => {
    const m = {};
    rows.forEach((r) => { m[r.incident] = (m[r.incident] || 0) + 1; });
    return Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [rows]);

  async function exportExcel() {
    try { await api.exportViolations(filters); }
    catch (e) { setErr(e.message); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("rep")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{ar ? "\u0633\u062C\u0644 \u0627\u0644\u0645\u062E\u0627\u0644\u0641\u0627\u062A \u0648\u0627\u0644\u062A\u062D\u0644\u064A\u0644\u0627\u062A" : "Violation history and analytics"}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <BtnSec onClick={() => setFilterOpen(!filterOpen)}>{IC.filter} <span>{t("filters")}</span></BtnSec>
          {isHR && <BtnPri onClick={exportExcel}>{IC.dl} <span>{t("export")}</span></BtnPri>}
        </div>
      </div>

      {filterOpen && (
        <Card style={{ background: S.g50 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14 }}>
            <FG label={t("employee")}>
              <select style={{ ...inp, cursor: "pointer" }} value={filters.employee} onChange={(e) => setFilters({ ...filters, employee: e.target.value })}>
                <option value="">{t("all")}</option>
                {employees.map((e) => <option key={e.id} value={e.name}>{e.name}</option>)}
              </select>
            </FG>
            <FG label={t("from")}>
              <input style={inp} type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} />
            </FG>
            <FG label={t("to")}>
              <input style={inp} type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} />
            </FG>
            <FG label={t("penLvl")}>
              <select style={{ ...inp, cursor: "pointer" }} value={filters.penalty} onChange={(e) => setFilters({ ...filters, penalty: e.target.value })}>
                <option value="">{t("all")}</option>
                {PENALTIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </FG>
          </div>
        </Card>
      )}

      {err && <div style={{ color: S.err, fontSize: 13 }}>Error: {err}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }}>
        <KpiCard icon={IC.warn} iconBg="rgba(232,130,92,.1)" value={totals.count} label={t("totV")} />
        <KpiCard icon={IC.users} iconBg="rgba(47,184,158,.1)" value={totals.emp} label={t("totE")} />
        <KpiCard icon={IC.clock} iconBg="rgba(217,119,6,.1)" value={totals.ded} label={t("totD")} />
        <KpiCard icon={IC.shieldR} iconBg="rgba(220,38,38,.1)" value={totals.freezes} label={t("actF")} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("penDist")}</h3>
          {rows.length === 0 ? <Empty text={t("noData")} /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {PENALTIES.map((lv) => {
                const count = byColor[lv] || 0;
                const pct = rows.length ? (count / rows.length) * 100 : 0;
                return (
                  <div key={lv} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <PenBadge level={lv} lang={lang} />
                    <div style={{ flex: 1, height: 8, background: S.g100, borderRadius: 999, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: S.pri, borderRadius: 999 }} />
                    </div>
                    <span style={{ fontSize: 12, fontWeight: 700, color: S.g700, minWidth: 28, textAlign: ar ? "left" : "right" }}>{count}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("topInc")}</h3>
          {topInc.length === 0 ? <Empty text={t("noData")} /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {topInc.map(([name, n]) => {
                const max = topInc[0][1] || 1;
                return (
                  <div key={name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 12, color: S.g600, minWidth: 150 }}>{name}</span>
                    <div style={{ flex: 1, height: 8, background: S.g100, borderRadius: 999, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${(n / max) * 100}%`, background: S.acc, borderRadius: 999 }} />
                    </div>
                    <span style={{ fontSize: 12, fontWeight: 700, color: S.g700 }}>{n}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <Card flush>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${S.g100}` }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, margin: 0 }}>{t("vHist")}</h3>
          <span style={{ fontSize: 12, color: S.g400 }}>{rows.length} records{loading ? " \u2026" : ""}</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr>{[t("employee"), t("cat"), t("inc"), t("pen"), t("ded"), t("subBy"), t("date"), ...(canDelete ? [t("act")] : [])].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={canDelete ? 8 : 7}><Empty text={t("noViol")} /></td></tr>
              ) : rows.map((r) => (
                <tr key={r.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>{r.employee_name}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{r.category}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{r.incident}</td>
                  <td style={{ padding: "12px 16px" }}><PenBadge level={r.penalty_color} lang={lang} /></td>
                  <td style={{ padding: "12px 16px", color: S.g700, fontWeight: 600 }}>{r.deduction_days} {t("days")}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{r.submitted_by}</td>
                  <td style={{ padding: "12px 16px", color: S.g500, fontSize: 12 }}>{r.created_at?.slice(0, 16)}</td>
                  {canDelete && (
                    <td style={{ padding: "12px 16px" }}>
                      <button onClick={() => remove(r.id)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
