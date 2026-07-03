"""Phase 7 멀티에이전트 (LangGraph 5노드).

검증된 도구를 노드로 감싼 배선:
  Collector → Analyst → Market → Strategy → Reporting
  (scrape)   (sentiment  (collect  (signals)  (report)
              ·aggregate) _market)

기본은 더미 엔진(오프라인·결정적)으로 배관 검증. Market 노드는 네트워크(yfinance)
필요 — 실패 시 경고 후 계속(그래프는 관통). 확장: Orchestrator(재시도·라우팅).

실행:  python3 agents/graph.py                    # 더미
       SENTIMENT_ENGINE=finbert python3 agents/graph.py 2025-01-29
"""
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db
from engine.preprocess import split_sentences
from index.aggregate import aggregate_meeting
from reports.report import write_report
from analysis.signals import (signal_tone_shift, signal_divergence,
                              signal_tone_vs_vix, grade)
from analysis import collect_market as cm

if os.getenv("SENTIMENT_ENGINE", "dummy").lower() == "finbert":
    from engine.sentiment import analyze, MODEL_TAG
else:
    from engine.dummy_sentiment import analyze, MODEL_TAG

DB = ROOT / "data" / "agent_skeleton.db"
REPORTS = ROOT / "reports" / "agent_out"


class State(TypedDict):
    date: str
    statement_path: str
    n_sentences: int
    index: dict
    market: dict
    signals: dict
    report_path: str
    log: list


# ── ① Data Collector ──
def collector_node(state: State) -> State:
    date = state["date"]
    for d in (ROOT / "data" / "statements", ROOT / "tests" / "fixtures"):
        hits = list(d.glob(f"FOMC_*{date}*.txt"))
        if hits:
            state["statement_path"] = str(hits[0])
            state["log"].append(f"[collector] found {hits[0].name}")
            return state
    state["log"].append(f"[collector] {date} 성명문 없음")
    return state


# ── ② Sentiment Analyst ──
def analyst_node(state: State) -> State:
    path = Path(state["statement_path"])
    text = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()[:10]
    date = state["date"]
    doc_id = f"{date}_statement"
    now = datetime.now(timezone.utc).isoformat()

    conn = db.connect(DB)
    db.init_db(conn)
    conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?)",
                 (doc_id, date, "statement", str(path), sha, now))
    sents = split_sentences(text)
    for idx, s in enumerate(sents):
        r = analyze(s)
        conn.execute("INSERT OR REPLACE INTO sentences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"{doc_id}#{idx}#{MODEL_TAG}", date, doc_id, "statement", "Statement", idx, s,
                      r["p_pos"], r["p_neu"], r["p_neg"], r["score"], r["entropy"], MODEL_TAG))
    for row in aggregate_meeting(conn, date, MODEL_TAG):
        conn.execute("INSERT OR REPLACE INTO meetings VALUES (?,?,?,?,?)", row)
    conn.commit()
    idx_vals = {m: v for _, m, g, v, c in
                conn.execute("SELECT * FROM meetings WHERE date=? AND granularity='meeting'", (date,))}
    conn.close()
    state["n_sentences"] = len(sents)
    state["index"] = {m: round(v, 4) for m, v in idx_vals.items()}
    state["log"].append(f"[analyst] {len(sents)}문장 → index {state['index']}")
    return state


# ── ③ Market Comparison ──
def market_node(state: State) -> State:
    date = state["date"]
    conn = db.connect(DB); db.init_db(conn)
    try:
        full = cm.download_full_range([date])
        full = cm.compute_derived_global(full)
        win = cm.slice_windows(full, [date])
        cm.upsert_market(conn, win)
        state["log"].append(f"[market] {len(win)}거래일 적재")
    except Exception as e:
        state["log"].append(f"[market] 다운로드 생략(오프라인?): {str(e)[:35]}")
    row = conn.execute("SELECT spx_ret_cc, vix_chg, vix FROM market WHERE date=?", (date,)).fetchone()
    conn.close()
    if row:
        state["market"] = {"spx_ret_cc": row[0], "vix_chg": row[1], "vix": row[2]}
    state["log"].append(f"[market] 반응 {state['market'] or '(없음)'}")
    return state


# ── ④ Strategy (신호) ──
def strategy_node(state: State) -> State:
    date = state["date"]
    tone = state["index"].get("conf_weighted")
    reaction = state["market"].get("spx_ret_cc")
    vix_chg = state["market"].get("vix_chg")
    conn = db.connect(DB)
    prev = conn.execute(
        "SELECT index_value FROM meetings WHERE method='conf_weighted' "
        "AND granularity='meeting' AND date<? ORDER BY date DESC LIMIT 1", (date,)).fetchone()
    conn.close()
    prev_tone: Optional[float] = prev[0] if prev else None

    sigs = [signal_tone_shift(prev_tone, tone),
            signal_divergence(tone, reaction),
            signal_tone_vs_vix(tone, vix_chg)]
    g = grade(sigs, tone, reaction)
    fired = [s.name for s in sigs if s.fired]
    state["signals"] = {"grade": g, "fired": fired}
    state["log"].append(f"[strategy] 등급 {g} | 발동 {fired or '없음'}")
    return state


# ── ⑤ Reporting ──
def reporting_node(state: State) -> State:
    conn = db.connect(DB)
    path = write_report(conn, state["date"], REPORTS)
    conn.close()
    state["report_path"] = str(path)
    state["log"].append(f"[reporting] {path.name}")
    return state


def build_graph():
    g = StateGraph(State)
    for name, fn in [("collector", collector_node), ("analyst", analyst_node),
                     ("market", market_node), ("strategy", strategy_node),
                     ("reporting", reporting_node)]:
        g.add_node(name, fn)
    g.set_entry_point("collector")
    g.add_edge("collector", "analyst")
    g.add_edge("analyst", "market")
    g.add_edge("market", "strategy")
    g.add_edge("strategy", "reporting")
    g.add_edge("reporting", END)
    return g.compile()


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2025-01-29"
    app = build_graph()
    print(f"엔진: {MODEL_TAG} | 대상 회의: {date}\n── 5-에이전트 흐름 ──")
    result = app.invoke({"date": date, "statement_path": "", "n_sentences": 0,
                         "index": {}, "market": {}, "signals": {}, "report_path": "", "log": []})
    for line in result["log"]:
        print(" ", line)
    print(f"\n최종: {result['n_sentences']}문장 | 등급 {result['signals'].get('grade','?')} "
          f"| 보고서 {Path(result['report_path']).name if result['report_path'] else '(없음)'}")
