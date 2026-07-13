import { useJson, fmt } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { SimpleLine } from "../components/charts";

export default function Presser() {
  const { data: presser } = useJson("presser");
  const { data: meta } = useJson("meta");
  if (!presser || !meta) return <div className="loading">데이터 로딩…</div>;
  const pf = meta.presser_finding;

  return (
    <>
      <h1>기자회견 vs 성명문</h1>
      <p className="sub">다듬어진 성명문과 라이브 Q&A(의장 발언만)의 톤 비교 — 2011~2026, 4의장 ({pf.n_meetings}회의)</p>

      <div className="kpis">
        <Kpi eyebrow="기자회견이 더 신중"
          value={<span style={{ color: "var(--accent)" }}>{Math.round(pf.pct_more_cautious * 100)}%</span>}
          meta={`${pf.n_meetings}회의 중 · 부호검정 p<10⁻¹²`} />
        <Kpi eyebrow="평균 괴리 (기자회견 − 성명문)" value={fmt(pf.mean_gap)}
          meta="일관되게 음수 = Q&A가 방어적" />
        <Kpi eyebrow="가장 큰 후퇴" value="−0.372" meta="2018-06-13 (긴축기) · Warsh 취임 −0.276" />
      </div>

      <h2 className="sec">회의별 톤 — 성명문 vs 기자회견</h2>
      <Panel cap="주황 = 성명문, 파랑 = 기자회견(의장 발언만, FinBERT T=3.1 동일 방법). 기자회견이 거의 항상 아래.">
        <SimpleLine data={presser} height={280}
          series={[
            { key: "statement", name: "성명문", color: "var(--accent)" },
            { key: "presser", name: "기자회견", color: "var(--blue)" },
          ]} />
      </Panel>

      <div className="note"><b>해석</b> — {pf.note}. 괴리가 평소(≈−0.11)보다 크게 벌어지면 "성명과 실제 스탠스 사이 긴장"의 주목 신호 (예측 아님).</div>
    </>
  );
}
