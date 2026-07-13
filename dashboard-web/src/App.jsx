import { useState } from "react";
import Overview from "./pages/Overview";
import Signals from "./pages/Signals";
import News from "./pages/News";
import Divergence from "./pages/Divergence";
import Presser from "./pages/Presser";
import Method from "./pages/Method";

const PAGES = [
  { key: "overview", label: "📊 대시보드", el: <Overview /> },
  { key: "signals", label: "🚦 신호", el: <Signals /> },
  { key: "news", label: "✦ News 축", el: <News /> },
  { key: "divergence", label: "🚩 괴리 검증", el: <Divergence /> },
  { key: "presser", label: "🎙 기자회견", el: <Presser /> },
  { key: "method", label: "🔬 방법론·한계", el: <Method /> },
];

export default function App() {
  const [page, setPage] = useState("overview");
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="mk">S</div>
          <div>
            <div className="t1">SentiBoard</div>
            <div className="t2">FOMC 감성·신호</div>
          </div>
        </div>
        {PAGES.map((p) => (
          <button key={p.key} className={`nav-btn${page === p.key ? " active" : ""}`}
            onClick={() => setPage(p.key)}>
            {p.label}
          </button>
        ))}
        <div className="side-note">
          규칙 기반 · LLM 미사용<br />
          모든 수치·신호는 파이프라인에서 직접. 재현·감사 가능. <b>예측이 아닌 경향.</b>
        </div>
      </aside>
      <main className="main">{PAGES.find((p) => p.key === page).el}</main>
    </div>
  );
}
