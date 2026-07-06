import { useEffect, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, Empty, SkeletonRows, Pager, BtnPri, BtnSec, Th, FG, inp } from "../components";
import { ConfirmModal } from "../modal";
import { useToast } from "../toast";
import { useDebouncedValue } from "../hooks";
import { getClockAssertion, getPosition, registerFingerprint, webauthnSupported } from "../webauthn";

const PAGE_SIZE = 10;

const utc = (s) => (s ? new Date(s.replace(" ", "T") + "Z") : null);
const fmtTime = (s, ar) => {
  const d = utc(s);
  return d ? d.toLocaleTimeString(ar ? "ar-SA" : "en-GB", { hour: "2-digit", minute: "2-digit" }) : "—";
};

const ERR_KEYS = {
  already_clocked_in: "errAlreadyIn",
  not_clocked_in: "errNotIn",
  location_required: "errLocReq",
  fingerprint_not_registered: "errFpNeeded",
  fingerprint_required: "errFpNeeded",
  fingerprint_failed: "errFpFailed",
  challenge_expired: "errFpFailed",
  unknown_credential: "errFpFailed",
  registration_failed: "errFpFailed",
  geo_denied: "errGeoDenied",
  geo_unsupported: "errGeoDenied",
};

function errMsg(t, e) {
  if (e?.name === "NotAllowedError") return t("fpCancelled");
  const m = e?.message || "";
  if (m.startsWith("outside_geofence")) {
    const d = m.split(":")[1];
    return t("errOutside") + (d ? ` (~${d}m)` : "");
  }
  return ERR_KEYS[m] ? t(ERR_KEYS[m]) : m || t("errGeneric");
}

export default function Attendance({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;
  const isHR = user?.role === "hr_manager" || user?.role === "hr_officer";
  const isManager = user?.role === "hr_manager";
  const isEmployee = user?.role === "employee";
  const toast = useToast();

  const [me, setMe] = useState(null);
  const [creds, setCreds] = useState([]);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [offices, setOffices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // "in" | "out" | "fp" | "office"
  const [now, setNow] = useState(new Date());
  const [filters, setFilters] = useState({ date_from: "", date_to: "", employee: "" });
  const [officeForm, setOfficeForm] = useState({ name: "", lat: "", lng: "", radius_m: 150 });
  const [confirmOffice, setConfirmOffice] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const dqEmployee = useDebouncedValue(filters.employee, 300);

  async function loadMe() {
    setMe(await api.attMe());
    setCreds(await api.listWaCredentials());
  }
  async function loadHistory(p = page) {
    const res = await api.listAttendance({
      ...filters,
      employee: dqEmployee,
      limit: PAGE_SIZE,
      offset: (p - 1) * PAGE_SIZE,
    });
    setRows(res.rows);
    setTotal(res.total);
  }
  async function loadOffices() {
    if (isHR) setOffices(await api.listOffices());
  }
  useEffect(() => {
    Promise.all([loadMe(), loadOffices()])
      .catch(() => toast("err", t("errGeneric")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Reset to the first page whenever the filters change.
  useEffect(() => { setPage(1); }, [dqEmployee, filters.date_from, filters.date_to]);
  useEffect(() => {
    loadHistory(page)
      .catch(() => toast("err", t("errGeneric")))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dqEmployee, filters.date_from, filters.date_to, page]);

  async function punch(kind) {
    setBusy(kind);
    try {
      const pos = await getPosition().catch((e) => {
        if (me?.require_geofence) throw e;
        return {};
      });
      let assertion;
      if (me?.require_biometric) {
        if (!me.has_credential) throw new Error("fingerprint_not_registered");
        assertion = await getClockAssertion();
      }
      await (kind === "in" ? api.clockIn : api.clockOut)({ ...pos, assertion });
      toast("ok", t(kind === "in" ? "clockInOk" : "clockOutOk"));
      await Promise.all([loadMe(), loadHistory()]);
    } catch (e) {
      toast("err", errMsg(t, e));
    } finally {
      setBusy(null);
    }
  }

  async function registerFp() {
    setBusy("fp");
    try {
      const label = /mobile|android|iphone/i.test(navigator.userAgent) ? "Mobile" : "Desktop";
      await registerFingerprint(label);
      toast("ok", t("fpOk"));
      await loadMe();
    } catch (e) {
      toast("err", errMsg(t, e));
    } finally {
      setBusy(null);
    }
  }

  async function removeCred(id) {
    try {
      await api.deleteWaCredential(id);
      toast("ok", t("delOk"));
      await loadMe();
    } catch {
      toast("err", t("errGeneric"));
    }
  }

  async function useMyLocation() {
    try {
      const pos = await getPosition();
      setOfficeForm((f) => ({ ...f, lat: pos.lat.toFixed(6), lng: pos.lng.toFixed(6) }));
    } catch (e) {
      toast("err", errMsg(t, e));
    }
  }

  async function addOffice() {
    if (!officeForm.name.trim() || officeForm.lat === "" || officeForm.lng === "") return;
    setBusy("office");
    try {
      await api.createOffice({
        name: officeForm.name,
        lat: parseFloat(officeForm.lat),
        lng: parseFloat(officeForm.lng),
        radius_m: parseInt(officeForm.radius_m, 10) || 150,
      });
      setOfficeForm({ name: "", lat: "", lng: "", radius_m: 150 });
      toast("ok", t("savedOk"));
      await Promise.all([loadOffices(), loadMe()]);
    } catch (e) {
      toast("err", errMsg(t, e));
    } finally {
      setBusy(null);
    }
  }

  async function removeOffice() {
    setDeleting(true);
    try {
      await api.deleteOffice(confirmOffice.id);
      toast("ok", t("delOk"));
      setConfirmOffice(null);
      await Promise.all([loadOffices(), loadMe()]);
    } catch {
      toast("err", t("errGeneric"));
    } finally {
      setDeleting(false);
    }
  }

  const today = me?.today;
  const canIn = !today;
  const canOut = !!today;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pager = {
    page, pages, total, setPage,
    from: total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1,
    to: Math.min(page * PAGE_SIZE, total),
  };
  const cols = isEmployee ? 6 : 7;
  // Clamp back onto a valid page if the result set shrank (e.g. after filtering).
  useEffect(() => { if (page > pages) setPage(pages); }, [page, pages]);

  const chip = (label, value, on) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, padding: "10px 16px", borderRadius: S.r2, background: on ? S.okL : S.g50, border: `1px solid ${on ? "transparent" : S.g100}`, minWidth: 110 }}>
      <span style={{ fontSize: 11, color: S.g400, fontWeight: 600 }}>{label}</span>
      <b style={{ fontSize: 16, color: on ? S.ok : S.g500 }}>{value}</b>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("att")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{t("attSub")}</p>
        </div>
        {isHR && (
          <BtnSec onClick={() => api.exportAttendance(filters).then(() => toast("ok", t("exportOk"))).catch(() => toast("err", t("errGeneric")))}>
            {IC.dl} <span>{t("export")}</span>
          </BtnSec>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 20 }}>
        {/* Clock in/out */}
        <Card>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16, padding: "8px 0" }}>
            <div style={{ fontSize: 40, fontWeight: 800, color: S.g800, letterSpacing: -1, fontVariantNumeric: "tabular-nums" }}>
              {now.toLocaleTimeString(ar ? "ar-SA" : "en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </div>
            <div style={{ fontSize: 13, color: S.g400 }}>
              {now.toLocaleDateString(ar ? "ar-SA" : "en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
              {chip(t("timeIn"), fmtTime(today?.clock_in_at, ar), !!today?.clock_in_at)}
              {chip(t("timeOut"), fmtTime(today?.clock_out_at, ar), !!today?.clock_out_at)}
            </div>
            {!today && <div style={{ fontSize: 12.5, color: S.g400 }}>{t("notClockedIn")}</div>}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
              <BtnPri onClick={() => punch("in")} disabled={!canIn || busy === "in"}>
                {IC.finger} <span>{busy === "in" ? t("loading") : t("clockIn")}</span>
              </BtnPri>
              <button onClick={() => punch("out")} disabled={!canOut || busy === "out"} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "9px 18px", borderRadius: S.r2, border: "none", cursor: !canOut || busy === "out" ? "not-allowed" : "pointer", opacity: !canOut || busy === "out" ? 0.5 : 1, fontSize: 13, fontWeight: 600, fontFamily: "inherit", background: S.err, color: "#fff" }}>
                {IC.finger} <span>{busy === "out" ? t("loading") : t("clockOut")}</span>
              </button>
            </div>
            {(me?.require_geofence || me?.require_biometric) && (
              <div style={{ display: "flex", gap: 12, fontSize: 11.5, color: S.g400, flexWrap: "wrap", justifyContent: "center" }}>
                {me?.require_geofence && <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>{IC.pin} {t("gpsChecked")}</span>}
                {me?.require_biometric && <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>{IC.finger} {t("fpChecked")}</span>}
              </div>
            )}
          </div>
        </Card>

        {/* Fingerprint registration */}
        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 6 }}>{t("fingerprint")}</h3>
          <p style={{ fontSize: 12.5, color: S.g400, marginTop: 0 }}>{t("fpSub")}</p>
          {!webauthnSupported() ? (
            <div style={{ fontSize: 13, color: S.err }}>{t("fpUnsupported")}</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {creds.length === 0 ? (
                <div style={{ fontSize: 13, color: S.warn, fontWeight: 600 }}>{t("fpNone")}</div>
              ) : (
                creds.map((c) => (
                  <div key={c.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 12px", borderRadius: S.r2, background: S.g50, border: `1px solid ${S.g100}` }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: S.g700, fontWeight: 600 }}>
                      {IC.finger} {c.device_label || t("fingerprint")}
                      <small style={{ color: S.g400, fontWeight: 400 }}>{(c.created_at || "").slice(0, 10)}</small>
                    </span>
                    <button onClick={() => removeCred(c.id)} style={{ fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                  </div>
                ))
              )}
              <div>
                <BtnPri onClick={registerFp} disabled={busy === "fp"}>
                  {IC.finger} <span>{busy === "fp" ? t("loading") : creds.length ? t("fpAddDevice") : t("fpRegister")}</span>
                </BtnPri>
              </div>
              <small style={{ fontSize: 11.5, color: S.g400 }}>{t("fpHint")}</small>
            </div>
          )}
        </Card>
      </div>

      {/* Office locations (HR manager) */}
      {isHR && (
        <Card>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, marginTop: 0, marginBottom: 6 }}>{t("offices")}</h3>
          <p style={{ fontSize: 12.5, color: S.g400, marginTop: 0 }}>{t("officesSub")}</p>
          {offices.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {offices.map((o) => (
                <div key={o.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 12px", borderRadius: S.r2, background: S.g50, border: `1px solid ${S.g100}`, gap: 10, flexWrap: "wrap" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: S.g700, fontWeight: 600 }}>
                    {IC.pin} {o.name}
                    <small style={{ color: S.g400, fontWeight: 400, direction: "ltr" }}>{o.lat.toFixed(5)}, {o.lng.toFixed(5)} · {o.radius_m}m</small>
                  </span>
                  {isManager && (
                    <button onClick={() => setConfirmOffice(o)} style={{ fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                  )}
                </div>
              ))}
            </div>
          )}
          {offices.length === 0 && <div style={{ fontSize: 13, color: S.warn, fontWeight: 600, marginBottom: 14 }}>{t("noOffices")}</div>}
          {isManager && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 14, marginBottom: 14 }}>
                <FG label={t("officeName")}><input style={inp} value={officeForm.name} onChange={(e) => setOfficeForm({ ...officeForm, name: e.target.value })} /></FG>
                <FG label={t("latitude")}><input style={inp} type="number" step="any" value={officeForm.lat} onChange={(e) => setOfficeForm({ ...officeForm, lat: e.target.value })} /></FG>
                <FG label={t("longitude")}><input style={inp} type="number" step="any" value={officeForm.lng} onChange={(e) => setOfficeForm({ ...officeForm, lng: e.target.value })} /></FG>
                <FG label={t("radiusM")}><input style={inp} type="number" min="20" max="5000" value={officeForm.radius_m} onChange={(e) => setOfficeForm({ ...officeForm, radius_m: e.target.value })} /></FG>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <BtnSec onClick={useMyLocation}>{IC.pin} <span>{t("useMyLocation")}</span></BtnSec>
                <BtnPri onClick={addOffice} disabled={busy === "office"}>{IC.plus} <span>{t("addOffice")}</span></BtnPri>
              </div>
            </>
          )}
        </Card>
      )}

      {/* History */}
      <Card flush>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, padding: "16px 16px 0" }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: S.g800, margin: 0 }}>{t("attHistory")}</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            {!isEmployee && (
              <input style={{ ...inp, width: 160, padding: "8px 12px" }} placeholder={t("employee")} value={filters.employee} onChange={(e) => setFilters({ ...filters, employee: e.target.value })} />
            )}
            <input style={{ ...inp, width: 140, padding: "8px 12px" }} type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} aria-label={t("from")} />
            <input style={{ ...inp, width: 140, padding: "8px 12px" }} type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} aria-label={t("to")} />
          </div>
        </div>
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                {[t("date"), ...(isEmployee ? [] : [t("employee")]), t("timeIn"), t("timeOut"), t("hours"), t("office"), t("fingerprint")].map((h) => (
                  <Th key={h} ar={ar}>{h}</Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} cols={cols} />
              ) : rows.length === 0 ? (
                <tr><td colSpan={cols}><Empty text={t("noAtt")} /></td></tr>
              ) : rows.map((r) => (
                <tr key={r.id} style={{ borderBottom: `1px solid ${S.g100}` }}>
                  <td style={{ padding: "12px 16px", color: S.g600, whiteSpace: "nowrap" }}>{r.work_date}</td>
                  {!isEmployee && <td style={{ padding: "12px 16px", fontWeight: 600, color: S.g700 }}>{r.name}<small style={{ display: "block", color: S.g400, fontWeight: 400 }}>{r.department}</small></td>}
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{fmtTime(r.clock_in_at, ar)}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{fmtTime(r.clock_out_at, ar)}</td>
                  <td style={{ padding: "12px 16px", color: S.g600, fontVariantNumeric: "tabular-nums" }}>{r.worked_hours ?? "—"}</td>
                  <td style={{ padding: "12px 16px", color: S.g600 }}>{r.clock_in_office || r.clock_out_office || "—"}</td>
                  <td style={{ padding: "12px 16px", color: r.clock_in_verified ? S.ok : S.g400 }}>{r.clock_in_verified ? "✓" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && <Pager {...pager} ar={ar} label={t("att")} />}
      </Card>

      <ConfirmModal
        open={confirmOffice !== null}
        onClose={() => setConfirmOffice(null)}
        onConfirm={removeOffice}
        busy={deleting}
        title={t("confirmDel")}
        body={`${t("del")}: ${confirmOffice?.name || ""} — ${t("irreversible")}`}
        confirmLabel={t("del")}
        cancelLabel={t("cancel")}
      />
    </div>
  );
}
