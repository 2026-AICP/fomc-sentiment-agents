import { useJson, fmt } from "../lib/data";
import { Kpi, Panel, Pill } from "../components/ui";
import { SimpleLine, CompareBars } from "../components/charts";

// 섹션 코드 → 사람이 읽는 이름 (회의록 표준 6섹션)
const SEC_NAME = {
  DFMOMO: "금융시장·공개시장조작",
  SRES: "경제상황 검토(스태프)",
  SRFS: "금융상황 검토(스태프)",
  SEO: "경제전망(스태프)",
  PVCCEO: "위원 견해",
  CPA: "정책 결정",
};

export default function Minutes() {
  const { data: minutes } = useJson("minutes");
  const { data: axis } = useJson("axis_status");
  const { data: meta } = useJson("meta");
  if (!minutes || !meta) return <div className="loading">데이터 로딩…</div>;
  const mf = meta.minutes_finding;

  // 섹션별 평균 — 전 회의 평균(있는 회의만)
  const secAvg = Object.keys(SEC_NAME).map((code) => {
    const vals = minutes.map((m) => m.sections?.[code]).filter((v) => v != null);
    return {
      code,
      name: SEC_NAME[code],
      tone: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null,
      n: vals.length,
    };
  }).filter((s) => s.tone != null);

  // 최근 회의의 축 완성 상태 (아직 안 온 축이 무엇인지)
  const recent = (axis || []).slice(-6).reverse();

  return (
    <>
      <h1>회의록 (Minutes)</h1>
      <p className="sub">
        회의 <b>3주 후</b> 공개되는 상세 의사록 — 6개 표준 섹션으로 나눠 성명문·기자회견과
        <b> 같은 방식</b>(FinBERT · 확신도 가중)으로 점수화 ({mf.n_meetings}회의)
      </p>

      <div className="kpis">
        <Kpi eyebrow="회의록이 성명문보다 신중"
          value={<span style={{ color: "var(--accent)" }}>{Math.round(mf.pct_more_cautious * 100)}%</span>}
          meta={`${mf.n_meetings}회의 중 · 부호검정 p<10⁻¹³`} />
        <Kpi eyebrow="평균 괴리 (회의록 − 성명문)" value={fmt(mf.mean_gap)}
          meta="음수 = 내부 논의가 더 조심스러움" />
        <Kpi eyebrow="3축 평균 톤"
          value={`${fmt(mf.axis_means.statement)} → ${fmt(mf.axis_means.minutes)} → ${fmt(mf.axis_means.presser)}`}
          meta="성명문 → 회의록 → 기자회견 (계단식 하락)" />
      </div>

      <h2 className="sec">회의별 톤 — 성명문 vs 회의록</h2>
      <Panel cap="주황 = 성명문(대외 공식), 파랑 = 회의록(내부 논의 요약). 회의록이 대체로 아래.">
        <SimpleLine data={minutes} height={280}
          series={[
            { key: "statement", name: "성명문", color: "var(--accent)" },
            { key: "minutes", name: "회의록", color: "var(--blue)" },
          ]} />
      </Panel>

      <h2 className="sec">섹션별 평균 톤</h2>
      <Panel cap="회의록 안에서도 섹션마다 톤이 다르다 — 전체 지수 하나로는 보이지 않는 내부 분화.">
        <CompareBars data={secAvg} x="code" y="tone"
          colorBy={(d) => (d.tone >= 0 ? "var(--accent)" : "var(--blue)")} />
        <div className="cap" style={{ marginTop: 8, lineHeight: 1.9 }}>
          {secAvg.map((s) => (
            <div key={s.code}>
              <b className="num">{s.code}</b> {s.name} — 평균 <b className="num">{fmt(s.tone)}</b>
              <span style={{ opacity: 0.6 }}> ({s.n}회의)</span>
            </div>
          ))}
        </div>
      </Panel>

      {recent.length > 0 && (
        <>
          <h2 className="sec">축 도착 현황 (최근 회의)</h2>
          <Panel cap="세 축은 도착 시각이 다르다 — 성명문(당일) · 기자회견(며칠 후) · 회의록(3주 후). 자동화가 매일 미완성 회의를 다시 확인해 채운다.">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {recent.map((r) => (
                <div key={r.date} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="num" style={{ minWidth: 92 }}>{r.date}</span>
                  <Pill color={r.statement ? "var(--accent)" : "var(--muted)"}>
                    {r.statement ? "성명문 ✓" : "성명문 —"}
                  </Pill>
                  <Pill color={r.minutes ? "var(--blue)" : "var(--muted)"}>
                    {r.minutes ? "회의록 ✓" : "회의록 대기"}
                  </Pill>
                  {r.presser !== null && (
                    <Pill color={r.presser ? "var(--green, var(--blue))" : "var(--muted)"}>
                      {r.presser ? "기자회견 ✓" : "기자회견 대기"}
                    </Pill>
                  )}
                  <span className="cap">{r.n_axes}/{r.expected}</span>
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}

      <div className="note">
        <b>해석</b> — {mf.note}.<br />
        축 상관이 <b className="num">{mf.axis_corr.stmt_minutes}</b>(성명문↔회의록) ·
        <b className="num"> {mf.axis_corr.minutes_presser}</b>(회의록↔기자회견) ·
        <b className="num"> {mf.axis_corr.stmt_presser}</b>(성명문↔기자회견)로,
        완전히 겹치지 않는다 = 세 축을 <b>따로 보는 것이 정보량이 크다</b>. (예측 아님 · 경향)
      </div>
    </>
  );
}
