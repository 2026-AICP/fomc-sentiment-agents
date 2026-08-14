import { useJson } from "../lib/data";
import { Kpi, Panel } from "../components/ui";

export default function Method() {
  const { data: meta } = useJson("meta");
  if (!meta) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  const v = meta.validation;

  return (
    <>
      <h1>방법론과 한계</h1>
      <p className="sub">
        지수 산출 방법과 검증 결과, 그리고 한계를 설명합니다. 문장 채점에는 금융 문서로
        학습된 감성 분석 모델(FinBERT)을 사용하며, 모든 수치는 고정된 규칙으로 계산됩니다.
      </p>

      <h2 className="sec">1. 왜 연준 문서와 뉴스를 함께 보나요?</h2>
      <div className="kpis">
        <Kpi eyebrow="연준 문서만" value={v.r_fed}
          meta={`VIX와의 상관계수 · ${v.n_months}개월`} />
        <Kpi eyebrow="뉴스만" value={v.r_news}
          meta="월스트리트저널 기사 38,869건" />
        <Kpi eyebrow="함께 볼 때"
          value={<span style={{ color: "var(--accent)" }}>{v.r_combined}</span>}
          meta="같은 비중으로 결합했을 때 가장 강합니다" />
      </div>
      <div className="note">
        상관계수는 −1에서 +1 사이의 값으로, 0에서 멀수록 두 지표가 함께 움직이는 정도가
        강하다는 뜻입니다. 감성지수는 시장 불안(VIX)과 반대 방향으로 움직입니다.
      </div>

      <h2 className="sec">2. 결과가 우연은 아닌가요?</h2>
      <div className="cards2">
        <Panel title="기간을 나눠 확인했습니다">
          앞 기간의 자료로 기준을 정한 뒤, 보지 않은 뒤 기간에서 다시 측정해도 상관이
          유지됩니다.
          {v.holdout.map((h) => (
            <div key={h.split} className="cap">{h.split}년 이후 자료에서 다시 측정한 값 <b className="num">{h.out}</b></div>
          ))}
        </Panel>
        <Panel title="무작위로 다시 뽑아 확인했습니다">
          자료를 12개월 단위로 3,000번 다시 뽑아 계산해도, 95% 범위
          <b className="num"> [{v.bootstrap_ci[0]}, {v.bootstrap_ci[1]}]</b>가 0을 포함하지
          않습니다.
        </Panel>
        <Panel title="특정 시기를 빼도 확인했습니다">
          256개월을 한 달씩 빼며 다시 계산해도 결과가
          <b className="num"> [{v.lomo_range[0]}, {v.lomo_range[1]}]</b> 범위를 벗어나지
          않습니다. 2008년 금융위기나 2020년을 빼도 마찬가지입니다.
        </Panel>
      </div>

      <h2 className="sec">3. 한계</h2>
      <div className="note" style={{ lineHeight: 1.8 }}>
        지수와 시장의 관계는 상관관계이며 인과관계가 아닙니다. 신호는 살펴볼 시점을 알리는
        용도이고, 매수·매도 판단의 근거가 아닙니다.<br />
        과거 검증에는 월스트리트저널 기사(2000~2021년)를 사용했고, 실시간 수집은 여러 매체를
        대상으로 하므로 두 자료의 구성이 다릅니다.<br />
        기자회견은 2011년 4월부터 도입되어 그 이전 회의에는 없습니다. 회의록은 회의 약 3주
        뒤에 공개되므로, 최근 회의는 공개 전까지 회의록 없이 집계됩니다.
      </div>
    </>
  );
}
