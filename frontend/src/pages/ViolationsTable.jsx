import PropTypes from "prop-types";
import { S } from "../tokens";
import { Card, Empty, Pager, PenBadge, SkeletonRows, Th } from "../components";

/** Paginated violation-history table used by the Reports page. */
export default function ViolationsTable({ pg, loading, total, canDelete, onDelete, ar, lang, t }) {
  const cols = canDelete ? 8 : 7;
  return (
    <Card flush>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${S.g100}` }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, margin: 0 }}>{t("vHist")}</h3>
        <span style={{ fontSize: 12, color: S.g400 }}>{total} {t("totV")}</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead><tr>{[t("employee"), t("cat"), t("inc"), t("pen"), t("ded"), t("subBy"), t("date"), ...(canDelete ? [t("act")] : [])].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
          <tbody>
            {loading ? (
              <SkeletonRows rows={6} cols={cols} />
            ) : total === 0 ? (
              <tr><td colSpan={cols}><Empty text={t("noViol")} sub={t("firstViolHint")} /></td></tr>
            ) : pg.slice.map((r) => (
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
                    <button onClick={() => onDelete(r.id)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!loading && <Pager {...pg} ar={ar} label={t("vHist")} />}
    </Card>
  );
}

ViolationsTable.propTypes = {
  pg: PropTypes.shape({ slice: PropTypes.array.isRequired }).isRequired,
  loading: PropTypes.bool.isRequired,
  total: PropTypes.number.isRequired,
  canDelete: PropTypes.bool.isRequired,
  onDelete: PropTypes.func.isRequired,
  ar: PropTypes.bool.isRequired,
  lang: PropTypes.string.isRequired,
  t: PropTypes.func.isRequired,
};
