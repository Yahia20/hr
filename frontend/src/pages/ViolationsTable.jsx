import { useState } from "react";
import PropTypes from "prop-types";
import { api } from "../api";
import { S } from "../tokens";
import { IC } from "../icons";
import { Card, Empty, Pager, PenBadge, SkeletonRows, Th } from "../components";
import { Modal } from "../modal";
import { proofDataUrl } from "../pdf";

/** Paginated violation-history table used by the Reports page. */
export default function ViolationsTable({ pg, loading, total, canDelete, canViewProof, onDelete, ar, lang, t }) {
  const cols = 7 + (canViewProof ? 1 : 0) + (canDelete ? 1 : 0);
  const [proofOpen, setProofOpen] = useState(null); // { id, src } | null
  const [proofBusy, setProofBusy] = useState(null);

  async function viewProof(vid) {
    setProofBusy(vid);
    try {
      const r = await api.violationProof(vid);
      setProofOpen({ id: vid, src: proofDataUrl(r.proof_image) });
    } catch {
      /* toast-less: the button simply stays available to retry */
    } finally {
      setProofBusy(null);
    }
  }

  return (
    <Card flush>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${S.g100}` }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, margin: 0 }}>{t("vHist")}</h3>
        <span style={{ fontSize: 12, color: S.g400 }}>{total} {t("totV")}</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead><tr>{[t("employee"), t("cat"), t("inc"), t("pen"), t("ded"), t("subBy"), t("date"), ...(canViewProof ? [t("attach")] : []), ...(canDelete ? [t("act")] : [])].map((h) => <Th key={h} ar={ar}>{h}</Th>)}</tr></thead>
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
                {canViewProof && (
                  <td style={{ padding: "12px 16px" }}>
                    {r.has_proof ? (
                      <button onClick={() => viewProof(r.id)} disabled={proofBusy === r.id} title={t("viewAttach")} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, padding: "5px 12px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.pri, cursor: "pointer", fontFamily: "inherit" }}>
                        {IC.clip} <span>{proofBusy === r.id ? "…" : t("attach")}</span>
                      </button>
                    ) : (
                      <span style={{ fontSize: 12, color: S.g300 }}>—</span>
                    )}
                  </td>
                )}
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
      <Modal open={proofOpen !== null} onClose={() => setProofOpen(null)} title={`${t("attach")} — #${proofOpen?.id ?? ""}`}>
        {proofOpen?.src ? (
          <img src={proofOpen.src} alt={t("attach")} style={{ maxWidth: "100%", maxHeight: "70vh", borderRadius: S.r2, border: `1px solid ${S.g200}`, display: "block", margin: "0 auto" }} />
        ) : (
          <Empty text={t("noAttach")} />
        )}
      </Modal>
    </Card>
  );
}

ViolationsTable.propTypes = {
  pg: PropTypes.shape({ slice: PropTypes.array.isRequired }).isRequired,
  loading: PropTypes.bool.isRequired,
  total: PropTypes.number.isRequired,
  canDelete: PropTypes.bool.isRequired,
  canViewProof: PropTypes.bool,
  onDelete: PropTypes.func.isRequired,
  ar: PropTypes.bool.isRequired,
  lang: PropTypes.string.isRequired,
  t: PropTypes.func.isRequired,
};
