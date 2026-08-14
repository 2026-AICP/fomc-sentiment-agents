import { useJson, fmt } from "../lib/data";
import { Panel } from "../components/ui";
import { IndexArea } from "../components/charts";

export default function News() {
  const { data: news } = useJson("news_daily");
  if (!news) return <div className="loading">데이터를 불러오는 중입니다.</div>;
  if (!news.length) return <div className="loading">아직 수집된 뉴스 지수가 없습니다.</div>;

  return (
    <>
      <h1>뉴스 감성지수</h1>
      <p className="sub">
        연준과 통화정책에 관한 경제뉴스를 매일 수집해 문장 단위로 채점하고,
        하루치를 모아 지수로 만듭니다.
      </p>

      <Panel cap="지수가 0보다 크면 낙관, 작으면 우려에 가까운 기사가 많았다는 뜻입니다. 기사 수가 적은 날은 값의 변동이 커질 수 있습니다.">
        <IndexArea data={news} y="index" color="var(--blue)" />
      </Panel>

      <h2 className="sec">일별 상세</h2>
      <div className="panel tbl-wrap">
        <table className="tbl">
          <thead>
            <tr><th>일자</th><th>기사 수</th><th>지수</th><th>신뢰구간</th><th>확신도</th></tr>
          </thead>
          <tbody>
            {news.slice().reverse().map((r) => (
              <tr key={r.date}>
                <td>{r.date}</td>
                <td>{r.n_articles}</td>
                <td className={r.index > 0 ? "pos" : "neg"}>{fmt(r.index)}</td>
                <td>{r.ci_lo == null ? "기사 부족" : `${fmt(r.ci_lo)} ~ ${fmt(r.ci_hi)}`}</td>
                <td>{fmt(r.confidence, 3, false)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note">
        신뢰구간은 그날 기사들을 무작위로 다시 뽑아 계산한 지수의 범위입니다. 범위가 좁을수록
        기사 간 어조가 일관됐다는 뜻입니다.
      </div>
    </>
  );
}
