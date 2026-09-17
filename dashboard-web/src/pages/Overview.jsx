import { useJson, fmt, gradeInfo, toneLabel, firedNames, stripEmoji } from "../lib/data";
import { Kpi, Panel, Pill } from "../components/ui";
import { IndexArea } from "../components/charts";
import { fedAxisStatus } from "../lib/fedAxis";

export default function Overview() {
  const { data: meetings } = useJson("meetings");
  const { data: news } = useJson("news_daily");
  const { data: combined } = useJson("daily_headline");
  const { data: alerts } = useJson("alerts");
  const { data: axis } = useJson("axis_status");
  if (!meetings || !alerts) return <div className="loading">데이터를 불러오는 중입니다.</div>;

  const lastMeet = meetings[meetings.length - 1];
  const lastCombined = combined?.[combined.length - 1];
  // 연준 값은 도착한 문서만으로 계산된 표준화 점수다. 문서별 원점수를 옆에 적으면 척도가
  // 달라 "성명문만 있는데 왜 값이 다르냐"로 읽힌다(2026-09-16 회의 지적) — 원점수 대신
  // 어떤 문서가 들어갔는지(✓/대기)와 잠정·확정 여부를 보여준다. 원점수는 FOMC 탭에 있다.
  const fedSt = fedAxisStatus(axis, lastCombined?.date);
  const lastNews = news?.[news.length - 1];
  const lastAlert = alerts[alerts.length - 1];
  const g = gradeInfo(lastAlert.grade);
  const newsLabel = toneLabel(lastNews?.index);

  return (
    <>
      <h1>감성지수 추이</h1>
      <p className="sub">
        연준 문서 세 종류(성명문·회의록·기자회견을 같은 비중으로 합친 값)와 경제뉴스를
        1:1로 결합해 매일 산출합니다. 통합 지수와 연준 문서 값은 과거 평균을 0으로 놓은
        표준화 점수라, 클수록 평소보다 긍정적입니다. 연준 문서 값은 회의록이 공개되는 회의
        약 3주 뒤까지 잠정치이며, 문서가 더 들어오면 달라질 수 있습니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="통합 감성지수"
          value={<span style={{ color: "var(--accent)" }}>{fmt(lastCombined?.index)}</span>}
          meta={lastCombined
            ? `${lastCombined.date} · 연준 ${fmt(lastCombined.fed)}${fedSt && !fedSt.final ? " (잠정)" : ""}`
              + ` · 뉴스 ${fmt(lastCombined.news_z ?? lastCombined.news)} 를 1:1 결합 (표준화 점수)`
            : "산출 전"} />
        <Kpi eyebrow="연준 문서"
          value={<>
            <span style={{ color: "var(--accent)" }}>{fmt(lastCombined?.fed)}</span>
            <span className="unit">표준화 점수</span>
          </>}
          pill={fedSt?.badge} pillColor={fedSt?.final ? "var(--accent)" : "var(--muted)"}
          meta={fedSt ? `${fedSt.date} 회의 · ${fedSt.docsText}` : `${lastMeet.date} 회의`} />
        <Kpi eyebrow="경제뉴스"
          value={<>{fmt(lastNews?.index)}<span className="unit">원점수</span></>}
          meta={lastNews
            ? `${lastNews.date} · 기사 ${lastNews.n_articles}건${newsLabel ? ` · ${newsLabel.text}` : ""}`
            : "수집 전"} />
        <Kpi eyebrow="최근 회의 신호"
          value={<span style={{ fontSize: 22, color: g.color }}>{g.label}</span>}
          meta={lastAlert.date} />
      </div>

      <h2 className="sec">통합 감성지수 추이 (일별)</h2>
      <Panel cap="연준 문서(성명문·회의록·기자회견 1:1:1)와 경제뉴스를 1:1로 결합한 일별 지수입니다. 0이 과거 평균이며, 문서별 톤은 FOMC 탭에서 볼 수 있습니다.">
        <IndexArea data={combined || []} y="index" color="var(--accent)" />
      </Panel>

      <h2 className="sec">최근 회의 신호</h2>
      {alerts.slice(-6).reverse().map((a) => {
        const gi = gradeInfo(a.grade);
        return (
          <div className="alert-row" key={a.date}>
            <div>
              <div className="d1">{a.date} · {stripEmoji(a.detail) || "특이 사항 없음"}</div>
              <div className="d2">
                톤 {fmt(a.tone)} · 시장 반응 {a.reaction == null ? "—" : `${fmt(a.reaction, 2)}%`} ·{" "}
                {a.fired.length ? `발동 규칙: ${firedNames(a.fired)}` : "발동한 규칙 없음"}
              </div>
            </div>
            <Pill color={gi.color}>{gi.label}</Pill>
          </div>
        );
      })}
      <div className="note">
        신호는 매수·매도 권고가 아니라, 연준의 어조와 시장 반응이 어긋난 날을 표시합니다.
        규칙별 기준은 신호 페이지에서 설명합니다.
      </div>
    </>
  );
}
