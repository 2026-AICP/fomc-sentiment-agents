import { useState } from "react";
import { useJson, fmt, confidenceLevel } from "../lib/data";
import { Panel } from "../components/ui";
import { IndexArea } from "../components/charts";

// 구간 단위 표기 — 주별(과거)과 일별(현재)이 한 시계열에 섞여 있어 행마다 밝힌다.
const periodLabel = (p) => (p === "weekly" ? "주" : "일");

export default function News() {
  const { data: news } = useJson("news_daily");
  const [showAll, setShowAll] = useState(false);   // 표: 기본 최근 7구간
  if (!news) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  if (!news.length) return <div className="loading">아직 수집된 뉴스 지수가 없습니다.</div>;

  const rows = news.slice().reverse();
  const visible = showAll ? rows : rows.slice(0, 7);
  const nWeekly = news.filter((r) => r.period === "weekly").length;
  const nDaily = news.length - nWeekly;

  return (
    <>
      <h1>뉴스 감성지수</h1>
      <p className="sub">
        연준과 통화정책에 관한 경제뉴스를 수집해 문장 단위로 채점하고, 모아서 지수로 만듭니다.
        {nWeekly > 0 && (
          <>
            {" "}2021년부터 2026년 7월 9일까지는 <b>주 단위</b>({nWeekly}주),
            그 이후는 <b>일 단위</b>({nDaily}일)입니다.
          </>
        )}
      </p>

      {nWeekly > 0 && (
        <div className="note" style={{ marginBottom: 12 }}>
          과거 구간을 주 단위로 묶은 이유는 하루치 기사가 중앙값 7건뿐이라
          신뢰도 하한(15건)을 넘지 못하는 날이 대부분이기 때문입니다. 주 단위로 묶으면
          중앙값 62건이 되어 값이 안정됩니다. 두 구간의 기사 선정 규칙은 같아서
          이어서 보셔도 됩니다.
        </div>
      )}

      <Panel cap="지수가 0보다 크면 낙관, 작으면 우려에 가까운 기사가 많았다는 뜻입니다. 기사 수가 적은 구간은 값의 변동이 커질 수 있습니다. 2026년 7월 9일을 기준으로 왼쪽은 주 단위, 오른쪽은 일 단위입니다.">
        <IndexArea data={news} y="index" color="var(--blue)" />
      </Panel>

      <h2 className="sec">구간별 지수</h2>
      <div className="panel tbl-wrap">
        <table className="tbl">
          <thead>
            <tr><th>기준일</th><th>단위</th><th className="r">지수</th>
              <th className="r">기사 수</th><th>신뢰도</th></tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const c = confidenceLevel(r.n_articles, r.ci_lo, r.ci_hi);
              return (
                <tr key={r.date}>
                  <td>{r.date}</td>
                  <td style={{ color: "var(--muted)" }}>{periodLabel(r.period)}</td>
                  <td className={`r ${r.index > 0 ? "pos" : "neg"}`}>{fmt(r.index)}</td>
                  <td className="r">{r.n_articles}</td>
                  <td style={{ color: c.color, fontWeight: 600 }}>{c.label}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length > 7 && (
          <button type="button" onClick={() => setShowAll(!showAll)}
            style={{ width: "100%", padding: "9px 0", marginTop: 2, cursor: "pointer",
                     background: "none", border: "none", borderTop: "1px solid var(--line)",
                     color: "var(--accent)", font: "inherit", fontWeight: 600 }}>
            {showAll ? "접기" : `더보기 (전체 ${rows.length}구간)`}
          </button>
        )}
      </div>
      <div className="note">
        주 단위 행의 기준일은 그 주의 시작일(월요일)입니다.
        신뢰도는 그 구간에 모인 기사 수와 기사 간 어조가 얼마나 일치하는지로 판단합니다.
        <b> 낮음</b>인 구간은 지수는 그대로 보여드리되 신호는 내지 않습니다.
      </div>

      <h2 className="sec">신뢰도를 어떻게 정하나요?</h2>
      <div className="cards2">
        {[["높음", "var(--up)", "기사 30건 이상이고 어조가 일관될 때"],
          ["보통", "var(--muted)", "기사 15건 이상이고 어조 차이가 크지 않을 때"],
          ["낮음", "var(--warn)", "기사가 15건 미만이거나 어조가 크게 엇갈릴 때"]].map(([l, c, d]) => (
          <div className="panel" key={l} style={{ marginTop: 0 }}>
            <b style={{ color: c }}>{l}</b>
            <div className="cap">{d}</div>
          </div>
        ))}
      </div>

      <details style={{ marginTop: 14 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600, padding: "8px 0" }}>
          상세 수치 보기 (신뢰구간·확신도)
        </summary>
        <div className="panel tbl-wrap" style={{ marginTop: 8 }}>
          <table className="tbl">
            <thead>
              <tr><th>기준일</th><th>단위</th><th className="r">지수</th><th className="r">기사 수</th>
                <th>신뢰구간 (95%)</th><th className="r">확신도</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date}>
                  <td>{r.date}</td>
                  <td style={{ color: "var(--muted)" }}>{periodLabel(r.period)}</td>
                  <td className={`r ${r.index > 0 ? "pos" : "neg"}`}>{fmt(r.index)}</td>
                  <td className="r">{r.n_articles}</td>
                  <td>{r.ci_lo == null ? "기사 부족" : `${fmt(r.ci_lo)} ~ ${fmt(r.ci_hi)}`}</td>
                  <td className="r">{fmt(r.confidence, 3, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="note">
          신뢰구간은 그 구간의 기사들을 무작위로 다시 뽑아 지수를 계산했을 때 나오는 범위입니다.
          범위가 좁을수록 기사 간 어조가 일관됐다는 뜻입니다. 확신도는 모델이 각 문장을
          얼마나 분명하게 판단했는지를 0~1로 나타냅니다.
        </div>
      </details>
    </>
  );
}
