import { useJson, fmt } from "../lib/data";
import { Panel } from "../components/ui";
import { IndexArea } from "../components/charts";

export default function News() {
  const { data: news } = useJson("news_daily");
  if (!news) return <div className="loading">데이터 로딩…</div>;
  if (!news.length) return <div className="loading">News 지수 없음 — 파이프라인을 먼저 실행하세요.</div>;

  return (
    <>
      <h1>News 축</h1>
      <p className="sub">Marketaux 실시간 뉴스 → FinBERT 채점 → 일별 지수 + 부트스트랩 95% CI</p>

      <Panel cap="확신도 가중 일별 지수 — 신뢰는 CI(기사 양)로 표시">
        <IndexArea data={news} y="index" color="var(--blue)" />
      </Panel>

      <h2 className="sec">일별 상세</h2>
      <div className="panel tbl-wrap">
        <table className="tbl">
          <thead>
            <tr><th>일자</th><th>기사수</th><th>지수</th><th>95% CI</th><th>확신도</th></tr>
          </thead>
          <tbody>
            {news.slice().reverse().map((r) => (
              <tr key={r.date}>
                <td>{r.date}</td>
                <td>{r.n_articles}</td>
                <td className={r.index > 0 ? "pos" : "neg"}>{fmt(r.index)}</td>
                <td>{r.ci_lo == null ? "계산불가 (표본<2)" : `${fmt(r.ci_lo)} ~ ${fmt(r.ci_hi)}`}</td>
                <td>{fmt(r.confidence, 3, false)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
