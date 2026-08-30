import { useJson, fmt, gradeInfo, toneLabel, firedNames, stripEmoji } from "../lib/data";
import { Kpi, Panel, Pill } from "../components/ui";
import { IndexArea } from "../components/charts";

export default function Overview() {
  const { data: meetings } = useJson("meetings");
  const { data: news } = useJson("news_daily");
  const { data: combined } = useJson("daily_headline");
  const { data: minutesTones } = useJson("minutes");
  const { data: presserTones } = useJson("presser");
  const { data: alerts } = useJson("alerts");
  if (!meetings || !alerts) return <div className="loading">데이터를 불러오는 중입니다.</div>;

  const lastMeet = meetings[meetings.length - 1];
  const lastCombined = combined?.[combined.length - 1];
  // 통합지수의 Fed 절반은 3축 결합값 — 성명문 하나만 보여주면 구성이 오해된다.
  const lastMn = minutesTones?.find((r) => r.date === lastMeet.date);
  const lastPr = presserTones?.find((r) => r.date === lastMeet.date);
  const axesTxt = [
    lastMeet.tone != null ? `성명문 ${fmt(lastMeet.tone)}` : null,
    lastMn?.minutes != null ? `회의록 ${fmt(lastMn.minutes)}` : null,
    lastPr?.presser != null ? `기자회견 ${fmt(lastPr.presser)}` : null,
  ].filter(Boolean).join(" · ");
  const lastNews = news?.[news.length - 1];
  const lastAlert = alerts[alerts.length - 1];
  const g = gradeInfo(lastAlert.grade);
  const newsLabel = toneLabel(lastNews?.index);

  return (
    <>
      <h1>감성지수 추이</h1>
      <p className="sub">
        연준 문서 세 종류(성명문·회의록·기자회견을 같은 비중으로 합친 값)와 경제뉴스를
        1:1로 결합해 매일 산출합니다. 통합 지수는 과거 평균을 0으로 놓은 상대값입니다.
      </p>

      <div className="kpis">
        <Kpi eyebrow="통합 감성지수"
          value={<span style={{ color: "var(--accent)" }}>{fmt(lastCombined?.index)}</span>}
          meta={lastCombined
            ? `${lastCombined.date} · Fed ${fmt(lastCombined.fed)} · 뉴스 ${fmt(lastCombined.news)} 를 1:1 결합`
            : "산출 전"} />
        <Kpi eyebrow="연준 문서 (3축)"
          value={<span style={{ color: "var(--accent)" }}>{fmt(lastCombined?.fed)}</span>}
          meta={`${lastMeet.date} 회의 · ${axesTxt}`} />
        <Kpi eyebrow="경제뉴스" value={fmt(lastNews?.index)}
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
