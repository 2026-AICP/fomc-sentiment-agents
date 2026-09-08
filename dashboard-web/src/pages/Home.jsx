import {
  useJson, fmt, gradeInfo, confidenceLevel, firedNames, FIRED_KO,
} from "../lib/data";

/** 부호에 따라 색을 주는 숫자. 값이 없으면 '—'. */
function N({ v, d = 3, suffix = "" }) {
  if (v == null) return <span className="na">—</span>;
  return <span className={`num ${v > 0 ? "pos" : v < 0 ? "neg" : ""}`}>{fmt(v, d)}{suffix}</span>;
}

const sign = (v) => (v > 0 ? 1 : v < 0 ? -1 : 0);

/** 초소형 추세 그래프 — Summary 페이지와 같은 그리기 방식. */
function Spark({ values, w = 168, h = 46, color = "var(--accent)", zero = true }) {
  if (!values?.length) return null;
  const lo = Math.min(...values), hi = Math.max(...values), rng = hi - lo || 1;
  const y = (v) => h - 4 - ((v - lo) / rng) * (h - 8);
  const px = (i) => 2 + (i / (values.length - 1)) * (w - 4);
  const pts = values.map((v, i) => `${px(i)},${y(v)}`).join(" ");
  const lastX = px(values.length - 1), lastY = y(values[values.length - 1]);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" style={{ flexShrink: 0 }}>
      {zero && lo < 0 && hi > 0 && (
        <line x1="0" y1={y(0)} x2={w} y2={y(0)} stroke="var(--line)" strokeDasharray="3 3" />
      )}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8"
        strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r="2.4" fill={color} />
    </svg>
  );
}

const SIGNAL_CODES = ["tone_shift", "divergence", "tone_vs_vix", "tone_vs_rate"];

export default function Home() {
  const { data: dsAll } = useJson("daily_signals");     // 일별 통합 신호 (헤드라인의 근거)
  const { data: combined } = useJson("daily_headline");  // 통합 감성지수 = Fed:뉴스 1:1
  const { data: market } = useJson("market");
  const { data: meetings } = useJson("meetings");
  const { data: minutes } = useJson("minutes");
  const { data: presser } = useJson("presser");
  const { data: meta } = useJson("meta");

  if (!dsAll?.length || !combined?.length || !market?.length || !meetings?.length || !meta)
    return <div className="loading">데이터 로딩…</div>;

  // ── 1단: 신호 (헤드라인) — 오늘의 결론 ──
  const ds = dsAll[dsAll.length - 1];
  const gi = gradeInfo(ds.grade);
  const emoji = (ds.grade || "").split(" ")[0] || "⚪";
  const mkt = market.find((r) => r.date === ds.date) || market[market.length - 1];
  const reaction = mkt?.spx_ret ?? null;

  // ── 2단: 근거 — 통합 감성지수 ↔ 시장 반응, 짝으로 배치 ──
  const comb = combined.find((r) => r.date === ds.date) || combined[combined.length - 1];
  const combSeries = combined.map((r) => r.index).filter((v) => v != null).slice(-30);

  const asOf = new Date(mkt.date);
  const yearAgo = new Date(asOf); yearAgo.setDate(yearAgo.getDate() - 365);
  const cut = yearAgo.toISOString().slice(0, 10);
  const hist = (key) => market.filter((r) => r.date >= cut).map((r) => r[key]).filter((v) => v != null);

  const divergenceFired = ds.fired.includes("divergence");
  const sameSign = sign(ds.index) !== 0 && sign(ds.index) === sign(reaction);
  const conn = divergenceFired
    ? { icon: "⇄", color: "var(--crit)", label: "부호 반대 · 괴리" }
    : sameSign
      ? { icon: "✓", color: "var(--up)", label: "부호 일치" }
      : { icon: "≈", color: "var(--muted)", label: "부호 불일치 또는 크기 미달" };

  // ── 3단: 세부 구성 지표 — Fed 축 상세는 가장 최근 FOMC 회의 기준 ──
  const lastMeet = meetings[meetings.length - 1];
  const lastMn = minutes?.find((r) => r.date === lastMeet.date);
  const lastPr = presser?.find((r) => r.date === lastMeet.date);
  const conf = confidenceLevel(ds.n_articles, ds.ci_lo, ds.ci_hi);

  const recent = (key) => {
    const out = [];
    for (let i = market.length - 1; i >= 0 && out.length < 2; i--) {
      if (market[i][key] != null) out.push(market[i][key]);
    }
    return out;
  };
  const chg = (key) => {
    const [v, prev] = recent(key);
    return v != null && prev != null ? Math.round((v - prev) * 1000) / 1000 : null;
  };

  return (
    <>
      <h1>오늘의 신호</h1>
      <p className="sub">
        연준의 어조와 시장 반응을 비교해 매일 하나의 결론(신호)을 냅니다. 그 아래 두 근거
        (통합 감성지수·시장 반응)를 나란히, 세부 구성 지표는 더 아래에 배치했습니다.
      </p>

      {/* TIER 1 — 신호 */}
      <div className="card hero-signal">
        <div className="grade-badge" style={{
          borderColor: gi.color, color: gi.color,
          background: `color-mix(in srgb, ${gi.color} 8%, transparent)`,
        }}>
          <div className="em">{emoji}</div>
          <div className="lb">{gi.label}</div>
        </div>
        <div className="hero-body">
          <div className="hero-date">{ds.date}</div>
          <div className="hero-why">
            톤 <N v={ds.index} /> · 시장 반응 <N v={reaction} d={2} suffix="%" /> ·{" "}
            {ds.fired.length ? `발동 규칙: ${firedNames(ds.fired)}` : "발동한 규칙 없음"}
          </div>
          <div className="fired-chips">
            {SIGNAL_CODES.map((code) => {
              const on = ds.fired.includes(code);
              return (
                <span key={code} className="fchip" style={on ? {
                  borderColor: `color-mix(in srgb, ${gi.color} 40%, transparent)`,
                  background: `color-mix(in srgb, ${gi.color} 10%, transparent)`, color: gi.color,
                } : undefined}>
                  {on ? "●" : "○"} {FIRED_KO[code]}
                </span>
              );
            })}
          </div>
          {ds.gate_reason && (
            <div className="gate-note" style={{
              color: "var(--warn)", background: "color-mix(in srgb, var(--warn) 8%, transparent)",
              border: "1px solid color-mix(in srgb, var(--warn) 28%, transparent)",
            }}>
              ⚙ 신뢰도 게이트 — {ds.gate_reason}. 지수·톤 값은 그대로 두고 경보만 낮췄습니다.
            </div>
          )}
        </div>
      </div>

      {/* TIER 2 — 근거: 통합 감성지수 ↔ 시장 반응 */}
      <div className="evidence-grid">
        <div className="card">
          <div className="ev-pad">
            <div className="ev-lbl">통합 감성지수 (Fed:뉴스 = 1:1)</div>
            <div className={`ev-big num ${ds.index > 0 ? "pos" : ds.index < 0 ? "neg" : ""}`}>
              {fmt(ds.index)}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
              Fed <N v={comb?.fed} /> · 뉴스 <N v={comb?.news_z ?? comb?.news} />
            </div>
            <div className="ev-foot">
              <div style={{ fontSize: 12.5, color: "var(--muted)" }}>최근 {combSeries.length}일 흐름</div>
              <Spark values={combSeries} color="var(--accent)" />
            </div>
          </div>
        </div>

        <div className="connector">
          <div className="cline" />
          <div className="cbadge" style={{
            borderColor: conn.color, color: conn.color,
            background: `color-mix(in srgb, ${conn.color} 8%, transparent)`,
          }}>{conn.icon}</div>
          <div className="clabel">{conn.label}</div>
          <div className="cline" />
        </div>

        <div className="card">
          <div className="ev-pad">
            <div className="ev-lbl">시장 반응 (S&amp;P 500)</div>
            <div className={`ev-big num ${reaction > 0 ? "pos" : reaction < 0 ? "neg" : ""}`}>
              {reaction == null ? "—" : `${fmt(reaction, 2)}%`}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
              종가 {mkt.spx?.toLocaleString(undefined, { minimumFractionDigits: 2 }) ?? "—"}
            </div>
            <div className="ev-foot">
              <div style={{ fontSize: 12.5, color: "var(--muted)" }}>최근 1년 흐름</div>
              <Spark values={hist("spx")} color="var(--blue)" zero={false} />
            </div>
          </div>
        </div>
      </div>
      <div className="note">
        원형 배지는 통합 감성지수와 S&amp;P500 반응의 방향이 같은지(✓)·반대인지(⇄)를 보여줍니다.
        신호는 매수·매도 권고가 아니라 어조와 시장 반응이 어긋난 날을 표시하는 참고 정보입니다.
      </div>

      {/* TIER 3 — 세부 구성 지표 */}
      <h2 className="sec">세부 구성 지표</h2>
      <div className="detail-grid">
        <div className="card dcard ev-pad">
          <h3>Fed 축 상세 · {lastMeet.date} 회의</h3>
          <div className="drow"><span>성명문</span><N v={lastMeet.tone} /></div>
          <div className="drow"><span>회의록</span><N v={lastMn?.minutes} /></div>
          <div className="drow"><span>기자회견</span><N v={lastPr?.presser} /></div>
        </div>
        <div className="card dcard ev-pad">
          <h3>뉴스 감성 신뢰도</h3>
          <div className="drow"><span>기사 수</span><span>{ds.n_articles ?? "—"}건</span></div>
          <div className="drow"><span>신뢰구간(CI)</span>
            <span className="num">[{fmt(ds.ci_lo, 2)}, {fmt(ds.ci_hi, 2)}]</span></div>
          <div className="drow"><span>판정</span>
            <b style={{ color: conf.color, fontSize: 12.5 }}>{conf.label}</b></div>
        </div>
        <div className="card dcard ev-pad">
          <h3>보조 시장지표</h3>
          <div className="drow"><span>VIX (전일비)</span>
            <span>{mkt.vix ?? "—"} (<N v={mkt.vix_chg ?? chg("vix")} d={2} suffix="pt" />)</span></div>
          <div className="drow"><span>국채 2년 (전일비)</span>
            <span>{mkt.ust2y ?? "—"}% (<N v={chg("ust2y")} d={2} suffix="%p" />)</span></div>
          <div className="drow"><span>장단기 스프레드</span><span>{mkt.spread ?? "—"}%p</span></div>
        </div>
      </div>
    </>
  );
}
