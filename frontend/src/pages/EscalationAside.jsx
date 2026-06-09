import PropTypes from "prop-types";
import { S } from "../tokens";
import { IC } from "../icons";
import { Card, PenBadge } from "../components";

/** Side panel on the Log Violation page: escalation path + incident details. */
export default function EscalationAside({ meta, preview, cat, lang, t }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card style={{ background: S.infoL, borderColor: "rgba(37,99,235,.15)" }}>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: S.info, marginTop: 0, marginBottom: 12, display: "flex", alignItems: "center", gap: 7 }}>{IC.shield}<span>{t("escPath")}</span></h4>
        {(meta?.escalation || []).map((step, i) => {
          const isNext = preview && preview.penalty_color === step && !meta.escalation.slice(0, i).some((s) => s === step);
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", opacity: isNext ? 1 : 0.75 }}>
              <span style={{ width: 22, height: 22, borderRadius: "50%", flexShrink: 0, background: S.w, border: `1.5px solid ${isNext ? S.info : S.g200}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: isNext ? S.info : S.g400 }}>{i + 1}</span>
              <PenBadge level={step} lang={lang} />
            </div>
          );
        })}
      </Card>
      <Card>
        <h4 style={{ fontSize: 13, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 12 }}>{t("details")}</h4>
        {[
          { label: t("reset"), value: `${meta?.reset || 30} ${t("days")}` },
          { label: t("maxS"), value: meta?.escalation?.length || 0 },
          { label: t("cat"), value: cat },
        ].map((r, i, a) => (
          <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderBottom: i < a.length - 1 ? `1px solid ${S.g100}` : "none" }}>
            <span style={{ fontSize: 12, color: S.g400 }}>{r.label}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: S.g700 }}>{r.value}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

EscalationAside.propTypes = {
  meta: PropTypes.shape({ escalation: PropTypes.array, reset: PropTypes.number }),
  preview: PropTypes.shape({ penalty_color: PropTypes.string }),
  cat: PropTypes.string,
  lang: PropTypes.string.isRequired,
  t: PropTypes.func.isRequired,
};
