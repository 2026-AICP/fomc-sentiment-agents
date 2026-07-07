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
                              signal_tone_vs_vix, signal_tone_vs_rate, grade)
from analysis import collect_market as cm
from analysis.analyze_alignment import get_reaction, get_ust2y_change, REACTION_OFFSET
from analysis.news_index_live import index_for_window
from analysis.headline import combine

if os.getenv("SENTIMENT_ENGINE", "dummy").lower() == "finbert":
    from engine.sentiment import analyze, MODEL_TAG
else:
    from engine.dummy_sentiment import analyze, MODEL_TAG

DB = ROOT / "data" / "agent_skeleton.db"
REPORTS = ROOT / "reports" / "agent_out"
DAILY_SIGNALS = ROOT / "outputs" / "daily_signals.csv"


class State(TypedDict):
    date: str
    statement_path: str
    n_sentences: int
    index: dict
    news: dict
    headline: dict
    market: dict
    signals: dict
    report_path: str
    log: list
    errors: list


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
    try:
        return _analyst(state)
    except Exception as e:
        state["errors"].append(f"analyst: {e}")
        state["log"].append(f"[analyst] 오류: {str(e)[:40]}")
        return state


def _analyst(state: State) -> State:
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


# ── ②b News Analyst + Combine (headline) ──
def news_node(state: State) -> State:
    """발표일 주변 뉴스로 News 지수 산출 후 Fed 지수와 통합(headline).

    실시간 뉴스가 없으면(과거 회의) News=없음 → headline=Fed 단독 폴백.
    """
    date = state["date"]
    if not state["index"]:                       # 일별 모드(analyst 건너뜀) → Fed 톤 이월
        from analysis.analyze_alignment import fed_tone_asof
        conn = db.connect(DB); db.init_db(conn)
        carry = fed_tone_asof(conn, date)
        conn.close()
        if carry is not None:
            state["index"] = {"conf_weighted": round(carry, 4)}
            state["log"].append(f"[news] Fed 이월 {carry:+.3f} (일별 모드)")
    fed = state["index"].get("conf_weighted") if state["index"] else None
    before = int(os.getenv("NEWS_WINDOW_BEFORE", "3"))
    after = int(os.getenv("NEWS_WINDOW_AFTER", "1"))
    try:
        news = index_for_window(center=date, before=before, after=after)
    except Exception as e:
        news = None
        state["log"].append(f"[news] 뉴스 지수 생략: {str(e)[:35]}")
    if news:
        state["news"] = news
        state["log"].append(f"[news] News {news['conf_weighted']:+.3f} (기사 {news['n_articles']}건)")
    else:
        state["log"].append("[news] 해당 기간 실시간 뉴스 없음 → Fed 단독")
    h = combine(fed, news["conf_weighted"] if news else None)
    if h:
        state["headline"] = h
        state["log"].append(f"[news] headline {h['headline']:+.3f} ({h['method']})")
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
    # 통합 에이전트는 라이브(당일=offset=0)로 비교 — 오늘 톤 vs 오늘 시장.
    # (offset=1 회의 백테스트는 analysis/signals.py main 에서 별도 유지.)
    reac = get_reaction(conn, date, 0)               # 당일(offset=0)
    rate_chg = get_ust2y_change(conn, date, 0)       # 2년물 변화; 데이터 없으면 None(신호 D 미발동)
    if reac:
        rdate, spx, vixc = reac
        vlv = conn.execute("SELECT vix FROM market WHERE date=?", (rdate,)).fetchone()
        state["market"] = {"spx_ret_cc": spx, "vix_chg": vixc,
                           "vix": vlv[0] if vlv else None, "ust2y_chg": rate_chg,
                           "reaction_date": rdate}
    conn.close()
    state["log"].append(f"[market] 반응 {state['market'] or '(없음)'}")
    return state


# ── ④ Strategy (신호) ──
def strategy_node(state: State) -> State:
    if not state["index"]:
        state["log"].append("[strategy] 인덱스 없음 → 건너뜀")
        return state
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
            signal_tone_vs_vix(tone, vix_chg),
            signal_tone_vs_rate(tone, state["market"].get("ust2y_chg"))]
    g = grade(sigs, tone, reaction)
    fired = [s.name for s in sigs if s.fired]
    state["signals"] = {"grade": g, "fired": fired}
    state["log"].append(f"[strategy] 등급 {g} | 발동 {fired or '없음'}")
    return state


# ── ⑤ Reporting ──
def append_daily_signal(rec: dict, out=None):
    """일별 신호 1행 누적(같은 날짜는 덮어쓰기). 최신일이 마지막 행 → 대시보드·기록용."""
    import csv
    out = Path(out or DAILY_SIGNALS)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if out.exists():
        for r in csv.DictReader(open(out, encoding="utf-8")):
            rows[r["date"]] = r
    rows[rec["date"]] = {"date": rec["date"], "grade": rec["grade"],
                         "index": round(rec.get("index") or 0.0, 4),
                         "fired": ";".join(rec.get("fired") or [])}
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "grade", "index", "fired"])
        w.writeheader()
        for d in sorted(rows):
            w.writerow(rows[d])


def reporting_node(state: State) -> State:
    conn = db.connect(DB)
    path = write_report(conn, state["date"], REPORTS,
                        news=state.get("news") or None,
                        headline=state.get("headline") or None)
    conn.close()
    state["report_path"] = str(path)
    append_daily_signal({"date": state["date"],
                         "grade": state["signals"].get("grade", "—"),
                         "index": (state["index"] or {}).get("conf_weighted"),
                         "fired": state["signals"].get("fired", [])})
    state["log"].append(f"[reporting] {path.name} + daily_signals.csv")
    return state


def route_after_collect(state: State) -> str:
    """성명문 있으면 analyst(회의 모드), 없으면 news(일별 모드 — Fed 이월)."""
    return "analyst" if state["statement_path"] else "news"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("collector", collector_node), ("analyst", analyst_node),
                     ("news", news_node), ("market", market_node),
                     ("strategy", strategy_node), ("reporting", reporting_node)]:
        g.add_node(name, fn)
    g.set_entry_point("collector")
    g.add_conditional_edges("collector", route_after_collect,
                            {"analyst": "analyst", "news": "news"})
    g.add_edge("analyst", "news")
    g.add_edge("news", "market")
    g.add_edge("market", "strategy")
    g.add_edge("strategy", "reporting")
    g.add_edge("reporting", END)
    return g.compile()


def _init_state(date: str) -> dict:
    return {"date": date, "statement_path": "", "n_sentences": 0, "index": {},
            "news": {}, "headline": {}, "market": {}, "signals": {},
            "report_path": "", "log": [], "errors": []}


def _discover_local_dates(limit=None):
    """로컬 성명문 파일에서 회의 날짜 추출 (data/statements 우선, 없으면 fixtures)."""
    import re
    dates = set()
    for d in (ROOT / "data" / "statements", ROOT / "tests" / "fixtures"):
        for f in d.glob("FOMC_*.txt"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
            if m:
                dates.add(m.group(1))
    out = sorted(dates, reverse=True)
    return out[:limit] if limit else out


def orchestrate(dates=None, limit=None, retries=1, on_result=None):
    """Orchestrator: 여러 회의를 무인 일괄 처리. 실패 시 재시도·계속(배치 안 죽음).

    on_result(rec: dict): 회의 1건 끝날 때마다 호출(있으면). Phase 8 로깅용(선택).
    """
    import time
    if dates is None:
        dates = _discover_local_dates(limit)
    app = build_graph()
    results = []
    for date in dates:
        t0 = time.perf_counter()
        last_err = None
        for attempt in range(retries + 1):
            try:
                r = app.invoke(_init_state(date))
                grade = r["signals"].get("grade", "—")
                errs = r["errors"]
                status = "ok" if not errs else f"부분오류({len(errs)})"
                results.append((date, grade, status))
                print(f"  {date}  등급 {grade:<8} [{status}]")
                if on_result:
                    on_result({"date": date, "grade": grade, "status": status,
                               "ok": not errs, "errors": errs,
                               "duration_s": round(time.perf_counter() - t0, 2),
                               "model_tag": MODEL_TAG,
                               "report": r.get("report_path") or None})
                last_err = None
                break
            except Exception as e:                 # 그래프 레벨 실패 → 재시도
                last_err = str(e)
                if attempt < retries:
                    print(f"  {date}  재시도({attempt+1})...")
        if last_err:
            status = f"실패: {last_err[:30]}"
            results.append((date, None, status))
            print(f"  {date}  ❌ 실패: {last_err[:40]}")
            if on_result:
                on_result({"date": date, "grade": None, "status": status,
                           "ok": False, "errors": [last_err],
                           "duration_s": round(time.perf_counter() - t0, 2),
                           "model_tag": MODEL_TAG, "report": None})
    ok = sum(1 for _, _, s in results if s == "ok")
    print(f"\n무인 처리 완료: {len(results)}건 중 정상 {ok}건")
    return results


if __name__ == "__main__":
    # 배치(무인 다건):  python3 agents/graph.py --batch [N]
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        print(f"엔진: {MODEL_TAG} | Orchestrator 무인 일괄 처리\n── 회의별 결과 ──")
        orchestrate(limit=limit)
    else:
        # 단건:  python3 agents/graph.py [YYYY-MM-DD]
        date = sys.argv[1] if len(sys.argv) > 1 else "2025-01-29"
        app = build_graph()
        print(f"엔진: {MODEL_TAG} | 대상 회의: {date}\n── 5-에이전트 흐름 ──")
        result = app.invoke(_init_state(date))
        for line in result["log"]:
            print(" ", line)
        hl = result.get("headline") or {}
        hl_str = f" | headline {hl['headline']:+.3f}" if hl else ""
        print(f"\n최종: {result['n_sentences']}문장 | 등급 {result['signals'].get('grade','?')}"
              f"{hl_str} | 보고서 {Path(result['report_path']).name if result['report_path'] else '(없음)'}")
