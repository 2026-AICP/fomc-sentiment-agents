"""Phase 7 최소 뼈대 — LangGraph 3노드 (Collector → Analyst → Reporting).

검증된 도구(scrape·sentiment·aggregate·report)를 노드로 감싼 배선 확인용.
배관(그래프가 처음부터 끝까지 도나)만 본다. 기본은 더미 엔진(오프라인·결정적).
확장: Market Comparison·Strategy 노드 추가, Orchestrator(재시도·에러).

실행:  python3 agents/graph.py                    # 더미로 배선 확인
       SENTIMENT_ENGINE=finbert python3 agents/graph.py 2025-01-29
"""
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db
from engine.preprocess import split_sentences
from index.aggregate import aggregate_meeting
from reports.report import write_report

# 엔진 선택 (기본 더미 — 배선 확인용, 모델 불필요)
if os.getenv("SENTIMENT_ENGINE", "dummy").lower() == "finbert":
    from engine.sentiment import analyze, MODEL_TAG
else:
    from engine.dummy_sentiment import analyze, MODEL_TAG

DB = ROOT / "data" / "agent_skeleton.db"
REPORTS = ROOT / "reports" / "agent_out"


# ── 에이전트 간 주고받는 상태 ──
class State(TypedDict):
    date: str
    statement_path: str
    n_sentences: int
    index: dict
    report_path: str
    log: list


# ── 노드 ① Data Collector: 성명문 파일 확보 ──
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


# ── 노드 ② Sentiment Analyst: 감성 → 인덱스(DB) ──
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
        sid = f"{doc_id}#{idx}#{MODEL_TAG}"
        conn.execute("INSERT OR REPLACE INTO sentences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, date, doc_id, "statement", "Statement", idx, s,
                      r["p_pos"], r["p_neu"], r["p_neg"], r["score"], r["entropy"], MODEL_TAG))
    for row in aggregate_meeting(conn, date, MODEL_TAG):
        conn.execute("INSERT OR REPLACE INTO meetings VALUES (?,?,?,?,?)", row)
    conn.commit()
    idx_vals = {m: (v, c) for _, m, g, v, c in
                conn.execute("SELECT * FROM meetings WHERE date=? AND granularity='meeting'", (date,))}
    conn.close()

    state["n_sentences"] = len(sents)
    state["index"] = {m: round(v, 4) for m, (v, c) in idx_vals.items()}
    state["log"].append(f"[analyst] {len(sents)}문장 → index {state['index']}")
    return state


# ── 노드 ③ Strategy & Reporting: 보고서 ──
def reporting_node(state: State) -> State:
    conn = db.connect(DB)
    path = write_report(conn, state["date"], REPORTS)
    conn.close()
    state["report_path"] = str(path)
    state["log"].append(f"[reporting] {path.name}")
    return state


# ── 그래프 배선 ──
def build_graph():
    g = StateGraph(State)
    g.add_node("collector", collector_node)
    g.add_node("analyst", analyst_node)
    g.add_node("reporting", reporting_node)
    g.set_entry_point("collector")
    g.add_edge("collector", "analyst")
    g.add_edge("analyst", "reporting")
    g.add_edge("reporting", END)
    return g.compile()


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2025-01-29"
    app = build_graph()
    print(f"엔진: {MODEL_TAG} | 대상 회의: {date}\n")
    result = app.invoke({"date": date, "statement_path": "", "n_sentences": 0,
                         "index": {}, "report_path": "", "log": []})
    print("── 에이전트 흐름 ──")
    for line in result["log"]:
        print(" ", line)
    print(f"\n최종: {result['n_sentences']}문장 → 보고서 {Path(result['report_path']).name if result['report_path'] else '(없음)'}")
