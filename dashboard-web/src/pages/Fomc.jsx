import { useState } from "react";
import { useJson, fmt } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { IndexArea, SimpleLine } from "../components/charts";

const C = { statement: "#f9812f", minutes: "#4a90e2", presser: "#55b892" };

/** 전체 — 세 문서 톤 오버레이 + 문서별 평균 + 해석 */
function AllDocs() {
  const { data: meetings } = useJson("meetings");
  const { data: minutes } = useJson("minutes");
  const { data: presser } = useJson("presser");
  const { data: meta } = useJson("meta");
  if (!meetings || !minutes || !presser)
    return <div className="loading">데이터를 불러오는 중입니다.</div>;

  const mn = Object.fromEntries(minutes.map((r) => [r.date, r.minutes]));
  const pr = Object.fromEntries(presser.map((r) => [r.date, r.presser]));
  const rows = meetings.map((m) => ({
    date: m.date, statement: m.tone,
    minutes: mn[m.date] ?? null, presser: pr[m.date] ?? null,
  }));

  const avg = meta?.minutes_finding?.axis_means || {};
  const corr = meta?.axis_corr || {};
  const rr = (v) => (v == null ? "—" : fmt(v, 2, false));

  return (
    <>
      <h1>FOMC 문서 전체</h1>
      <p className="sub">
        연준이 한 회의를 두고 내는 세 문서 — 성명문(당일 공식 발표), 기자회견(당일
        즉석 질의응답), 회의록(3주 뒤 상세 기록) — 의 어조를 같은 기준으로 나란히 봅니다.
      </p>

      <div style={{ display: "flex", gap: 14, margin: "0 0 6px 2px", fontSize: 13 }}>
        {[["성명문", C.statement], ["회의록", C.minutes], ["기자회견", C.presser]].map(([l, c]) => (
          <span key={l} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 14, height: 3, background: c, borderRadius: 2 }} />
            <span style={{ color: "var(--muted)" }}>{l}</span>
          </span>
        ))}
      </div>
      <Panel cap="회의일 기준. 기자회견은 2011년 도입 후 2019년 전까지는 분기(SEP) 회의에만 있어 사이가 벌어집니다.">
        <SimpleLine data={rows} height={300} series={[
          { key: "statement", name: "성명문", color: C.statement, width: 2.2 },
          { key: "minutes", name: "회의록", color: C.minutes, connectNulls: true },
          { key: "presser", name: "기자회견", color: C.presser, connectNulls: true },
        ]} />
      </Panel>

      <h2 className="sec">문서별 평균 톤</h2>
      <div className="kpis">
        <Kpi eyebrow="성명문" value={<span style={{ color: C.statement }}>{fmt(avg.statement ?? 0.185)}</span>}
          meta="공식 발표문 — 가장 낙관적" />
        <Kpi eyebrow="회의록" value={<span style={{ color: C.minutes }}>{fmt(avg.minutes ?? 0.088)}</span>}
          meta="내부 논의 기록" />
        <Kpi eyebrow="기자회견" value={<span style={{ color: C.presser }}>{fmt(avg.presser ?? 0.056)}</span>}
          meta="즉석 질의응답 — 가장 신중" />
      </div>

      <div className="note" style={{ lineHeight: 1.8 }}>
        <b>공식 문서일수록 어조가 낙관적입니다.</b> 다듬어진 발표문(성명문)이 가장 높고,
        내부 논의(회의록), 즉석 답변(기자회견) 순으로 낮아집니다. 전체 회의의 약 72%에서
        성명문 어조가 낙관(양수)이고 2008·2020년 위기 성명문조차 양수였습니다 — 그래서
        각 문서의 톤은 절대값이 아니라 <b>그 문서의 평소 수준 대비</b>로 읽으며, 통합지수도
        문서별로 표준화한 뒤 같은 비중(1:1:1)으로 합칩니다.
        {corr.stmt_minutes != null && (
          <> 세 문서의 상관은 성명문·회의록 {rr(corr.stmt_minutes)}, 성명문·기자회견{" "}
          {rr(corr.stmt_presser)}, 회의록·기자회견 {rr(corr.minutes_presser)} — 관련은
          있지만 겹치지 않는 정보를 담고 있어 셋을 나눠 측정합니다.</>
        )}
      </div>
    </>
  );
}

/** 개별 문서 — 해당 지수 그래프만 */
function DocChart({ title, sub, data, y, color, cap }) {
  if (!data) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  return (
    <>
      <h1>{title}</h1>
      <p className="sub">{sub}</p>
      <Panel cap={cap}>
        <IndexArea data={data} y={y} color={color} height={300} />
      </Panel>
    </>
  );
}

function Statement() {
  const { data: meetings } = useJson("meetings");
  return <DocChart title="성명문" data={meetings} y="tone" color={C.statement}
    sub="FOMC가 회의 당일 발표하는 공식 결정문 — 2000년 이후 전 회의(221건)."
    cap="문장 단위로 채점한 뒤 확신이 높은 문장에 더 큰 비중을 두어 평균했습니다." />;
}

function MinutesChart() {
  const { data: minutes } = useJson("minutes");
  return <DocChart title="회의록" data={minutes} y="minutes" color={C.minutes}
    sub="회의 약 3주 뒤 공개되는 상세 논의 기록 — 214건, 여섯 개 표준 섹션을 같은 기준으로 채점."
    cap="회의록은 공개일이 회의 3주 뒤이므로 최근 회의는 값이 늦게 채워집니다." />;
}

function PresserChart() {
  const { data: presser } = useJson("presser");
  return <DocChart title="기자회견" data={presser} y="presser" color={C.presser}
    sub="의장 기자회견 트랜스크립트 — 2011년 도입, 93건. 정제된 발표문과 달리 즉석 답변의 어조."
    cap="2019년 전에는 분기(SEP) 회의에만 열려 값이 드문드문합니다." />;
}

const SUB = [
  { key: "all", label: "전체", el: <AllDocs /> },
  { key: "statement", label: "성명문", el: <Statement /> },
  { key: "minutes", label: "회의록", el: <MinutesChart /> },
  { key: "presser", label: "기자회견", el: <PresserChart /> },
];

export default function Fomc() {
  const [sub, setSub] = useState("all");
  return (
    <>
      <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
        {SUB.map((s) => (
          <button key={s.key} type="button" onClick={() => setSub(s.key)}
            style={{
              padding: "7px 16px", cursor: "pointer", font: "inherit", fontWeight: 600,
              borderRadius: 999, border: "1px solid var(--line)",
              background: sub === s.key ? "var(--accent)" : "transparent",
              color: sub === s.key ? "#fff" : "var(--muted)",
            }}>
            {s.label}
          </button>
        ))}
      </div>
      {SUB.find((s) => s.key === sub).el}
    </>
  );
}
