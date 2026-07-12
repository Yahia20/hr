import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, KpiCard, KpiSkeleton, SkeletonRows, Pager, BtnPri, BtnSec, Th, FG, PenBadge, inp } from "../components";
import { ConfirmModal } from "../modal";
import ViolationsTable from "./ViolationsTable";
import { BarList, PenaltyDist, PENALTY_LEVELS } from "../charts";
import { useToast } from "../toast";
import { useDebouncedValue, useFocusSearch, usePagination } from "../hooks";
import { exportViolationsPdf, proofDataUrl } from "../pdf";

export default function Reports({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isHR = user?.role === "hr_manager" || user?.role === "hr_officer";
  const canDelete = user?.role === "hr_manager";

  const [employees, setEmployees] = useState([]);
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState({ employee: "", date_from: "", date_to: "", penalty: "" });
  const [filterOpen, setFilterOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");
  const dq = useDebouncedValue(q, 300);
  const [confirmId, setConfirmId] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const toast = useToast();
  const searchRef = useRef(null);
  useFocusSearch(searchRef);

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

  async function remove() {
    setDeleting(true);
    try {
      await api.deleteViolation(confirmId);
      toast("ok", t("delOk"));
      setConfirmId(null);
      await load();
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeleting(false);
    }
  }

  // client-side text search on top of the server-side filters
  const searched = useMemo(() => {
    const needle = dq.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) =>
      [r.employee_name, r.incident, r.category, r.comment, r.submitted_by]
        .some((f) => (f || "").toLowerCase().includes(needle))
    );
  }, [rows, dq]);

  const pg = usePagination(searched, 10);

  const totals = useMemo(() => {
    const ded = searched.reduce((s, r) => s + (r.deduction_days || 0), 0);
    const freezes = searched.filter((r) => (r.freeze_months || 0) > 0).length;
    const employeesSet = new Set(searched.map((r) => r.employee_name));
    return { count: searched.length, ded, freezes, emp: employeesSet.size };
  }, [searched]);

  const byColor = useMemo(() => {
    const m = {};
    searched.forEach((r) => { m[r.penalty_color] = (m[r.penalty_color] || 0) + 1; });
    return m;
  }, [searched]);

  const topInc = useMemo(() => {
    const m = {};
    searched.forEach((r) => { m[r.incident] = (m[r.incident] || 0) + 1; });
    return Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [searched]);

  async function exportExcel() {
    try {
      await api.exportViolations(filters);
      toast("ok", t("exportOk"));
    } catch {
      toast("err", t("errGeneric"));
    }
  }

  const [pdfBusy, setPdfBusy] = useState(false);

  async function exportPdf() {
    setPdfBusy(true);
    try {
      // Pull the proof images (stored separately from the list payload) so the
      // report shows each violation's uploaded attachment under its row.
      const proofs = {};
      await Promise.all(
        searched.filter((r) => r.has_proof).map(async (r) => {
          try {
            const p = await api.violationProof(r.id);
            const src = proofDataUrl(p.proof_image);
            if (src) proofs[r.id] = src;
          } catch { /* row still exports, just without its image */ }
        })
      );
      const ok = exportViolationsPdf({ rows: searched, t, ar, filters, proofs });
      toast(ok ? "ok" : "warn", ok ? t("exportOk") : t("popupBlocked"));
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("rep")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{ar ? "\u0633\u062C\u0644 \u0627\u0644\u0645\u062E\u0627\u0644\u0641\u0627\u062A \u0648\u0627\u0644\u062A\u062D\u0644\u064A\u0644\u0627\u062A" : "Violation history and analytics"}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
            <span style={{ position: "absolute", insetInlineStart: 12, pointerEvents: "none", display: "flex" }}>{IC.srch}</span>
            <input ref={searchRef} style={{ ...inp, padding: "10px 14px 10px 14px", paddingInlineStart: 36, width: 190 }} placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("search")} />
          </div>
          <BtnSec onClick={() => setFilterOpen(!filterOpen)}>{IC.filter} <span>{t("filters")}</span></BtnSec>
          {isHR && <BtnSec onClick={exportPdf} disabled={pdfBusy}>{IC.dl} <span>{pdfBusy ? "…" : t("exportPdf")}</span></BtnSec>}
          {isHR && <BtnPri onClick={exportExcel}>{IC.dl} <span>{t("export")}</span></BtnPri>}
        </div>
      </div>

      {filterOpen && (
        <Card style={{ background: S.g50 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14 }}>
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
                {PENALTY_LEVELS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </FG>
          </div>
        </Card>
      )}

      {err && <div style={{ color: S.err, fontSize: 13 }}>Error: {err}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 16 }}>
        {loading ? (
          <><KpiSkeleton /><KpiSkeleton /><KpiSkeleton /><KpiSkeleton /></>
        ) : (
          <>
            <KpiCard icon={IC.warn} iconBg="rgba(232,130,92,.1)" value={totals.count} label={t("totV")} />
            <KpiCard icon={IC.users} iconBg="rgba(47,184,158,.1)" value={totals.emp} label={t("totE")} />
            <KpiCard icon={IC.clock} iconBg="rgba(217,119,6,.1)" value={totals.ded} label={t("totD")} />
            <KpiCard icon={IC.shieldR} iconBg="rgba(220,38,38,.1)" value={totals.freezes} label={t("actF")} />
          </>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(290px,1fr))", gap: 20 }}>
        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("penDist")}</h3>
          {searched.length === 0 ? <Empty text={t("noData")} /> : (
            <PenaltyDist byColor={byColor} total={searched.length} lang={lang} ar={ar} />
          )}
        </Card>

        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("topInc")}</h3>
          {topInc.length === 0 ? <Empty text={t("noData")} /> : (
            <BarList items={topInc} color={S.acc} ar={ar} />
          )}
        </Card>
      </div>

      <ViolationsTable pg={pg} loading={loading} total={searched.length} canDelete={canDelete} canViewProof={isHR} onDelete={setConfirmId} ar={ar} lang={lang} t={t} />

      <ConfirmModal
        open={confirmId !== null}
        onClose={() => setConfirmId(null)}
        onConfirm={remove}
        busy={deleting}
        title={t("confirmDel")}
        body={`${t("del")} #${confirmId} — ${t("irreversible")}`}
        confirmLabel={t("del")}
        cancelLabel={t("cancel")}
      />
    </div>
  );
}
