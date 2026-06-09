import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { S } from "../tokens";
import { L } from "../i18n";
import { IC } from "../icons";
import { Card, BtnPri, BtnSec, PenBadge, FG, inp, Skeleton } from "../components";
import { GUIDE } from "../tokens";
import { useToast } from "../toast";
import { useMediaQuery } from "../hooks";

export default function LogViolation({ lang, user }) {
  const ar = lang === "ar";
  const t = (k) => L[lang][k] || k;

  const [matrix, setMatrix] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [cat, setCat] = useState("");
  const [inc, setInc] = useState("");
  const [emp, setEmp] = useState("");
  const [comment, setComment] = useState("");
  const [force, setForce] = useState(false);
  const [override, setOverride] = useState(-1);
  const [preview, setPreview] = useState(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [proof, setProof] = useState({ name: "", dataUrl: "" });
  const toast = useToast();
  const narrow = useMediaQuery("(max-width: 980px)");

  function onProofChange(e) {
    const file = e.target.files?.[0];
    if (!file) { setProof({ name: "", dataUrl: "" }); return; }
    if (file.size > 5 * 1024 * 1024) {
      setMsg({ type: "err", text: ar ? "\u0627\u0644\u062D\u062C\u0645 \u0623\u0643\u0628\u0631 \u0645\u0646 5MB" : "File exceeds 5MB" });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setProof({ name: file.name, dataUrl: reader.result });
    reader.readAsDataURL(file);
  }

  useEffect(() => {
    api.matrix().then((m) => {
      setMatrix(m);
      const first = Object.keys(m.matrix)[0];
      setCat(first);
      setInc(Object.keys(m.matrix[first])[0]);
    });
    api.listEmployees().then(setEmployees);
  }, []);

  useEffect(() => {
    if (!matrix || !cat) return;
    const first = Object.keys(matrix.matrix[cat])[0];
    setInc(first);
  }, [cat, matrix]);

  useEffect(() => {
    if (!emp || !cat || !inc) { setPreview(null); return; }
    api.previewPenalty(emp, cat, inc).then(setPreview).catch(() => setPreview(null));
  }, [emp, cat, inc]);

  const meta = useMemo(() => (matrix && cat && inc ? matrix.matrix[cat][inc] : null), [matrix, cat, inc]);
  const guideLabels = { Yellow: t("pNotice"), Orange: t("pFlag"), Red: t("pAlert"), Black: t("pWarn"), Investigation: t("pSusp") };

  async function submit() {
    if (!emp) { setMsg({ type: "err", text: t("employee") + " *" }); return; }
    setSaving(true);
    setMsg(null);
    try {
      const proofB64 = proof.dataUrl ? proof.dataUrl.split(",")[1] || "" : "";
      const payload = {
        employee_name: emp, category: cat, incident: inc, comment,
        force_investigation: force,
        override_days: override >= 0 ? Number(override) : null,
        proof_image: proofB64,
      };
      const v = await api.createViolation(payload);
      toast("ok", `${t("vLogged")}: ${v.penalty_color} \u2014 ${v.deduction_days} ${t("days")}`);
      setMsg({ type: "ok", text: `${v.penalty_color} \u2014 ${v.deduction_days} ${t("days")}` });
      setComment(""); setForce(false); setOverride(-1);
      setProof({ name: "", dataUrl: "" });
    } catch (e) {
      toast("err", e.message || t("errGeneric"));
      setMsg({ type: "err", text: e.message });
    } finally {
      setSaving(false);
    }
  }

  if (!matrix) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "1fr 340px", gap: 22 }}>
        <Card>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <Skeleton w="40%" h={11} />
                <Skeleton h={40} style={{ borderRadius: 10 }} />
              </div>
            ))}
          </div>
        </Card>
        <Card><Skeleton w="60%" h={14} style={{ marginBottom: 14 }} /><Skeleton h={90} /></Card>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: S.g800, margin: 0 }}>{t("regV")}</h2>
          <p style={{ fontSize: 13, color: S.g400, marginTop: 2 }}>{ar ? "\u0623\u062F\u062E\u0644 \u0627\u0644\u062A\u0641\u0627\u0635\u064A\u0644" : "Fill in the details"}</p>
        </div>
        <BtnSec onClick={() => setGuideOpen(!guideOpen)}>{IC.info} <span>{t("pGuide")}</span></BtnSec>
      </div>

      {guideOpen && (
        <Card style={{ background: S.priL, borderColor: S.priM }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: 10 }}>
            {GUIDE.map((g) => (
              <div key={g.lv} style={{ background: S.w, borderRadius: S.r2, padding: "14px 10px", textAlign: "center", border: `1px solid ${S.g200}` }}>
                <div style={{ fontSize: 26, marginBottom: 8 }}>{g.ic}</div>
                <PenBadge level={g.lv} size="lg" lang={lang} />
                <div style={{ fontSize: 11, color: S.g400, marginTop: 6 }}>{guideLabels[g.lv]}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: S.g700, marginTop: 4 }}>{g.dd !== "\u2014" ? `${g.dd} ${t("days")}` : "\u2014"}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "1fr 340px", gap: 22 }}>
        <Card>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 20, marginBottom: 20 }}>
            <FG label={t("vCat")}>
              <select style={{ ...inp, cursor: "pointer" }} value={cat} onChange={(e) => setCat(e.target.value)}>
                {Object.keys(matrix.matrix).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </FG>
            <FG label={t("incType")}>
              <select style={{ ...inp, cursor: "pointer" }} value={inc} onChange={(e) => setInc(e.target.value)}>
                {cat && Object.keys(matrix.matrix[cat]).map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </FG>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 20, marginBottom: 20 }}>
            <FG label={`${t("employee")} *`}>
              <select style={{ ...inp, cursor: "pointer" }} value={emp} onChange={(e) => setEmp(e.target.value)}>
                <option value="">{ar ? "\u2014 \u0627\u062E\u062A\u0631 \u2014" : "\u2014 select \u2014"}</option>
                {employees.map((e) => <option key={e.id} value={e.name}>{e.name}</option>)}
              </select>
            </FG>
            <FG label={t("hrRep")}>
              <input style={{ ...inp, background: S.g50, color: S.g500 }} value={user?.name || ""} readOnly aria-readonly="true" />
            </FG>
          </div>
          <div style={{ marginBottom: 20 }}>
            <FG label={t("comments")}>
              <textarea style={{ ...inp, resize: "vertical", minHeight: 88 }} value={comment} onChange={(e) => setComment(e.target.value)} />
            </FG>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 20, marginBottom: 20 }}>
            <FG label={t("proof")}>
              <label style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: S.r2, border: `1.5px dashed ${S.g300}`, cursor: "pointer", background: S.g50, fontSize: 13, color: S.g500 }}>
                {IC.upload}
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{proof.name || (ar ? "\u0627\u062E\u062A\u0631 \u0635\u0648\u0631\u0629..." : "Choose image...")}</span>
                <input type="file" accept="image/*" onChange={onProofChange} style={{ display: "none" }} />
              </label>
              {proof.dataUrl && (
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
                  <img src={proof.dataUrl} alt="proof" style={{ width: 56, height: 56, objectFit: "cover", borderRadius: S.r2, border: `1px solid ${S.g200}` }} />
                  <button type="button" onClick={() => setProof({ name: "", dataUrl: "" })} style={{ fontSize: 11, padding: "4px 10px", borderRadius: S.r2, border: `1px solid ${S.g200}`, background: S.w, color: S.err, cursor: "pointer", fontFamily: "inherit" }}>{t("del")}</button>
                </div>
              )}
            </FG>
            <FG label={t("dedOver")}>
              <input style={inp} type="number" value={override} step="0.5" onChange={(e) => setOverride(parseFloat(e.target.value))} />
            </FG>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 16px", borderRadius: S.r2, background: S.errL, border: "1px solid rgba(220,38,38,.15)", marginBottom: 22 }}>
            <input type="checkbox" id="fi" checked={force} onChange={(e) => setForce(e.target.checked)} style={{ width: 16, height: 16, accentColor: S.err, cursor: "pointer" }} />
            <label htmlFor="fi" style={{ fontSize: 13, fontWeight: 600, color: S.err, cursor: "pointer" }}>{t("forceInv")}</label>
          </div>
          {msg && (
            <div style={{ padding: "10px 14px", borderRadius: S.r2, marginBottom: 16, fontSize: 13, fontWeight: 600, background: msg.type === "ok" ? S.okL : S.errL, color: msg.type === "ok" ? S.ok : S.err }}>
              {msg.text}
            </div>
          )}
          <BtnPri wide disabled={saving} onClick={submit}>{IC.check} <span>{saving ? "\u2026" : t("submit")}</span></BtnPri>
        </Card>

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
      </div>
    </div>
  );
}
