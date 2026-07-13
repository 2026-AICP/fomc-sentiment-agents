import { useJson, fmt, GRADE_COLOR } from "../lib/data";
import { Pill } from "../components/ui";

// 신호 정의 — analysis/signals.py 의 규칙을 사람 말로 (θ는 데이터 기반 보정, signal_calibration.md)
const SIGNAL_DEFS = [
  {
    code: "A", name: "tone_shift · 톤 급변", color: "var(--warn)",
    what: "직전 회의 대비 톤이 크게 변함",
    why: "연준 스탠스가 바뀌는 순간 — 시장이 다시 읽어야 할 때",
  },
  {
    code: "B", name: "divergence · 괴리 ⭐", color: "var(--bad)",
    what: "톤과 당일 시장(S&P) 방향이 서로 반대 (둘 다 충분히 클 때)",
    why: "연준 인식 ≠ 시장 인식 — 위기 예측이 아니라 추가 검토가 필요한 attention signal (위기 구간과 2.4× 연관)",
  },
  {
    code: "C", name: "tone_vs_vix · 톤-공포 이례", color: "var(--blue)",
    what: "평소의 음(−)의 동행(톤↑→VIX↓)이 깨짐",
    why: "말과 공포가 같이 오르는 이례적 순간",
  },
  {
    code: "D", name: "tone_vs_rate · 톤-금리 이탈", color: "var(--accent)",
    what: "톤과 2년물 금리 변화의 동행이 깨짐",
    why: "2년물은 정책 기대에 민감 — 시장의 정책 해석이 연준 톤과 어긋남",
  },
];

const GRADES = [
  { g: "🔴 경고", d: "강한 괴리 — 톤·시장 모두 크게 어긋남" },
  { g: "⚠️ 주의", d: "신호 1개 이상 발동 — 들여다볼 것" },
  { g: "🟢 정합", d: "톤과 시장이 같은 방향 — 특이 없음" },
  { g: "⚪ 중립", d: "신호 판단에 충분한 크기 아님" },
];

export default function Signals() {
  const { data: alerts } = useJson("alerts");
  if (!alerts) return <div className="loading">데이터 로딩…</div>;

  return (
    <>
      <h1>신호</h1>
      <p className="sub">검증된 analysis.signals 엔진 — <b>예측이 아닌 알림</b> ("사라/팔아라"가 아니라 "정합/괴리" 표시)</p>

      <h2 className="sec" style={{ marginTop: 8 }}>네 가지 규칙</h2>
      <div className="cards2">
        {SIGNAL_DEFS.map((s) => (
          <div className="panel" key={s.code} style={{ marginTop: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span className="pill" style={{ background: `color-mix(in srgb, ${s.color} 15%, transparent)`, color: s.color, fontSize: 13 }}>{s.code}</span>
              <b>{s.name}</b>
            </div>
            <div style={{ fontSize: 13.5 }}>{s.what}</div>
            <div className="cap">{s.why}</div>
          </div>
        ))}
      </div>
      <div className="note">
        임계값(θ)은 자의가 아니라 <b>실제 분포(분위수) 기반으로 보정</b> — <span className="num">docs/signal_calibration.md</span> · 결과 최적화 아님(과최적 회피)
      </div>

      <h2 className="sec">등급 읽는 법</h2>
      <div className="kpis">
        {GRADES.map((x) => (
          <div className="kpi" key={x.g}>
            <div className="big" style={{ fontSize: 20 }}>{x.g}</div>
            <div className="mt">{x.d}</div>
          </div>
        ))}
      </div>

      <h2 className="sec">회의별 신호 (전체 {alerts.length}건, 최신순)</h2>
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
