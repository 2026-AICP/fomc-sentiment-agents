import { useJson, fmt } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { IndexArea, SimpleLine, DualLine } from "../components/charts";

export default function Market() {
  const { data: market } = useJson("market");
  const { data: vs } = useJson("sentiment_vs_market");
  if (!market) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  if (!market.length) return <div className="loading">아직 수집된 시장 데이터가 없습니다.</div>;

  const last = market[market.length - 1];
  const inverted = last.spread != null && last.spread < 0;

  return (
    <>
      <h1>시장지표</h1>
      <p className="sub">
        감성지수와 비교하는 주요 시장 지표입니다. 2000년 이후 자료를 주 단위로 표시합니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="S&P 500" value={last.spx?.toLocaleString() ?? "—"}
          meta={`${last.date} · 당일 ${fmt(last.spx_ret, 2)}%`} />
        <Kpi eyebrow="VIX 변동성지수" value={fmt(last.vix, 2, false)}
          meta={`전일 대비 ${fmt(last.vix_chg, 2)}`} />
        <Kpi eyebrow="미 국채 2년" value={`${fmt(last.ust2y, 2, false)}%`}
          meta="정책 기대를 민감하게 반영합니다" />
        <Kpi eyebrow="장단기 금리차 (10년−2년)"
          value={<span style={{ color: inverted ? "var(--dn)" : "var(--up)" }}>{fmt(last.spread, 2)}%p</span>}
          meta={inverted ? "장단기 금리가 역전된 상태입니다" : "정상 범위입니다"} />
      </div>

      <h2 className="sec">감성지수와 VIX</h2>
      {vs?.series ? (
        <Panel cap={`주황 선은 통합 감성지수, 파랑 선은 VIX입니다. 감성이 낮아질 때 변동성이 오르는 반대 방향의 관계가 나타나며, ${vs.n_months}개월 동안의 상관계수는 ${vs.r}입니다. 검증 과정은 방법론 페이지에서 설명합니다.`}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <b>통합 감성지수와 VIX (월별)</b>
          <span className="pill" style={{ background: "color-mix(in srgb, var(--accent) 15%, transparent)", color: "var(--accent)", fontSize: 13 }}>상관계수 {vs.r}</span>
        </div>
        <DualLine data={vs.series}
          left={{ key: "combined", name: "통합 감성지수", color: "var(--accent)" }}
          right={{ key: "vix", name: "VIX", color: "var(--blue)" }} />
        </Panel>
      ) : (
        <div className="note">감성지수와 시장의 비교 자료가 아직 준비되지 않았습니다.</div>
      )}

      <h2 className="sec">VIX 변동성지수</h2>
      <Panel cap="시장의 불안 수준을 나타내는 지표입니다. 장기 추세 없이 일정 범위에서 움직여, 감성지수와 수준을 직접 비교하는 기준으로 적합합니다.">
        <IndexArea data={market} y="vix" color="var(--dn)" />
      </Panel>

      <h2 className="sec">S&P 500</h2>
      <Panel cap="엇갈림 신호는 지수의 수준이 아니라 발표 당일의 수익률과 어조를 비교해 판정합니다.">
        <IndexArea data={market} y="spx" color="var(--up)" />
      </Panel>

      <h2 className="sec">미 국채 금리 (2년·10년)</h2>
      <Panel cap="2년물은 정책 기대를, 10년물은 장기 경기 전망을 주로 반영합니다.">
        <SimpleLine data={market} height={260}
          series={[
            { key: "ust2y", name: "2년물", color: "var(--accent)" },
            { key: "ust10y", name: "10년물", color: "var(--blue)" },
          ]} />
      </Panel>

      <h2 className="sec">장단기 금리차 (10년 − 2년)</h2>
      <Panel cap="0 아래로 내려가면 장단기 금리 역전으로, 과거 경기 침체에 앞서 자주 나타났습니다.">
        <IndexArea data={market} y="spread" color="var(--warn)" height={220} />
      </Panel>
    </>
  );
}
