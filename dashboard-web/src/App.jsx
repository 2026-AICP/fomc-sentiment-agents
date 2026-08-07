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
  const a = mk[mk.length - 1], b = mk[mk.length - 2];
  const d = (x, y) => (x == null || y == null ? null : Math.round((x - y) * 100) / 100);
  const items = [
    { n: "S&P 500", v: a.spx?.toLocaleString(undefined, { minimumFractionDigits: 2 }), c: a.spx_ret, s: "%" },
    { n: "VIX", v: a.vix?.toFixed(2), c: a.vix_chg, s: "" },
    { n: "미 국채 2년", v: a.ust2y?.toFixed(2) + "%", c: d(a.ust2y, b.ust2y), s: "%p" },
    { n: "미 국채 10년", v: a.ust10y?.toFixed(2) + "%", c: d(a.ust10y, b.ust10y), s: "%p" },
    { n: "장단기 스프레드", v: a.spread?.toFixed(2) + "%p", c: d(a.spread, b.spread), s: "%p" },
  ];
  return (
    <div className="ticker">
      <div className="wrap">
        {items.map((it) => (
          <div className="tk" key={it.n}>
            <span className="tk-n">{it.n}</span>
            <span className="tk-v">{it.v}</span>
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
          <span>FOMC 성명문 · 회의록 · 기자회견 감성 분석</span>
          <span>데이터 자동 갱신 07:00 KST{updated ? ` · 최근 ${updated}` : ""}</span>
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
          <span>데이터: 연방준비제도 공개문서 · 시장 공개데이터</span>
          <span>규칙 기반 · LLM 미사용 · 재현 가능</span>
          <span>참고용 · 투자조언 아님</span>
        </div>
      </footer>
    </>
  );
}
