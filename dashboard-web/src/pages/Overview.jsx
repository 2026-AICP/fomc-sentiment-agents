import { useJson, fmt, GRADE_COLOR } from "../lib/data";
import { Kpi, Panel, Pill } from "../components/ui";
import { IndexArea } from "../components/charts";

export default function Overview() {
  const { data: meetings } = useJson("meetings");
  const { data: daily } = useJson("daily_signals");
  const { data: news } = useJson("news_daily");
  const { data: alerts } = useJson("alerts");
  if (!meetings || !alerts) return <div className="loading">데이터 로딩…</div>;

  const lastMeet = meetings[meetings.length - 1];
  const lastDaily = daily?.[daily.length - 1];
  const lastNews = news?.[news.length - 1];
  const lastAlert = alerts[alerts.length - 1];

  return (
    <>
      <h1>오늘의 시장 감성 👋</h1>
      <p className="sub">FOMC 성명문(Fed 축) + 경제뉴스(News 축) 실시간 감성·신호 — 예측이 아닌 경향</p>

      <div className="kpis">
        <Kpi eyebrow="통합 감성 (headline) Σ"
          value={<span style={{ color: "var(--accent)" }}>{fmt(lastDaily?.index)}</span>}
          meta={lastDaily ? `${lastDaily.date} · 결합(News+Fed) z` : "daily_signals 없음"} />
        <Kpi eyebrow="Fed 축 (성명문) 🏛" value={fmt(lastMeet.tone)}
          meta={`${lastMeet.date} 성명문`} />
        <Kpi eyebrow="News 축 (최근) ✦" value={fmt(lastNews?.index)}
          meta={lastNews ? `${lastNews.date} · 기사 ${lastNews.n_articles}건` : "뉴스 없음"} />
        <Kpi eyebrow="최근 회의 신호 ⚑"
          value={<span style={{ fontSize: 22 }}>{lastAlert.grade}</span>}
          meta={lastAlert.date} />
      </div>

      <h2 className="sec">회의 톤 타임라인 (Fed 축, 2000~)</h2>
      <Panel cap="확신도 가중(conf_weighted) · FinBERT T=3.1 보정 · 220개 회의">
        <IndexArea data={meetings} y="tone" />
      </Panel>

      <h2 className="sec">최근 신호</h2>
      {alerts.slice(-6).reverse().map((a) => (
        <div className="alert-row" key={a.date}>
          <div>
            <div className="d1">{a.date} — {a.detail || "특이신호 없음"}</div>
            <div className="d2">톤 {fmt(a.tone)} · 시장반응 {fmt(a.reaction, 2)}% · 발동 [{a.fired.join(", ") || "—"}]</div>
          </div>
          <Pill color={GRADE_COLOR[a.grade]}>{a.grade}</Pill>
        </div>
      ))}
    </>
  );
}
