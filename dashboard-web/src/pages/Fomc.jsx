import { useState } from "react";
import { useJson, fmt } from "../lib/data";
import { Kpi, Panel } from "../components/ui";
import { IndexArea } from "../components/charts";
import Minutes from "./Minutes";
import Presser from "./Presser";

/** 성명문 — 감성지수 탭에 섞여 있던 성명문 콘텐츠를 문서 자격으로 독립. */
function Statement() {
  const { data: meetings } = useJson("meetings");
  const { data: meta } = useJson("meta");
  if (!meetings) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  const last = meetings[meetings.length - 1];
  const avg = meta?.minutes_finding?.axis_means?.statement;

  return (
    <>
      <h1>성명문</h1>
      <p className="sub">
        FOMC가 회의 당일 발표하는 공식 결정문입니다. 세 문서 중 가장 다듬어진 언어로 쓰이며,
        지수의 가장 긴 축(2000년~현재)을 이룹니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="최근 성명문 톤" value={fmt(last.tone)} meta={`${last.date} 회의`} />
        <Kpi eyebrow="역사 평균" value={fmt(avg ?? 0.185)}
          meta="세 문서 중 가장 낙관적" />
        <Kpi eyebrow="수집 범위" value={`${meetings.length}회`} meta="2000년 이후 전 회의" />
      </div>

      <h2 className="sec">성명문 톤 추이 (2000년 이후)</h2>
      <Panel cap="회의별 성명문을 문장 단위로 채점한 뒤, 확신이 높은 문장에 더 큰 비중을 두어 평균했습니다.">
        <IndexArea data={meetings} y="tone" />
      </Panel>

      <div className="note">
        성명문은 시장을 안심시키는 공식 화법으로 쓰여, 전체 회의의 약 72%에서 어조가
        낙관(양수)입니다. 2008년 10월·2020년 3월 위기 성명문조차 양수였습니다. 그래서
        성명문 톤은 절대값보다 <b>평소 수준(평균 {fmt(avg ?? 0.185)}) 대비 어디에 있는지</b>로
        읽는 것이 정확하며, 통합지수 계산도 같은 이유로 각 문서를 자기 평균 대비로 변환한 뒤
        결합합니다.
      </div>
    </>
  );
}

const SUB = [
  { key: "statement", label: "성명문", el: <Statement /> },
  { key: "minutes", label: "회의록", el: <Minutes /> },
  { key: "presser", label: "기자회견", el: <Presser /> },
];

export default function Fomc() {
  const [sub, setSub] = useState("statement");
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
