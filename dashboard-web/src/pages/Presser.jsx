import { useJson, fmt } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { SimpleLine } from "../components/charts";

export default function Presser() {
  const { data: presser } = useJson("presser");
  const { data: meta } = useJson("meta");
  if (!presser || !meta) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  const pf = meta.presser_finding;

  return (
    <>
      <h1>기자회견</h1>
      <p className="sub">
        정제된 성명문과 의장의 즉석 질의응답의 어조를 비교합니다. 기자회견은 2011년에
        도입되어 지금까지 {pf.n_meetings}회 열렸습니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="기자회견이 성명문보다 신중"
          value={<span style={{ color: "var(--accent)" }}>{Math.round(pf.pct_more_cautious * 100)}%</span>}
          meta={`전체 ${pf.n_meetings}회 중 ${Math.round(pf.pct_more_cautious * pf.n_meetings)}회`} />
        <Kpi eyebrow="평균 차이 (기자회견 − 성명문)" value={fmt(pf.mean_gap)}
          meta="음수는 질의응답이 더 신중하다는 뜻입니다" />
        <Kpi eyebrow="차이가 가장 컸던 회의" value="−0.501"
          meta="2018년 9월 26일, 금리 인상기" />
      </div>

      <h2 className="sec">회의별 톤 비교</h2>
      <Panel cap="주황 선은 성명문, 파랑 선은 기자회견입니다. 같은 회의라도 즉석 답변이 거의 항상 더 신중합니다.">
        <SimpleLine data={presser} height={280}
          series={[
            { key: "statement", name: "성명문", color: "var(--accent)" },
            { key: "presser", name: "기자회견", color: "var(--blue)" },
          ]} />
      </Panel>

      <div className="note">
        준비된 발표문일수록 어조가 낙관적이고, 즉석 답변일수록 신중해지는 경향이
        일관되게 나타납니다. 두 어조의 차이가 평소보다 크게 벌어진 회의는 발표문과 실제
        스탠스가 달랐을 가능성이 있어 살펴볼 만합니다.
      </div>
    </>
  );
}
