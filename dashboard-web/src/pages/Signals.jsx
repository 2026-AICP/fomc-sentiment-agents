import { useJson, fmt, GRADE_COLOR } from "../lib/data";
import { Pill } from "../components/ui";

export default function Signals() {
  const { data: alerts } = useJson("alerts");
  if (!alerts) return <div className="loading">데이터 로딩…</div>;

  return (
    <>
      <h1>신호</h1>
      <p className="sub">규칙 A(톤급변) · B(괴리) · C(톤-VIX) · D(톤-2Y) — 검증된 analysis.signals 엔진 · 예측 아닌 알림</p>
      {alerts.slice().reverse().map((a) => (
        <div className="alert-row" key={a.date}>
          <div>
            <div className="d1">{a.date} — {a.detail || "특이신호 없음"}</div>
            <div className="d2">톤 {fmt(a.tone)} · 시장반응 {fmt(a.reaction, 2)}% · 발동 [{a.fired.join(", ") || "—"}]</div>
          </div>
          <Pill color={GRADE_COLOR[a.grade]}>{a.grade}</Pill>
        </div>
      ))}
    </>
  );
}
