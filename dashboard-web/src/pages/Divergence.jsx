import { useJson } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { CompareBars } from "../components/charts";

const CASES = [
  { date: "2020-03-15", ctx: "코로나 긴급 제로금리", fed: "+0.10 (안심)", mkt: "주가 −12.0%" },
  { date: "2008-10-07", ctx: "금융위기 공조 금리 인하", fed: "+0.11 (안심)", mkt: "주가 −5.7%" },
  { date: "2001-01-03", ctx: "닷컴 붕괴 긴급 인하", fed: "−0.08 (우려)", mkt: "주가 +5.0%" },
  { date: "2011-08-09", ctx: "미국 신용등급 강등 직후", fed: "−0.05 (우려)", mkt: "주가 +4.7%" },
];

export default function Divergence({ embedded = false }) {
  const { data: meta } = useJson("meta");
  if (!meta) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  const dv = meta.divergence;
  const bars = [
    { name: "평소", rate: Math.round(dv.rate_normal * 100) },
    { name: "위기 구간", rate: Math.round(dv.rate_crisis * 100) },
  ];

  return (
    <>
      {embedded ? (
        <h2 className="sec">대표 괴리 사례</h2>
      ) : (
        <h1>괴리 신호 검증</h1>
      )}
      {!embedded && (
        <p className="sub">
          연준의 어조와 시장 반응이 서로 반대로 움직인 회의를 괴리라고 부릅니다.
          위기를 예측하는 지표가 아니라, 자세히 살펴볼 시점을 표시하는 알림입니다.
        </p>
      )}

      <Panel title="괴리란 무엇인가요?">
        연준의 <b>어조</b>와 시장의 <b>반응</b>이 서로 <b style={{ color: "var(--dn)" }}>엇갈린</b> 회의입니다.
        <div className="cap">
          2020년 3월에는 연준이 시장을 안심시켰지만 주가는 급락했고, 2001년 1월에는 연준이
          우려를 표했지만 주가는 반등했습니다.
        </div>
      </Panel>

      <h2 className="sec">괴리는 위기 구간에서 더 자주 나타납니다</h2>
      <div className="kpis">
        <Kpi eyebrow="평소"
          value={<span style={{ color: "var(--muted)" }}>{Math.round(dv.rate_normal * 100)}%</span>}
          meta="회의 중 괴리가 나타난 비율" />
        <Kpi eyebrow="위기 구간"
          value={<span style={{ color: "var(--dn)" }}>{Math.round(dv.rate_crisis * 100)}%</span>}
          meta={`평소의 ${dv.ratio}배입니다`} pill={`${dv.ratio}배`} pillColor="var(--dn)" />
        <Kpi eyebrow="우연일 가능성"
          value={<span style={{ color: "var(--up)" }}>{(dv.p_permutation * 100).toFixed(1)}%</span>}
          meta="무작위로는 설명되지 않는 수준입니다" />
      </div>

      <Panel cap="위기 구간은 신호와 무관하게 미리 정한 경기 침체·위기 시기입니다. 이 구간에서 괴리가 나타난 비율이 평소의 2.4배였습니다.">
        <CompareBars data={bars} x="name" y="rate"
          colorBy={(d) => (d.name === "위기 구간" ? "var(--dn)" : "var(--muted)")} />
      </Panel>

      <h2 className="sec">대표 사례</h2>
      <div className="cards2">
        {CASES.map((c) => (
          <div className="panel" key={c.date} style={{ marginTop: 0 }}>
            <div style={{ fontWeight: 700 }}>{c.date} · {c.ctx}</div>
            <div className="cap">연준 어조 {c.fed} · 당일 {c.mkt}</div>
          </div>
        ))}
      </div>

      <div className="note">
        괴리는 위기 구간과 함께 나타나는 경향이 있다는 통계적 사실이며, 인과관계나 예측력을
        뜻하지 않습니다.
      </div>
    </>
  );
}
