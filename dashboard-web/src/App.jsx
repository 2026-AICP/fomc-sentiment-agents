import { useState } from "react";
import { useJson, fmt } from "./lib/data";
import Home from "./pages/Home";
import Overview from "./pages/Overview";
import Signals from "./pages/Signals";
import News from "./pages/News";
import Market from "./pages/Market";
import Divergence from "./pages/Divergence";
import Presser from "./pages/Presser";
import Minutes from "./pages/Minutes";
import Method from "./pages/Method";

// 상단 가로 내비 — 경제정보 사이트 구조(좌측 사이드바 아님).
// 라벨은 이모지 없이, 방문자가 아는 말로.
const PAGES = [
  { key: "home", label: "홈", el: <Home /> },
  { key: "overview", label: "감성지수", el: <Overview /> },
  { key: "minutes", label: "회의록", el: <Minutes /> },
  { key: "presser", label: "기자회견", el: <Presser /> },
  { key: "signals", label: "신호", el: <Signals /> },
  { key: "news", label: "뉴스", el: <News /> },
  { key: "market", label: "시장지표", el: <Market /> },
  { key: "divergence", label: "괴리 검증", el: <Divergence /> },
  { key: "method", label: "방법론", el: <Method /> },
];

/** 시세 티커 — 최신 거래일 종가와 전일비. 시장 데이터가 없으면 렌더하지 않는다. */
function Ticker() {
  const { data: mk } = useJson("market");
  if (!mk || mk.length < 2) return null;

  // 항목마다 **가장 최근의 유효값 2개**를 뒤에서부터 찾는다.
  // 마지막 행만 보면, 그날 못 받은 항목(예: 국채금리 결측)이 빈 값으로 나온다.
  const recent = (key, n = 2) => {
    const out = [];
    for (let i = mk.length - 1; i >= 0 && out.length < n; i--) {
      if (mk[i][key] != null) out.push(mk[i][key]);
    }
    return out;
  };
  const last = mk[mk.length - 1];
  const round2 = (x) => Math.round(x * 100) / 100;
  // 값·전일비를 함께 만든다. 값이 아예 없으면 null → 화면엔 "—".
  const field = (key, { fixed = 2, suffix = "", chgKey = null } = {}) => {
    const [v, prev] = recent(key);
    const c = chgKey ? last[chgKey] : (v != null && prev != null ? round2(v - prev) : null);
    return { v: v == null ? null : v.toFixed(fixed) + suffix, c };
  };
  const items = [
    { n: "S&P 500", ...field("spx", { chgKey: "spx_ret" }), s: "%",
      v: last.spx?.toLocaleString(undefined, { minimumFractionDigits: 2 }) ?? null },
    { n: "VIX", ...field("vix", { chgKey: "vix_chg" }), s: "" },
    { n: "미 국채 2년", ...field("ust2y", { suffix: "%" }), s: "%p" },
    { n: "미 국채 10년", ...field("ust10y", { suffix: "%" }), s: "%p" },
    { n: "장단기 스프레드", ...field("spread", { suffix: "%p" }), s: "%p" },
  ];
  return (
    <div className="ticker">
      <div className="wrap">
        {items.map((it) => (
          <div className="tk" key={it.n}>
            <span className="tk-n">{it.n}</span>
            <span className="tk-v">{it.v ?? "—"}</span>
            <span className={`num ${it.c > 0 ? "pos" : it.c < 0 ? "neg" : ""}`}>
              {it.c == null ? "—" : `${fmt(it.c, 2)}${it.s}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("home");
  const { data: meta } = useJson("meta");
  const updated = meta?.generated_at?.slice(0, 10);

  return (
    <>
      <div className="util">
        <div className="wrap">
          <span>연준 문서와 경제뉴스의 감성 분석</span>
          <span>매일 오전 7시 업데이트{updated ? ` · 최근 ${updated}` : ""}</span>
          <span className="right">2026-AICP · Econpilot</span>
        </div>
      </div>

      <header className="site-head">
        <div className="wrap">
          <div className="brand">Econ<span>pilot</span></div>
          <nav className="top">
            {PAGES.map((p) => (
              <button key={p.key} className={page === p.key ? "on" : ""}
                onClick={() => setPage(p.key)}>
                {p.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <Ticker />

      <main className="main">
        <div className="wrap">{PAGES.find((p) => p.key === page).el}</div>
      </main>

      <footer className="site-foot">
        <div className="wrap">
          <span>2026-AICP · Econpilot</span>
          <span>자료: 연방준비제도 공개 문서, 시장 공개 데이터</span>
          <span>모든 수치는 고정된 규칙으로 계산되며 전 과정을 재현할 수 있습니다.</span>
          <span>본 사이트의 지수와 신호는 공개 문서를 분석한 참고 정보이며, 투자 자문이 아닙니다.</span>
        </div>
      </footer>
    </>
  );
}
