import { useJson } from "../lib/data";
import { Kpi, Panel } from "../components/ui";

export default function Method() {
  const { data: meta } = useJson("meta");
  if (!meta) return <div className="loading">데이터 로딩…</div>;
  const v = meta.validation, c = meta.calibration;

  return (
    <>
      <h1>방법론 · 검증 · 한계</h1>
      <p className="sub">모든 수치는 파이썬 파이프라인에서 직접 산출·검증 — 재현 가능 · LLM 미사용 · <b>예측이 아닌 경향</b></p>

      <h2 className="sec">1. 왜 두 축(News + Fed)을 합치나</h2>
      <div className="kpis">
        <Kpi eyebrow="Fed 단독 ↔ VIX" value={v.r_fed} meta={`${v.n_months}개월 (${v.period})`} />
        <Kpi eyebrow="News 단독 ↔ VIX" value={v.r_news} meta="WSJ 38,869건 기사" />
        <Kpi eyebrow="통합 ↔ VIX"
          value={<span style={{ color: "var(--accent)" }}>{v.r_combined}</span>}
          meta="z-표준화 50:50 결합 — 가장 강함 ★" />
      </div>

      <h2 className="sec">2. 신뢰성 3중 검증</h2>
      <div className="cards2">
        <Panel title="홀드아웃 (과최적 아님)">
          앞 기간으로 파라미터를 고정하고 <b>안 본 기간</b>에서 재측정:
          {v.holdout.map((h) => (
            <div key={h.split} className="cap">분할 {h.split} → 홀드아웃 <b className="num">{h.out}</b></div>
          ))}
        </Panel>
        <Panel title="블록 부트스트랩 (우연 아님)">
          95% CI <b className="num">[{v.bootstrap_ci[0]}, {v.bootstrap_ci[1]}]</b>
          <div className="cap">0 미포함 = 통계적으로 유의 (블록=12개월, 3000회)</div>
        </Panel>
        <Panel title="LOMO (단일사건 아님)">
          256개월을 하나씩 빼도 전부 <b className="num">[{v.lomo_range[0]}, {v.lomo_range[1]}]</b>
          <div className="cap">2009-03(금융위기)을 빼도 −0.543 — 2008·2020이 결과를 만들지 않음</div>
        </Panel>
        <Panel title="온도 보정 T=3.1 (확신도가 정직)">
          성명문 ECE <b className="num">{(c.statement ?? c).ece_raw} → {(c.statement ?? c).ece_calibrated}</b>
          {c.presser && <> · presser ECE <b className="num">{c.presser.ece_raw} → {c.presser.ece_calibrated}</b></>}
          <div className="cap">사람 라벨 {c.labeled_sentences ?? 143}문장(성명문150+presser150) 검증 — 한 온도값이 문어·구어 모두에서 정직(엔트로피 0.24→~0.8)</div>
        </Panel>
      </div>

      <h2 className="sec">3. 정직한 한계</h2>
      <div className="note" style={{ lineHeight: 1.8 }}>
        <b>상관 ≠ 인과, 예측 아님</b> — 신호는 "매수/매도"가 아니라 정합/괴리 <b>알림</b>.<br />
        괴리는 위기 <b>예측</b>이 아니라 위기 구간과 유의하게 <b>연관</b>된 attention signal (사후·동시 감지).<br />
        News 검증은 WSJ 단일 소스(2000–2021) — 실시간은 Marketaux 다중소스로 별도 운영.<br />
        기자회견은 2011-04 신설 이후만 존재 (그 전 회의는 성명문만) · 의사록(minutes)은 3주 지연으로 의도적 제외.
      </div>
    </>
  );
}
