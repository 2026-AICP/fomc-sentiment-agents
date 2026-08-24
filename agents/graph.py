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
from analysis.signals import (signal_tone_shift, signal_divergence, signal_tone_vs_vix,
                              signal_tone_vs_rate, grade, COMBINED_THRESHOLDS, GRADE_WATCH,
                              GRADE_CAUTION, GRADE_ALERT)
from analysis import collect_market as cm
from analysis.analyze_alignment import (get_reaction, get_ust2y_change, REACTION_OFFSET,
                                        fed_composite_asof, upsert_fed_composite)
from analysis.news_index_live import index_for_window, index_pre_post
from analysis.news_signals import confident as news_confident
from analysis.presser_index import presser_tone, has_presser
from analysis.minutes_index import minutes_tone, has_minutes
from analysis.headline import combine, combine_fed_axes
from analysis.axis_status import expected_axes

if os.getenv("SENTIMENT_ENGINE", "dummy").lower() == "finbert":
    from engine.sentiment import analyze, MODEL_TAG
else:
    from engine.dummy_sentiment import analyze, MODEL_TAG

DB = ROOT / "data" / "fomc.db"           # 통일 DB — pipeline·signals·collect_market 과 공유(이중 DB 제거)
REPORTS = ROOT / "reports" / "agent_out"
DAILY_SIGNALS = ROOT / "outputs" / "daily_signals.csv"


class State(TypedDict):
    date: str
    statement_path: str
    n_sentences: int
    index: dict
    news: dict
    pre_post: dict
    presser: dict
    minutes: dict
    fed_axes: Optional[list]
    fed_final: bool
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


def _fed_value_and_stats(idx):
    """state['index'] → (combine()에 넘길 fed 값, fed_stats).

    fed_composite(statement:presser:minutes 1:1:1 결합, docs/fed_weights.md)는 이미
    z-척도이므로 combine()이 다시 표준화(raw 통계로 재-z)하면 척도가 깨진다
    (예: composite -0.87 을 raw fed 평균 0.149/표준편차 0.1649 로 나누면 폭주).
    그래서 fed_stats=(0,1)을 줘서 combine() 내부 _z()가 값을 그대로 통과시키게 한다.
    fed_composite 가 없으면(레거시/에러) conf_weighted 원값 그대로 기본 표준화를 쓴다.
    """
    idx = idx or {}
    if "fed_composite" in idx:
        return idx["fed_composite"], (0.0, 1.0)
    return idx.get("conf_weighted"), None


# ── ②b News Analyst + Combine (headline) ──
def news_node(state: State) -> State:
    """발표일 주변 뉴스로 News 지수 산출 후 Fed 지수(3축 결합)와 통합(headline).

    실시간 뉴스가 없으면(과거 회의) News=없음 → headline=Fed 단독 폴백.
    """
    date = state["date"]
    if not state["index"]:                       # 일별 모드(analyst 건너뜀) → Fed 톤 이월
        conn = db.connect(DB); db.init_db(conn)
        carry = fed_composite_asof(conn, date)     # 확정판 > 속보치 > 레거시(statement 단독)
        conn.close()
        if carry is not None:                      # fed_composite_asof 는 항상 z-척도로 반환
            state["index"] = {"fed_composite": round(carry, 4)}
            state["log"].append(f"[news] Fed 이월 {carry:+.3f} (일별 모드)")

    # #4 Step 3(B1): FOMC일 & presser 트랜스크립트 있으면 성명문 vs presser 톤 괴리
    # (트랜스크립트는 회의 며칠 후 게시 → 그때 재실행 때 잡힘. 성명문과 같은 analyze 로 공정 비교.)
    if state["statement_path"] and has_presser(date):
        try:
            stmt = (state["index"] or {}).get("conf_weighted")
            pt = presser_tone(date, analyze=analyze)
            if pt and stmt is not None:
                gap = pt["conf_weighted"] - stmt
                state["presser"] = {"tone": pt["conf_weighted"], "statement_tone": stmt,
                                    "gap": gap, "n_sentences": pt["n_sentences"]}
                state["log"].append(
                    f"[news] 성명문 {stmt:+.3f} vs 기자회견 {pt['conf_weighted']:+.3f} (괴리 {gap:+.3f})")
        except Exception as e:
            state["log"].append(f"[news] presser 톤 생략: {str(e)[:35]}")
    # 회의록(minutes) 축 — 회의 3주 후 공개라, 그날 처리에는 대개 없다.
    # 미완성 회의 재방문(run_news_daily → pending_meetings)에서 나중에 채워진다.
    if state["statement_path"] and has_minutes(date):
        try:
            stmt = (state["index"] or {}).get("conf_weighted")
            mt = minutes_tone(date, analyze=analyze)
            if mt:
                state["minutes"] = {
                    "tone": mt["conf_weighted"], "statement_tone": stmt,
                    "gap": (mt["conf_weighted"] - stmt) if stmt is not None else None,
                    "n_sentences": mt["n_sentences"],
                    "sections": {c: s["conf_weighted"] for c, s in mt["sections"].items()},
                }
                gap_s = f" (괴리 {state['minutes']['gap']:+.3f})" if stmt is not None else ""
                state["log"].append(
                    f"[news] 회의록 톤 {mt['conf_weighted']:+.3f}{gap_s} · {mt['n_sentences']}문장")
        except Exception as e:
            state["log"].append(f"[news] 회의록 톤 생략: {str(e)[:35]}")

    # Fed 축 내부 결합(statement:presser:minutes=1:1:1, docs/fed_weights.md) — 회의일에만 계산.
    # 질문 6 피드백 "절충안" 채택: 속보치는 확정 전까지 갱신 가능(예: presser 며칠 후 도착)하되,
    # minutes 로 3축이 다 차면 확정판을 단 한 번만 기록하고 그 뒤로는 재작성하지 않는다
    # (analyze_alignment.upsert_fed_composite — 과거 실시간 값을 덮어쓰지 않는다는 원칙).
    if state["statement_path"]:
        stmt = (state["index"] or {}).get("conf_weighted")
        fc = combine_fed_axes(stmt, (state.get("presser") or {}).get("tone"),
                              (state.get("minutes") or {}).get("tone"))
        if fc:
            state["index"]["fed_composite"] = round(fc["fed_composite"], 4)
            state["fed_axes"] = fc["axes"]
            expected = len(expected_axes(date))
            # 확정 기준은 "minutes 포함 여부"다 — expected_axes()는 2011-04~2018 회의도
            # presser 를 기대하지만 실제로는 분기(SEP) 회의에만 있었다(has_presser 는 그
            # 경우 영원히 False). n_axes>=expected 로 판정하면 그런 회의는 minutes 가
            # 와도 영원히 확정되지 않는다 — minutes 는 유일하게 3주 지연되는 축이라
            # 도착 시점이 곧 "더 늦게 올 축이 없다"는 뜻이므로 이것만으로 충분하다.
            state["fed_final"] = "minutes" in fc["axes"]
            conn = db.connect(DB); db.init_db(conn)
            upsert_fed_composite(conn, date, fc["fed_composite"], fc["n_axes"], expected,
                                 state["fed_final"])
            conn.close()
            state["log"].append(
                f"[news] Fed 축 결합 {fc['fed_composite']:+.3f} "
                f"({'+'.join(fc['axes'])}{', 확정판' if state['fed_final'] else ', 속보치'})")

    fed, fed_stats = _fed_value_and_stats(state["index"])
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
    h = combine(fed, news["conf_weighted"] if news else None, fed_stats=fed_stats)
    if h:
        state["headline"] = h
        state["log"].append(f"[news] headline {h['headline']:+.3f} ({h['method']})")
    # 2d Step 2: FOMC일이면 성명문(2pm ET) 전/후 뉴스 감성 분리 (시각 있는 수집분에만 유효)
    if state["statement_path"]:
        try:
            pp = index_pre_post(meeting_date=date, after_days=1)
            state["pre_post"] = pp
            if pp["shift"] is not None:
                state["log"].append(
                    f"[news] 발표 전/후 {pp['pre']['conf_weighted']:+.3f}"
                    f"→{pp['post']['conf_weighted']:+.3f} (변화 {pp['shift']:+.3f})")
            elif pp["pre"] or pp["post"]:
                state["log"].append("[news] 발표 전/후 한쪽 뉴스만 → 변화 계산 불가")
        except Exception as e:
            state["log"].append(f"[news] pre/post 생략: {str(e)[:35]}")
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
    # 신호 톤 = 결합(News+Fed) 지수 — 검증된 두 축 이점(-0.534)을 신호에 반영.
    tone = (state.get("headline") or {}).get("headline")
    if tone is None:                                  # 결합 없으면 Fed 단독 z 로 폴백
        fed, fed_stats = _fed_value_and_stats(state["index"])
        tone = (combine(fed, None, fed_stats=fed_stats) or {}).get("headline")
    reaction = state["market"].get("spx_ret_cc")
    vix_chg = state["market"].get("vix_chg")
    rate_chg = state["market"].get("ust2y_chg")
    prev_tone = _prev_combined(state["date"])         # 직전 결합 지수 (daily_signals.csv)

    th = COMBINED_THRESHOLDS                           # 결합 척도용 θ (theta_t 0.22, theta_shift 0.95)
    sigs = [signal_tone_shift(prev_tone, tone, th.theta_shift),
            signal_divergence(tone, reaction, th.theta_t, th.theta_m),
            signal_tone_vs_vix(tone, vix_chg, th.theta_t, th.theta_vix),
            signal_tone_vs_rate(tone, rate_chg, th.theta_t, th.theta_rate)]
    g = grade(sigs, tone, reaction)
    fired = [s.name for s in sigs if s.fired]

    # 질문 5 피드백(A+B 절충): 측정(지수·CI)은 그대로 두고, 뉴스 표본이 적거나(<15건)
    # CI가 넓을 때는 "경보"만 관망으로 낮춘다 — 헛경보 방지. news_signals.confident() 재사용.
    gate_reason = None
    news = state.get("news")
    if news and g in (GRADE_CAUTION, GRADE_ALERT):
        ok, reason = news_confident(news["n_articles"], news.get("ci_lo"), news.get("ci_hi"))
        if not ok:
            gate_reason = reason
            g = GRADE_WATCH

    state["signals"] = {"grade": g, "fired": fired, "gate_reason": gate_reason,
                        "n_articles": news.get("n_articles") if news else None,
                        "ci_lo": news.get("ci_lo") if news else None,
                        "ci_hi": news.get("ci_hi") if news else None}
    tstr = f"{tone:+.3f}" if tone is not None else "—"
    gate_str = f" (게이트: {gate_reason})" if gate_reason else ""
    state["log"].append(f"[strategy] 등급 {g}{gate_str} (결합톤 {tstr}) | 발동 {fired or '없음'}")
    return state


# ── ⑤ Reporting ──
DAILY_FIELDS = ["date", "grade", "index", "fired", "gate_reason", "n_articles", "ci_lo", "ci_hi",
                "fed_axes", "grade_final", "index_final", "fed_axes_final", "finalized_at"]


def append_daily_signal(rec: dict, out=None):
    """일별 신호 1행 누적. 최신일이 마지막 행 → 대시보드·기록용.

    원칙(질문 6 피드백): "과거 실시간 값을 덮어쓰면 안 된다." 그 날짜로 처음 기록되는
    grade/index/fed_axes(및 게이트·표본 정보)는 "속보치"로 영구 고정한다. 같은 날짜를
    재방문해도(예: minutes 도착 후 재처리) 이 필드들은 절대 수정하지 않는다 — rec에
    is_final=True가 실리면 grade_final/index_final/fed_axes_final 에만 그 시점 값을
    추가로 기록한다(절충안: 속보치·확정판 이원화). fed_axes 를 확정판 값으로 덮어쓰면
    "이 grade/index 는 몇 개 축으로 계산됐나"라는 속보치 자체의 근거가 사라지므로,
    fed_axes 도 grade/index 와 함께 얼려두고 fed_axes_final 을 따로 둔다.
    """
    import csv
    out = Path(out or DAILY_SIGNALS)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if out.exists():
        for r in csv.DictReader(open(out, encoding="utf-8")):
            rows[r["date"]] = r

    existing = rows.get(rec["date"])
    if existing is None:
        row = {"date": rec["date"], "grade": rec["grade"],
              "index": round(rec.get("index") or 0.0, 4),
              "fired": ";".join(rec.get("fired") or []),
              "gate_reason": rec.get("gate_reason") or "",
              "n_articles": rec.get("n_articles") if rec.get("n_articles") is not None else "",
              "ci_lo": rec.get("ci_lo") if rec.get("ci_lo") is not None else "",
              "ci_hi": rec.get("ci_hi") if rec.get("ci_hi") is not None else "",
              "fed_axes": ";".join(rec.get("fed_axes") or []),
              "grade_final": "", "index_final": "", "fed_axes_final": "", "finalized_at": ""}
    else:
        row = {k: existing.get(k, "") for k in DAILY_FIELDS}   # 속보치 필드 보존(옛 스키마 보정)

    if rec.get("is_final"):
        row["grade_final"] = rec["grade"]
        row["index_final"] = round(rec.get("index") or 0.0, 4)
        row["fed_axes_final"] = ";".join(rec.get("fed_axes") or []) or row.get("fed_axes_final", "")
        row["finalized_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    rows[rec["date"]] = row
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DAILY_FIELDS)
        w.writeheader()
        for d in sorted(rows):
            w.writerow({k: rows[d].get(k, "") for k in DAILY_FIELDS})


def _prev_combined(date, out=None):
    """date 직전(가장 최근 이전 날)의 결합 지수 — daily_signals.csv. 없으면 None(첫 실행)."""
    import csv
    out = Path(out or DAILY_SIGNALS)
    if not out.exists():
        return None
    prev = None
    for r in csv.DictReader(open(out, encoding="utf-8")):
        if r.get("date", "") < date:
            try:
                prev = float(r["index"])
            except (KeyError, ValueError, TypeError):
                pass
    return prev


def reporting_node(state: State) -> State:
    conn = db.connect(DB)
    path = write_report(conn, state["date"], REPORTS,
                        news=state.get("news") or None,
                        headline=state.get("headline") or None,
                        pre_post=state.get("pre_post") or None,
                        presser=state.get("presser") or None,
                        minutes=state.get("minutes") or None)
    conn.close()
    # 축 톤을 CSV에 upsert — 대시보드 JSON(export_dashboard)의 입력이라, 여기서 갱신해야
    # 새 회의·늦게 도착한 축이 배치 재실행 없이 대시보드에 반영된다.
    try:
        from analysis.tone_store import save_minutes, save_presser
        if state.get("presser"):
            save_presser(state["date"], state["presser"])
        if state.get("minutes"):
            save_minutes(state["date"], state["minutes"])
    except Exception as e:
        state["log"].append(f"[reporting] 톤 CSV 갱신 생략: {str(e)[:35]}")
    state["report_path"] = str(path)
    sig = state.get("signals") or {}
    append_daily_signal({"date": state["date"],
                         "grade": sig.get("grade", "—"),
                         "index": (state.get("headline") or {}).get("headline"),  # 결합(뉴스포함)
                         "fired": sig.get("fired", []),
                         "gate_reason": sig.get("gate_reason"),
                         "n_articles": sig.get("n_articles"),
                         "ci_lo": sig.get("ci_lo"), "ci_hi": sig.get("ci_hi"),
                         "fed_axes": state.get("fed_axes"),
                         "is_final": bool(state.get("fed_final"))})
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
            "news": {}, "pre_post": {}, "presser": {}, "minutes": {},
            "fed_axes": None, "fed_final": False, "headline": {},
            "market": {}, "signals": {},
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
