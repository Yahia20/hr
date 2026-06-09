import { useEffect, useState } from "react";
import { api } from "../api";
import { S, pbStyle } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, KpiCard, KpiSkeleton, SkeletonRows, BtnPri, BtnSec, BtnGhost, PenBadge, Th } from "../components";
import { useToast } from "../toast";
import { BarList, PenaltyDist } from "../charts";

export default function Dashboard({ lang, user, onNewV, onViewAll }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const toast = useToast();
  const loading = !data && !err;

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setErr(e.message));
  }, []);

  const totals = data?.totals || { violations: 0, employees: 0, deduction_days: 0, active_freezes: 0 };
  const byColor = data?.by_color || {};
  const totalByColor = Object.values(byColor).reduce((a, b) => a + b, 0) || 1;
  const recent = data?.recent || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, letterSpacing: "-.4px", margin: 0 }}>
            {t("welcome")}, {user?.name} {"\u{1F44B}"}
          </h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{t("todayAct")}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <BtnPri onClick={onNewV}>{IC.plus} <span>{t("newV")}</span></BtnPri>
          <BtnSec onClick={() => api.exportViolations({}).then(() => toast("ok", t("exportOk"))).catch(() => toast("err", t("errGeneric")))}>{IC.dl} <span>{t("export")}</span></BtnSec>
        </div>
      </div>

      {err && <div style={{ color: S.err, fontSize: 13 }}>Error loading data: {err}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 16 }}>
        {loading ? (
          <><KpiSkeleton /><KpiSkeleton /><KpiSkeleton /><KpiSkeleton /></>
        ) : (
          <>
            <KpiCard icon={IC.warn} iconBg="rgba(232,130,92,.1)" value={totals.violations} label={t("totV")} />
            <KpiCard icon={IC.users} iconBg="rgba(47,184,158,.1)" value={totals.employees} label={t("totE")} />
            <KpiCard icon={IC.clock} iconBg="rgba(217,119,6,.1)" value={totals.deduction_days} label={t("totD")} />
            <KpiCard icon={IC.shieldR} iconBg="rgba(220,38,38,.1)" value={totals.active_freezes} label={t("actF")} />
          </>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(290px,1fr))", gap: 20 }}>
        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 18 }}>{t("trend")}</h3>
          {data?.monthly?.length ? (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 160 }}>
              {data.monthly.map((m) => {
                const max = Math.max(...data.monthly.map((x) => x.count), 1);
                const h = (m.count / max) * 100;
                return (
                  <div key={m.month} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                    <div style={{ width: "100%", height: `${h}%`, background: S.pri, borderRadius: "6px 6px 0 0", minHeight: 4 }} />
                    <span style={{ fontSize: 10, color: S.g400 }}>{m.month.slice(5)}</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: S.g700 }}>{m.count}</span>
                  </div>
                );
              })}
            </div>
          ) : <Empty text={t("noData")} />}
        </Card>

        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 18 }}>{t("byCat")}</h3>
          {Object.keys(data?.by_category || {}).length ? (
            <BarList items={Object.entries(data.by_category)} ar={ar} labelWidth={140} />
          ) : <Empty text={t("noData")} />}
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 20 }}>
        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 16 }}>{t("penDist")}</h3>
          <PenaltyDist byColor={byColor} total={totalByColor} lang={lang} ar={ar} />
        </Card>

        <Card flush>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${S.g100}` }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, margin: 0 }}>{t("recent")}</h3>
            <BtnGhost onClick={onViewAll}>{t("viewAll")} {"\u2192"}</BtnGhost>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr>{[t("employee"), t("inc"), t("pen"), t("ded"), t("date")].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
              <tbody>
                {loading ? (
                  <SkeletonRows rows={5} cols={5} />
                ) : recent.length === 0 ? (
                  <tr><td colSpan={5}><Empty text={t("noViol")} sub={t("firstViolHint")} action={<BtnPri onClick={onNewV}>{IC.plus} <span>{t("newV")}</span></BtnPri>} /></td></tr>
                ) : recent.map((v) => (
                  <tr key={v.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                    <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>{v.employee_name}</td>
                    <td style={{ padding: "12px 16px", color: S.g600 }}>{v.incident}</td>
                    <td style={{ padding: "12px 16px" }}><PenBadge level={v.penalty_color} lang={lang} /></td>
                    <td style={{ padding: "12px 16px", color: S.g700, fontWeight: 600 }}>{v.deduction_days} {t("days")}</td>
                    <td style={{ padding: "12px 16px", color: S.g500, fontSize: 12 }}>{v.created_at?.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
