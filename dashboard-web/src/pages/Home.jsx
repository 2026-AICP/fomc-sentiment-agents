import { useJson, fmt, toneLabel, confidenceLevel } from "../lib/data";

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
// 초소형 추세 그래프 — 축·눈금 없이 방향과 굴곡만 보여준다(값은 옆 숫자가 말한다).
// zero: 0 기준선(감성지수처럼 부호가 의미 있을 때만), dot: 최신값 강조점.
function Spark({ values, w = 300, h = 44, color = "var(--accent)", zero = true, dot = false }) {
  if (!values?.length) return null;
  const lo = Math.min(...values), hi = Math.max(...values), rng = hi - lo || 1;
  const y = (v) => h - 4 - ((v - lo) / rng) * (h - 8);
  const px = (i) => 2 + (i / (values.length - 1)) * (w - 4);
  const pts = values.map((v, i) => `${px(i)},${y(v)}`).join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`}
      aria-hidden="true" style={{ flexShrink: 0 }}>
      {zero && lo < 0 && hi > 0 && (
        <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--line)" strokeDasharray="3 3" />
      )}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8"
        strokeLinejoin="round" strokeLinecap="round" />
      {dot && <circle cx={px(values.length - 1)} cy={y(values[values.length - 1])} r="2.2" fill={color} />}
    </svg>
  );
}

export default function Home() {
  const { data: daily } = useJson("news_daily");        // 뉴스 단독 — 기사 수·CI 용
  const { data: combined } = useJson("daily_headline"); // 통합 = 뉴스 : Fed(1:1:1) = 1:1
  const { data: alerts } = useJson("alerts");
  const { data: minutes } = useJson("minutes");
  const { data: presser } = useJson("presser");
  const { data: axis } = useJson("axis_status");
  const { data: market } = useJson("market");
  const { data: news } = useJson("news_headlines");
  const { data: meta } = useJson("meta");
  if (!daily || !combined || !alerts || !meta || !market)
    return <div className="loading">데이터 로딩…</div>;

  const byDate = (arr) => Object.fromEntries((arr || []).map((r) => [r.date, r]));
  const mn = byDate(minutes), pr = byDate(presser), ax = byDate(axis);

  // 통합 감성지수 = News : Fed = 1:1 (Fed 내부는 성명문:회의록:기자회견 = 1:1:1).
  // 신뢰도는 그날 뉴스 표본으로 판정한다 — 통합값이 흔들리는 원인은 뉴스 쪽이기 때문.
  const series = combined.map((d) => d.index).filter((v) => v != null).slice(-30);
  const last = combined[combined.length - 1] || {};
  const lastNews = daily.find((d) => d.date === last.date) || daily[daily.length - 1] || {};
  const rows = alerts.slice(-8).reverse();

  const m = market[market.length - 1];
  // 지표별 최근 1년 흐름 — 숫자만으론 수준·방향이 안 잡혀서 작은 그래프를 붙인다.
  // ★행 개수로 자르면 안 된다: 표본 간격이 불규칙해서(회의 주간 위주) 마지막 52행이
  //   실제로는 약 3년치다. "52주"가 거짓이 되지 않게 날짜로 자른다.
  const asOf = new Date(m.date);
  const yearAgo = new Date(asOf); yearAgo.setDate(yearAgo.getDate() - 365);
  const cut = yearAgo.toISOString().slice(0, 10);
  const hist = (key) =>
    market.filter((r) => r.date >= cut).map((r) => r[key]).filter((v) => v != null);
  const spx52 = hist("spx");
  const wk52 = spx52.length
    ? { hi: Math.max(...spx52), lo: Math.min(...spx52) } : null;
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
  // 표기 규칙(2026-09 정리): '단위' 열은 종가의 단위이고, 전일비는 각 셀이 제 단위를 단다.
  //  · S&P 전일비 = 등락률(%) — 지수의 하루 변화는 %가 관례(알림 사전등록 |S&P 1d|>1.78% 와 동일 단위)
  //  · VIX 전일비 = 포인트 차이(pt) — %가 아님(사전등록 |VIX 1d|>2.40pt 와 동일 단위).
  //    예전엔 접미사가 없어 %로 오독될 여지가 있었다.
  const indicators = [
    ["S&P 500", ...pick("spx", "spx_ret"), "지수", "%"],
    ["VIX 변동성", ...pick("vix", "vix_chg"), "지수", "pt"],
    ["미 국채 2년", ...pick("ust2y"), "%", "%p"],
    ["미 국채 10년", ...pick("ust10y"), "%", "%p"],
    ["장단기 금리차", ...pick("spread"), "%p", "%p"],
  ];

  const lastLabel = toneLabel(last.index);
  const conf = confidenceLevel(lastNews.n_articles, lastNews.ci_lo, lastNews.ci_hi);

  return (
    <>
      <h1>FOMC 감성지수</h1>
      <p className="sub">
        미국 연방준비제도(연준)의 성명문·회의록·기자회견과 경제뉴스를 같은 기준으로 분석해,
        연준의 어조가 낙관에 가까운지 우려에 가까운지 지수로 보여줍니다.
        통합 지수는 과거 평균을 0으로 놓은 상대값이라, 양수면 그동안보다 낙관·음수면 우려 쪽입니다.
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
              <div className="sub2" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span>신뢰도</span>
                <b style={{ color: conf.color }}>{conf.label}</b>
                <span style={{ opacity: 0.7 }}>· {conf.why}</span>
              </div>
              <div className="sub2">
                Fed <N v={last.fed} /> · 뉴스 <N v={last.news} /> 를 1:1 로 결합
              </div>
              <div className="sub2">최근 {series.length}일 흐름</div>
            </div>
            <Spark values={series} />
          </div>
          <div className="note">
            연준 문서(성명문·회의록·기자회견을 같은 비중으로 합친 값)와 경제뉴스를 1:1 로
            결합한 지수입니다. <b>0이 과거 평균</b>이고, 양수면 그동안보다 낙관, 음수면
            우려 쪽이라는 뜻입니다. 시장 전망이나 투자 판단의 근거가 아닙니다.{" "}
            {conf.label === "낮음" && (
              <b>수집된 기사가 적은 날은 지수가 크게 흔들릴 수 있어 신호를 내지 않습니다.</b>
            )}
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
          <div className="pad" style={{ paddingTop: 10, paddingBottom: 6 }}>
            {/* S&P 500 — 대표 지표는 크게, 52주 범위까지 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
              <div>
                <div style={{ fontSize: 13, color: "var(--ink-2)" }}>S&P 500</div>
                <div className="num" style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.25 }}>
                  {indicators[0][1] == null ? "—"
                    : indicators[0][1].toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: 13 }}><N v={indicators[0][2]} d={2} suffix="%" /></div>
              </div>
              <Spark values={hist("spx")} w={124} h={52} color="var(--blue)" zero={false} dot />
            </div>
            {wk52 && (
              <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 6 }}>
                52주 최고 <span className="num">{wk52.hi.toLocaleString()}</span>
                {" · "}최저 <span className="num">{wk52.lo.toLocaleString()}</span>
              </div>
            )}
            <div style={{ borderTop: "1px solid var(--line)", margin: "12px 0 4px" }} />
            {[
              ["VIX 변동성", "vix", indicators[1][1], indicators[1][2], "pt", ""],
              ["미 국채 2년", "ust2y", indicators[2][1], indicators[2][2], "%p", "%"],
              ["미 국채 10년", "ust10y", indicators[3][1], indicators[3][2], "%p", "%"],
              ["장단기 금리차", "spread", indicators[4][1], indicators[4][2], "%p", "%p"],
            ].map(([name, key, v, c, cs, vs]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between",
                                      alignItems: "center", gap: 10, padding: "7px 0" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, color: "var(--ink-2)", whiteSpace: "nowrap" }}>{name}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span className="num" style={{ fontSize: 15.5, fontWeight: 600 }}>
                      {v == null ? "—" : `${v.toLocaleString(undefined, { minimumFractionDigits: 2 })}${vs}`}
                    </span>
                    <span style={{ fontSize: 12.5 }}><N v={c} d={2} suffix={cs} /></span>
                  </div>
                </div>
                <Spark values={hist(key)} w={96} h={34} color="var(--blue)" zero={false} dot />
              </div>
            ))}
          </div>
          <div className="note">기준일 {m.date} · 그래프는 최근 1년 흐름</div>
        </div>

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
