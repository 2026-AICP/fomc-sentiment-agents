import { useJson, fmt } from "../lib/data";

/** 부호에 따라 색을 주는 숫자. 값이 없으면 '대기'(아직 안 온 축) 또는 '—'. */
function N({ v, d = 3, suffix = "", pending = false }) {
  if (v == null) return <span className="na">{pending ? "대기" : "—"}</span>;
  return <span className={`num ${v > 0 ? "pos" : v < 0 ? "neg" : ""}`}>{fmt(v, d)}{suffix}</span>;
}

const GRADE = {
  "🔴 경고": ["crit", "경고"], "⚠️ 주의": ["warn", "주의"],
  "🟢 정합": ["ok", "정합"], "⚪ 중립": ["mut", "중립"],
};
function Grade({ g }) {
  if (!g) return <span className="na">—</span>;
  const [k, label] = GRADE[g] || ["mut", g];
  const color = { crit: "var(--crit)", warn: "var(--warn)", ok: "var(--up)", mut: "var(--muted)" }[k];
  return (
    <span className="pill" style={{
      color, borderColor: `color-mix(in srgb, ${color} 30%, transparent)`,
      background: `color-mix(in srgb, ${color} 9%, transparent)`,
    }}>{label}</span>
  );
}

/** 일별 지수 스파크라인 — 0선을 함께 그려 부호를 읽히게 한다. */
function Spark({ values, w = 300, h = 44 }) {
  if (!values?.length) return null;
  const lo = Math.min(...values), hi = Math.max(...values), rng = hi - lo || 1;
  const y = (v) => h - 4 - ((v - lo) / rng) * (h - 8);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${y(v)}`).join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}
      aria-label="최근 지수 추이">
      <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--line)" strokeDasharray="3 3" />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.8" />
    </svg>
  );
}

export default function Home() {
  const { data: daily } = useJson("news_daily");
  const { data: alerts } = useJson("alerts");
  const { data: minutes } = useJson("minutes");
  const { data: presser } = useJson("presser");
  const { data: axis } = useJson("axis_status");
  const { data: market } = useJson("market");
  const { data: news } = useJson("news_headlines");
  const { data: meta } = useJson("meta");
  if (!daily || !alerts || !meta || !market) return <div className="loading">데이터 로딩…</div>;

  const byDate = (arr) => Object.fromEntries((arr || []).map((r) => [r.date, r]));
  const mn = byDate(minutes), pr = byDate(presser), ax = byDate(axis);

  const series = daily.map((d) => d.index).filter((v) => v != null).slice(-30);
  const last = daily[daily.length - 1];
  const rows = alerts.slice(-8).reverse();

  const m = market[market.length - 1], m0 = market[market.length - 2];
  const diff = (a, b) => (a == null || b == null ? null : Math.round((a - b) * 100) / 100);
  const indicators = [
    ["S&P 500", m.spx, m.spx_ret, "지수", "%"],
    ["VIX 변동성", m.vix, m.vix_chg, "지수", ""],
    ["미 국채 2년", m.ust2y, diff(m.ust2y, m0.ust2y), "%", "%p"],
    ["미 국채 10년", m.ust10y, diff(m.ust10y, m0.ust10y), "%", "%p"],
    ["장단기 스프레드", m.spread, diff(m.spread, m0.spread), "%p", "%p"],
  ];

  const mf = meta.minutes_finding, am = mf?.axis_means;

  return (
    <div className="cols">
      <div>
        <div className="card">
          <h2>Fed·뉴스 통합 감성지수
            <span className="more"><a href="#">지수 상세 ›</a></span></h2>
          <div className="pad hero">
            <div>
              <div className="lbl">최근값 · {last.date}</div>
              <div className={`big ${last.index > 0 ? "pos" : last.index < 0 ? "neg" : ""}`}>
                {fmt(last.index)}
              </div>
              <div className="sub2">기사 {last.n_articles}건 · 확신도 가중 · 최근 {series.length}일 추이</div>
            </div>
            <Spark values={series} />
          </div>
          <div className="note">
            지수는 공개 문서·기사의 <b>톤</b>을 수치화한 것입니다. 시장 예측이 아닙니다.
          </div>
        </div>

        <div className="card">
          <h2>FOMC 회의 일정 · 감성
            <span className="more"><a href="#">전체 캘린더 ›</a></span></h2>
          <div className="scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>일자</th><th>이벤트</th>
                  <th className="r">성명문</th><th className="r">회의록</th><th className="r">기자회견</th>
                  <th className="c">수집</th><th className="c">신호</th><th className="r">시장반응</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => {
                  const x = ax[a.date] || {};
                  const full = x.n_axes === x.expected;
                  return (
                    <tr key={a.date}>
                      <td className="dt">{a.date}</td>
                      <td>FOMC 정례회의</td>
                      <td className="r"><N v={a.tone} /></td>
                      <td className="r"><N v={mn[a.date]?.minutes} pending /></td>
                      <td className="r"><N v={pr[a.date]?.presser} pending /></td>
                      <td className="c">
                        <span className={`ax ${full ? "full" : "part"}`}>
                          {x.n_axes ?? "–"}/{x.expected ?? "–"}
                        </span>
                      </td>
                      <td className="c"><Grade g={a.grade} /></td>
                      <td className="r"><N v={a.reaction} d={2} suffix="%" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="note">
            회의록은 회의 <b>3주 후</b>, 기자회견 원문은 며칠 후 공개됩니다 — 도착하는 대로 자동으로 채워집니다.
          </div>
        </div>

        {news?.length > 0 && (
          <div className="card">
            <h2>Fed 관련 주요 뉴스<span className="more"><a href="#">더 보기 ›</a></span></h2>
            <ul className="news">
              {news.slice(0, 8).map((n) => (
                <li key={n.url || n.title}>
                  <a className="hl" href={n.url || "#"} target="_blank" rel="noreferrer">{n.title}</a>
                  <div className="hl-meta">
                    <span className="src">{n.source}</span>
                    <span>{n.published_at.slice(5, 10).replace("-", "/")} {n.published_at.slice(11, 16)}</span>
                  </div>
                </li>
              ))}
            </ul>
            <div className="note">
              연준·통화정책 키워드(F그룹 AND M그룹)를 만족한 기사만 지수에 반영됩니다.
            </div>
          </div>
        )}
      </div>

      <aside>
        <div className="card">
          <h2>시장 지표</h2>
          <table className="data">
            <thead>
              <tr><th>지표</th><th className="r">종가</th><th className="r">전일비</th><th className="c">단위</th></tr>
            </thead>
            <tbody>
              {indicators.map(([n, v, c, u, s]) => (
                <tr key={n}>
                  <td>{n}</td>
                  <td className="r"><span className="num">{v?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></td>
                  <td className="r"><N v={c} d={2} suffix={s} /></td>
                  <td className="c u">{u}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="note">기준일 {m.date}</div>
        </div>

        {am && (
          <div className="card">
            <h2>문서별 평균 톤</h2>
            <table className="data">
              <thead><tr><th>문서</th><th className="r">평균</th><th>성격</th></tr></thead>
              <tbody>
                {[["성명문", am.statement, "대외 공식"],
                  ["회의록", am.minutes, "내부 논의"],
                  ["기자회견", am.presser, "라이브 Q&A"]].map(([n, v, d]) => (
                  <tr key={n}><td>{n}</td><td className="r"><N v={v} /></td><td className="u">{d}</td></tr>
                ))}
              </tbody>
            </table>
            <div className="note">
              공식 문서일수록 낙관적 — 회의록이 성명문보다 신중한 비율{" "}
              <b>{Math.round(mf.pct_more_cautious * 100)}%</b> (n={mf.n_meetings}, p={mf.p_sign_test.toExponential(0)})
            </div>
          </div>
        )}

        <div className="card">
          <h2>이 사이트는</h2>
          <div className="pad" style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.7 }}>
            FOMC <b>성명문·회의록·기자회견</b>과 경제뉴스를 같은 방식으로 점수화해 공개합니다.
            <br /><br />
            규칙 기반 · LLM 미사용 · 전 과정 재현 가능.
          </div>
        </div>
      </aside>
    </div>
  );
}
