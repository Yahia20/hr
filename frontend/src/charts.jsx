import { memo } from "react";
import PropTypes from "prop-types";
import { S, pbStyle } from "./tokens";
import { PenBadge } from "./components";

export const PENALTY_LEVELS = ["Yellow", "Orange", "Red", "Black", "Investigation"];

/** Horizontal labeled bars (top incidents, categories, ...). */
export const BarList = memo(function BarList({ items, color = S.pri, ar, labelWidth = 150 }) {
  const max = Math.max(...items.map(([, n]) => n), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {items.map(([name, n]) => (
        <div key={name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 12, color: S.g600, minWidth: labelWidth }}>{name}</span>
          <div style={{ flex: 1, height: 8, background: S.g100, borderRadius: 999, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${(n / max) * 100}%`, background: color, borderRadius: 999 }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: S.g700 }}>{n}</span>
        </div>
      ))}
    </div>
  );
});

BarList.propTypes = {
  items: PropTypes.arrayOf(PropTypes.array).isRequired,
  color: PropTypes.string,
  ar: PropTypes.bool,
  labelWidth: PropTypes.number,
};

/** Penalty level distribution with badge, bar, and count. */
export const PenaltyDist = memo(function PenaltyDist({ byColor, total, lang, ar }) {
  const denom = total || 1;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {PENALTY_LEVELS.map((lv) => {
        const count = byColor[lv] || 0;
        return (
          <div key={lv} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
            <PenBadge level={lv} lang={lang} />
            <div style={{ flex: 1, height: 7, background: S.g100, borderRadius: 999, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${(count / denom) * 100}%`, background: pbStyle[lv].dot, borderRadius: 999 }} />
            </div>
            <span style={{ fontSize: 13, fontWeight: 700, color: S.g700, minWidth: 26, textAlign: ar ? "left" : "right" }}>{count}</span>
          </div>
        );
      })}
    </div>
  );
});

PenaltyDist.propTypes = {
  byColor: PropTypes.object.isRequired,
  total: PropTypes.number.isRequired,
  lang: PropTypes.string.isRequired,
  ar: PropTypes.bool,
};
