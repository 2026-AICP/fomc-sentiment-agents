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
      <h1>회의록</h1>
      <p className="sub">
        회의 약 3주 뒤에 공개되는 상세 논의 기록입니다. 여섯 개 표준 섹션으로 나눠
        성명문·기자회견과 같은 기준으로 채점합니다. 지금까지 {mf.n_meetings}회의를
        분석했습니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="회의록이 성명문보다 신중"
          value={<span style={{ color: "var(--accent)" }}>{Math.round(mf.pct_more_cautious * 100)}%</span>}
          meta={`전체 ${mf.n_meetings}회 중 ${Math.round(mf.pct_more_cautious * mf.n_meetings)}회`} />
        <Kpi eyebrow="평균 차이 (회의록 − 성명문)" value={fmt(mf.mean_gap)}
          meta="음수는 내부 논의가 더 조심스럽다는 뜻입니다" />
        <Kpi eyebrow="문서별 평균"
          value={`${fmt(mf.axis_means.statement)} · ${fmt(mf.axis_means.minutes)} · ${fmt(mf.axis_means.presser)}`}
          meta="성명문, 회의록, 기자회견 순. 공식 문서일수록 낙관적입니다" />
      </div>

      <h2 className="sec">회의별 톤 비교</h2>
      <Panel cap="주황 선은 성명문, 파랑 선은 회의록입니다. 같은 회의라도 내부 논의 기록이 대체로 더 신중합니다.">
        <SimpleLine data={minutes} height={280}
          series={[
            { key: "statement", name: "성명문", color: "var(--accent)" },
            { key: "minutes", name: "회의록", color: "var(--blue)" },
          ]} />
      </Panel>

      <h2 className="sec">섹션별 평균 톤</h2>
      <Panel cap="같은 회의록 안에서도 섹션마다 어조가 다릅니다. 전체 지수 하나로는 보이지 않는 차이입니다.">
        <CompareBars data={secAvg} x="code" y="tone"
          colorBy={(d) => (d.tone >= 0 ? "var(--accent)" : "var(--blue)")} />
        <div className="cap" style={{ marginTop: 8, lineHeight: 1.9 }}>
          {secAvg.map((s) => (
            <div key={s.code}>
              <b className="num">{s.code}</b> {s.name} · 평균 <b className="num">{fmt(s.tone)}</b>
              <span style={{ opacity: 0.6 }}> ({s.n}회)</span>
            </div>
          ))}
        </div>
      </Panel>

      {recent.length > 0 && (
        <>
          <h2 className="sec">자료 수집 현황 (최근 회의)</h2>
          <Panel cap="성명문은 회의 당일, 기자회견 원문은 며칠 뒤, 회의록은 약 3주 뒤에 공개됩니다. 공개되는 대로 자동으로 반영됩니다.">
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
        세 문서의 상관계수는 성명문과 회의록이 <b className="num">{mf.axis_corr.stmt_minutes}</b>,
        회의록과 기자회견이 <b className="num">{mf.axis_corr.minutes_presser}</b>,
        성명문과 기자회견이 <b className="num">{mf.axis_corr.stmt_presser}</b>입니다.
        서로 완전히 겹치지 않는 정보를 담고 있어, 이 사이트는 세 문서를 나눠서 보여줍니다.
      </div>
    </>
  );
}
