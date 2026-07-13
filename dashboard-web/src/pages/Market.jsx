import { useJson, fmt } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { IndexArea, SimpleLine } from "../components/charts";

export default function Market() {
  const { data: market } = useJson("market");
  if (!market) return <div className="loading">데이터 로딩…</div>;
  if (!market.length) return <div className="loading">시장 데이터 없음 — collect_market을 먼저 실행하세요.</div>;

  const last = market[market.length - 1];
  const inverted = last.spread != null && last.spread < 0;

  return (
    <>
      <h1>시장 축</h1>
      <p className="sub">S&amp;P 500 · VIX · 국채금리(2Y/10Y) — 감성 지수가 비교·검증되는 대상 (2000~현재, 주단위 표시)</p>

      <div className="kpis">
        <Kpi eyebrow="S&P 500" value={last.spx?.toLocaleString() ?? "—"}
          meta={`${last.date} · 당일 ${fmt(last.spx_ret, 2)}%`} />
        <Kpi eyebrow="VIX (공포지수)" value={fmt(last.vix, 2, false)}
          meta={`변화 ${fmt(last.vix_chg, 2)}`} />
        <Kpi eyebrow="2년물 (정책 민감)" value={`${fmt(last.ust2y, 2, false)}%`}
          meta="신호 D(톤-금리)의 기준 금리" />
        <Kpi eyebrow="장단기 스프레드 (10Y−2Y)"
          value={<span style={{ color: inverted ? "var(--bad)" : "var(--good)" }}>{fmt(last.spread, 2)}%p</span>}
          meta={inverted ? "역전 — 전통적 침체 선행 신호" : "정상"} />
      </div>

      <h2 className="sec">VIX — 감성 검증의 기준 (통합↔VIX −0.534)</h2>
      <Panel cap="시장 공포·스트레스 게이지. 정상성(평균회귀)이라 감성과의 레벨 상관에 적합 — 방법론·한계 참조">
        <IndexArea data={market} y="vix" color="var(--bad)" />
      </Panel>

      <h2 className="sec">S&amp;P 500 — 괴리 신호(B)의 시장 반응</h2>
      <Panel cap="괴리 신호는 톤 vs 'S&P 당일 수익률' 로 판정 (레벨이 아닌 수익률 — 추세 허위상관 회피)">
        <IndexArea data={market} y="spx" color="var(--good)" />
      </Panel>

      <h2 className="sec">국채금리 — 2Y(정책 기대) vs 10Y</h2>
      <Panel cap="2년물은 Fed 정책에 민감해 신호 D(톤-금리 이탈)의 대리 변수로 사용">
        <SimpleLine data={market} height={260}
          series={[
            { key: "ust2y", name: "2년물", color: "var(--accent)" },
            { key: "ust10y", name: "10년물", color: "var(--blue)" },
          ]} />
      </Panel>

      <h2 className="sec">장단기 스프레드 (10Y − 2Y)</h2>
      <Panel cap="음수(0 아래) = 장단기 역전 → 전통적 침체 선행 신호">
        <IndexArea data={market} y="spread" color="var(--warn)" height={220} />
      </Panel>
    </>
  );
}
