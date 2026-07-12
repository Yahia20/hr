// PDF export via a print-optimized window (user saves as PDF from the print
// dialog). Chosen over a JS PDF library because browser printing shapes
// Arabic script and RTL layout correctly with no font embedding.

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Violation proofs are stored as bare base64 with no mime; sniff it from the
// magic bytes so the data: URL renders (uploads are images only).
export function proofDataUrl(b64) {
  if (!b64) return "";
  const mime =
    b64.startsWith("iVBOR") ? "image/png"
    : b64.startsWith("R0lGOD") ? "image/gif"
    : b64.startsWith("UklGR") ? "image/webp"
    : "image/jpeg";
  return `data:${mime};base64,${b64}`;
}

export function exportViolationsPdf({ rows, t, ar, filters = {}, proofs = {} }) {
  const headers = [t("employee"), t("cat"), t("inc"), t("pen"), t("ded"), t("subBy"), t("date")];
  const colors = { Yellow: "#D97706", Orange: "#EA580C", Red: "#DC2626", Black: "#1E293B", Investigation: "#7C3AED" };

  const filterLine = [
    filters.employee && `${t("employee")}: ${filters.employee}`,
    filters.date_from && `${t("from")}: ${filters.date_from}`,
    filters.date_to && `${t("to")}: ${filters.date_to}`,
    filters.penalty && `${t("penLvl")}: ${filters.penalty}`,
  ].filter(Boolean).join("  ·  ");

  const body = rows.map((r) => `
    <tr>
      <td><b>${esc(r.employee_name)}</b></td>
      <td>${esc(r.category)}</td>
      <td>${esc(r.incident)}</td>
      <td><span class="dot" style="background:${colors[r.penalty_color] || "#888"}"></span>${esc(r.penalty_color)}</td>
      <td>${esc(r.deduction_days)} ${esc(t("days"))}</td>
      <td>${esc(r.submitted_by)}</td>
      <td>${esc((r.created_at || "").slice(0, 16))}</td>
    </tr>${proofs[r.id] ? `
    <tr class="proofRow">
      <td colspan="7">
        <div class="proofLabel">${esc(t("attach"))}</div>
        <img class="proof" src="${proofs[r.id]}" alt="">
      </td>
    </tr>` : ""}`).join("");

  const html = `<!doctype html>
<html lang="${ar ? "ar" : "en"}" dir="${ar ? "rtl" : "ltr"}">
<head>
<meta charset="utf-8">
<title>${esc(t("vHist"))} — Travel Gate</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: ${ar ? "'Noto Sans Arabic'," : ""}'DM Sans','Segoe UI',Tahoma,sans-serif; color: #273545; margin: 28px; font-size: 12px; }
  .head { display: flex; align-items: center; justify-content: space-between; border-bottom: 3px solid #2FB89E; padding-bottom: 12px; margin-bottom: 6px; }
  .brand { display: flex; align-items: center; gap: 10px; }
  .logo { width: 34px; height: 34px; border-radius: 9px; background: #2FB89E; color: #fff; font-weight: 800; display: flex; align-items: center; justify-content: center; font-size: 13px; }
  h1 { font-size: 16px; margin: 0; }
  .sub { color: #5F6E80; font-size: 11px; }
  .meta { color: #5F6E80; font-size: 10.5px; margin: 8px 0 14px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: ${ar ? "right" : "left"}; font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: #5F6E80; border-bottom: 2px solid #ECEEF2; padding: 7px 8px; }
  td { padding: 7px 8px; border-bottom: 1px solid #ECEEF2; vertical-align: top; }
  tr { page-break-inside: avoid; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-inline-end: 5px; }
  .proofRow td { background: #FAFBFC; }
  .proofLabel { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: #5F6E80; margin-bottom: 4px; }
  .proof { max-width: 340px; max-height: 220px; border: 1px solid #ECEEF2; border-radius: 6px; }
  .tot { margin-top: 14px; font-size: 11px; color: #5F6E80; }
  @page { margin: 14mm; }
</style>
</head>
<body>
  <div class="head">
    <div class="brand">
      <div class="logo">TG</div>
      <div><h1>${esc(t("vHist"))}</h1><div class="sub">Travel Gate — ${esc(t("hrSys"))}</div></div>
    </div>
    <div class="sub">${new Date().toISOString().slice(0, 10)}</div>
  </div>
  ${filterLine ? `<div class="meta">${esc(filterLine)}</div>` : ""}
  <table>
    <thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${body}</tbody>
  </table>
  <div class="tot">${rows.length} ${esc(t("totV"))} · ${esc(t("totD"))}: ${rows.reduce((s, r) => s + (r.deduction_days || 0), 0)}</div>
  <script>window.onload = function () { window.print(); };</script>
</body>
</html>`;

  const win = window.open("", "_blank");
  if (!win) return false;
  win.document.write(html);
  win.document.close();
  return true;
}
