// All colors resolve through CSS variables (src/theme.css) so the dark theme
// is a single `data-theme` attribute flip on <html>.
export const S = {
  pri: "var(--pri)", priD: "var(--priD)", priL: "var(--priL)", priM: "var(--priM)",
  acc: "var(--acc)", w: "var(--w)", g50: "var(--g50)", g100: "var(--g100)",
  g200: "var(--g200)", g300: "var(--g300)", g400: "var(--g400)", g500: "var(--g500)",
  g600: "var(--g600)", g700: "var(--g700)", g800: "var(--g800)",
  ok: "var(--ok)", okL: "var(--okL)", warn: "var(--warn)", warnL: "var(--warnL)",
  err: "var(--err)", errL: "var(--errL)", info: "var(--info)", infoL: "var(--infoL)",
  sh0: "var(--sh0)",
  sh1: "var(--sh1)",
  sh2: "var(--sh2)",
  r2: 10, r3: 14, rF: 999,
  tr: "all 0.18s cubic-bezier(.4,0,.2,1)",
  fontEn: "'DM Sans Variable','DM Sans','Segoe UI',sans-serif",
  fontAr: "'Noto Sans Arabic Variable','Noto Sans Arabic','Segoe UI',sans-serif",
};

export const pbStyle = {
  Yellow: { bg: "var(--pYB)", color: "var(--pY)", dot: "var(--pYD)", border: "var(--pYBor)" },
  Orange: { bg: "var(--pOB)", color: "var(--pO)", dot: "var(--pOD)", border: "var(--pOBor)" },
  Red:    { bg: "var(--pRB)", color: "var(--pR)", dot: "var(--pRD)", border: "var(--pRBor)" },
  Black:  { bg: "var(--pKB)", color: "var(--pK)", dot: "var(--pKD)", border: "var(--pKBor)" },
  Investigation: { bg: "var(--pIB)", color: "var(--pI)", dot: "var(--pID)", border: "var(--pIBor)" },
};

export const GUIDE = [
  { lv: "Yellow", dd: "0",   ic: "\u{1F7E1}" },
  { lv: "Orange", dd: "0.5", ic: "\u{1F7E0}" },
  { lv: "Red",    dd: "2",   ic: "\u{1F534}" },
  { lv: "Black",  dd: "4",   ic: "\u{2B1B}" },
  { lv: "Investigation", dd: "—", ic: "\u{1F50D}" },
];
