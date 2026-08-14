import { useJson, fmt, toneLabel } from "../lib/data";

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

  const m = market[market.length - 1];
  // 항목마다 가장 최근의 유효값 2개를 찾는다 — 마지막 행만 보면 그날 결측인 항목이 빈칸이 된다.
  const recent = (key) => {
    const out = [];
    for (let i = market.length - 1; i >= 0 && out.length < 2; i--) {
      if (market[i][key] != null) out.push(market[i][key]);
    }
    return out;
  };
  const pick = (key, chgKey = null) => {
    const [v, prev] = recent(key);
    const c = chgKey ? m[chgKey] : (v != null && prev != null ? Math.round((v - prev) * 100) / 100 : null);
    return [v ?? null, c ?? null];
  };
  const indicators = [
    ["S&P 500", ...pick("spx", "spx_ret"), "지수", "%"],
    ["VIX 변동성", ...pick("vix", "vix_chg"), "지수", ""],
    ["미 국채 2년", ...pick("ust2y"), "%", "%p"],
    ["미 국채 10년", ...pick("ust10y"), "%", "%p"],
    ["장단기 스프레드", ...pick("spread"), "%p", "%p"],
  ];

  const mf = meta.minutes_finding, am = mf?.axis_means;
  const lastLabel = toneLabel(last.index);

  return (
    <>
      <h1>FOMC 감성지수</h1>
      <p className="sub">
        미국 연방준비제도(연준)의 성명문·회의록·기자회견과 경제뉴스를 같은 기준으로 분석해,
        연준의 어조가 낙관에 가까운지 우려에 가까운지 지수로 보여줍니다.
        지수는 −1(비관)부터 +1(낙관) 사이의 값이며, 대체로 −0.3에서 +0.4 사이에서 움직입니다.
      </p>

      <div className="cols">
      <div>
        <div className="card">
          <h2>통합 감성지수</h2>
          <div className="pad hero">
            <div>
              <div className="lbl">최근값 · {last.date}</div>
              <div className={`big ${last.index > 0 ? "pos" : last.index < 0 ? "neg" : ""}`}
                style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {fmt(last.index)}
                {lastLabel && (
                  <span className="pill" style={{
                    color: lastLabel.color, fontSize: 13,
                    border: `1px solid color-mix(in srgb, ${lastLabel.color} 30%, transparent)`,
                    background: `color-mix(in srgb, ${lastLabel.color} 9%, transparent)`,
                  }}>{lastLabel.text}</span>
                )}
              </div>
              <div className="sub2">이날 기사 {last.n_articles}건 기준 · 최근 {series.length}일 흐름</div>
            </div>
            <Spark values={series} />
          </div>
          <div className="note">
            지수는 공개된 문서와 기사의 어조를 수치화한 것입니다. 시장 전망이나 투자 판단의
            근거가 아닙니다.
          </div>
        </div>

        <div className="card">
          <h2>FOMC 회의별 감성</h2>
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
            한 회의에서 성명문·회의록·기자회견 세 자료가 모두 공개되면 수집 항목이 3/3이 됩니다.
            회의록은 회의 약 3주 뒤, 기자회견 원문은 며칠 뒤에 공개되며, 그때까지는 대기로
            표시됩니다. 신호는 매수·매도 권고가 아니라 연준의 어조와 시장 반응이 어긋난 날을
            표시합니다.
          </div>
        </div>

        {news?.length > 0 && (
          <div className="card">
            <h2>연준 관련 주요 뉴스</h2>
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
              연준과 통화정책에 직접 관련된 기사만 골라 지수에 반영합니다.
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
                  <td className="r"><span className="num">
                    {v == null ? <span className="na">—</span>
                      : v.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span></td>
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
                {[["성명문", am.statement, "공식 발표문"],
                  ["회의록", am.minutes, "내부 논의 기록"],
                  ["기자회견", am.presser, "즉석 질의응답"]].map(([n, v, d]) => (
                  <tr key={n}><td>{n}</td><td className="r"><N v={v} /></td><td className="u">{d}</td></tr>
                ))}
              </tbody>
            </table>
            <div className="note">
              공식 발표문일수록 어조가 낙관적입니다. 전체 {mf.n_meetings}회 중{" "}
              {Math.round(mf.pct_more_cautious * mf.n_meetings)}회에서 회의록이 성명문보다
              신중했습니다.
            </div>
          </div>
        )}

        <div className="card">
          <h2>이 사이트는</h2>
          <div className="pad" style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.7 }}>
            Econpilot은 연준의 공개 문서와 경제뉴스를 자동으로 수집해 같은 기준으로 채점하고,
            매일 아침 지수를 갱신합니다. 모든 수치는 고정된 규칙으로 계산되며 전 과정을
            재현할 수 있습니다.
          </div>
        </div>
      </aside>
      </div>
    </>
  );
}
