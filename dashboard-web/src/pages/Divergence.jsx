import { useJson } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { CompareBars } from "../components/charts";

const CASES = [
  { icon: "🦠", date: "2020-03-15", ctx: "COVID 긴급 제로금리", fed: "＋0.10 긍정", mkt: "−12.0%" },
  { icon: "🏦", date: "2008-10-07", ctx: "금융위기 공조 인하", fed: "＋0.11 긍정", mkt: "−5.7%" },
  { icon: "💻", date: "2001-01-03", ctx: "닷컴 긴급인하 → 안도 랠리", fed: "−0.08 부정", mkt: "＋5.0%" },
  { icon: "📉", date: "2011-08-09", ctx: "신용강등 후 저금리 약속", fed: "−0.05 부정", mkt: "＋4.7%" },
];

export default function Divergence() {
  const { data: meta } = useJson("meta");
  if (!meta) return <div className="loading">데이터 로딩…</div>;
  const dv = meta.divergence;
  const bars = [
    { name: "평소", rate: Math.round(dv.rate_normal * 100) },
    { name: "위기 구간", rate: Math.round(dv.rate_crisis * 100) },
  ];

  return (
    <>
      <h1>괴리 신호 — "지금 자세히 봐야 할 때"</h1>
      <p className="sub">괴리는 위기를 <b>예측</b>하는 게 아니라, <b>추가 검토가 필요한 시점</b>을 짚어주는 attention signal 입니다.</p>

      <Panel title="괴리(divergence)란?">
        연준의 <b>톤</b>과 시장의 <b>반응</b>이 서로 <b style={{ color: "var(--bad)" }}>엇갈린</b> 회의입니다.
        <div className="cap">예 · 연준은 안심시키는데 시장은 급락(2020 COVID) / 연준은 우려하는데 시장은 안도 랠리(2001 닷컴)</div>
      </Panel>

      <h2 className="sec">괴리가 뜨면? — 위기 구간일 확률이 평소의 {dv.ratio}배</h2>
      <div className="kpis">
        <Kpi eyebrow="평소 (위기 아닐 때)"
          value={<span style={{ color: "var(--muted)" }}>{Math.round(dv.rate_normal * 100)}%</span>}
          meta={`회의의 ${Math.round(dv.rate_normal * 100)}%에서만 괴리`} />
        <Kpi eyebrow="위기 구간에서는"
          value={<span style={{ color: "var(--bad)" }}>{Math.round(dv.rate_crisis * 100)}%</span>}
          meta={`괴리가 ${dv.ratio}배 더 자주`} pill={`${dv.ratio}×`} pillColor="var(--bad)" />
        <Kpi eyebrow="우연일 가능성"
          value={<span style={{ color: "var(--good)" }}>{(dv.p_permutation * 100).toFixed(1)}%</span>}
          meta={`permutation p=${dv.p_permutation} · 유의`} />
      </div>

      <Panel cap="금융스트레스 구간(NBER 침체 + 알려진 위기)에 괴리가 우연보다 2.4배 몰림. 위기 구간은 신호와 독립으로 사전 정의(순환논리 회피). 검정: permutation p=0.001 · Fisher p<0.001 · analysis/validate_divergence.py">
        <CompareBars data={bars} x="name" y="rate"
          colorBy={(d) => (d.name === "위기 구간" ? "var(--bad)" : "var(--muted)")} />
      </Panel>

      <h2 className="sec">대표 사례 — 연준 ≠ 시장</h2>
      <div className="cards2">
        {CASES.map((c) => (
          <div className="panel" key={c.date} style={{ marginTop: 0 }}>
            <div style={{ fontWeight: 700 }}>{c.icon} {c.date} · {c.ctx}</div>
            <div className="cap">연준 톤 {c.fed} ↔ 시장 당일 {c.mkt}</div>
          </div>
        ))}
      </div>

      <div className="note"><b>주의</b> — {dv.note}. 상관 ≠ 인과, 사후·동시 감지.</div>
    </>
  );
}
