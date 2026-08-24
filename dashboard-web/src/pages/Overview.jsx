import { useJson, fmt, gradeInfo, toneLabel, firedNames, stripEmoji } from "../lib/data";
import { Kpi, Panel, Pill } from "../components/ui";
import { IndexArea } from "../components/charts";

export default function Overview() {
  const { data: meetings } = useJson("meetings");
  const { data: daily } = useJson("daily_signals");
  const { data: news } = useJson("news_daily");
  const { data: alerts } = useJson("alerts");
  if (!meetings || !alerts) return <div className="loading">데이터를 불러오는 중입니다.</div>;

  const lastMeet = meetings[meetings.length - 1];
  const lastDaily = daily?.[daily.length - 1];
  const lastNews = news?.[news.length - 1];
  const lastAlert = alerts[alerts.length - 1];
  const g = gradeInfo(lastAlert.grade);
  const newsLabel = toneLabel(lastNews?.index);

  return (
    <>
      <h1>감성지수 추이</h1>
      <p className="sub">
        연준 문서와 경제뉴스의 어조를 하나의 지수로 결합해 매일 산출합니다.
        지수가 0보다 크면 낙관, 작으면 우려에 가까운 어조입니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="통합 감성지수"
          value={<span style={{ color: "var(--accent)" }}>{fmt(lastDaily?.index)}</span>}
          meta={lastDaily
            ? `${lastDaily.date} · 연준 문서와 뉴스 결합`
              + (lastDaily.gate_reason ? ` · ${lastDaily.gate_reason}` : "")
              + (lastDaily.grade_final
                  ? ` · 회의록 반영 확정판 ${fmt(lastDaily.index_final)} (${lastDaily.finalized_at?.slice(0, 10)})`
                  : "")
            : "산출 전"} />
        <Kpi eyebrow="연준 성명문" value={fmt(lastMeet.tone)}
          meta={`${lastMeet.date} 회의`} />
        <Kpi eyebrow="경제뉴스" value={fmt(lastNews?.index)}
          meta={lastNews
            ? `${lastNews.date} · 기사 ${lastNews.n_articles}건${newsLabel ? ` · ${newsLabel.text}` : ""}`
            : "수집 전"} />
        <Kpi eyebrow="최근 회의 신호"
          value={<span style={{ fontSize: 22, color: g.color }}>{g.label}</span>}
          meta={lastAlert.date} />
      </div>

      <h2 className="sec">성명문 톤 추이 (2000년 이후)</h2>
      <Panel cap="회의 220건의 성명문을 문장 단위로 채점한 뒤, 확신이 높은 문장에 더 큰 비중을 두어 평균했습니다.">
        <IndexArea data={meetings} y="tone" />
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
