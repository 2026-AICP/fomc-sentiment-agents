# Unified Daily Sentiment Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One LangGraph agent runs daily, compares the sentiment index with same-day market indicators (S&P/VIX/2Y), and emits offset=0 signals A–D; FOMC days ingest the statement, other days carry the Fed tone forward.

**Architecture:** Extend the existing `agents/graph.py` LangGraph (collector→analyst→news→market→strategy→reporting) with a **daily mode**: when no statement exists for a date, carry the last meeting's Fed tone forward and skip the analyst. The `market` node fetches same-day (offset=0) S&P/VIX/2Y; the `strategy` node computes signals A–D on the **raw** daily tone. A `reporting` step appends to accumulating daily CSVs, and the daily GitHub Actions workflow drives the agent.

**Tech Stack:** Python 3, LangGraph, FinBERT (transformers/torch), pandas, yfinance, SQLite, pytest.

**Reference:** design spec `docs/superpowers/specs/2026-07-07-unified-daily-agent-design.md`.

---

### Task 1: Fed tone carry-forward helper

**Files:**
- Modify: `analysis/analyze_alignment.py` (add `fed_tone_asof`)
- Test: `tests/test_fed_carry.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fed_carry.py
import os, sqlite3, tempfile
from analysis.analyze_alignment import fed_tone_asof

def _db():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.executemany("INSERT INTO meetings VALUES (?,?,?,?,?)", [
        ("2026-01-28", "conf_weighted", "meeting", 0.20, 0.3),
        ("2026-03-18", "conf_weighted", "meeting", 0.35, 0.3),
    ])
    con.commit()
    return con

def test_carry_forward_uses_last_meeting_on_or_before():
    con = _db()
    assert fed_tone_asof(con, "2026-02-10") == 0.20   # Jan 이후, Mar 이전 → Jan 이월
    assert fed_tone_asof(con, "2026-03-18") == 0.35   # 회의 당일
    assert fed_tone_asof(con, "2026-04-01") == 0.35   # Mar 이후 이월
    assert fed_tone_asof(con, "2020-01-01") is None   # 회의 이전 → 없음
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fed_carry.py -v`
Expected: FAIL — `ImportError: cannot import name 'fed_tone_asof'`

- [ ] **Step 3: Write minimal implementation**

```python
# analysis/analyze_alignment.py  (add below get_meeting_tone)
def fed_tone_asof(con, date, method="conf_weighted"):
    """date 시점 Fed 톤 = 그날 이전(포함) 마지막 회의의 index_value (이월). 없으면 None."""
    row = con.execute(
        "SELECT index_value FROM meetings WHERE method=? AND granularity='meeting' "
        "AND date<=? ORDER BY date DESC LIMIT 1", (method, date)).fetchone()
    return row[0] if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_fed_carry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/analyze_alignment.py tests/test_fed_carry.py
git commit -m "feat: fed_tone_asof carry-forward helper for daily agent mode"
```

---

### Task 2: Daily-mode routing decision (pure function)

The graph must continue past `collector` even when no statement exists. Extract the routing decision into a pure function so it is unit-testable.

**Files:**
- Modify: `agents/graph.py` (replace `_route_after_collect`)
- Test: `tests/test_daily_route.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_route.py
from agents.graph import route_after_collect

def test_meeting_day_routes_to_analyst():
    assert route_after_collect({"statement_path": "/x/FOMC_2026-03-18.txt"}) == "analyst"

def test_daily_day_routes_to_news_not_end():
    # 성명문 없음 → 종료(skip)가 아니라 일별(news)로 진행
    assert route_after_collect({"statement_path": ""}) == "news"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_daily_route.py -v`
Expected: FAIL — `ImportError: cannot import name 'route_after_collect'`

- [ ] **Step 3: Write minimal implementation**

Replace the existing `_route_after_collect` in `agents/graph.py`:

```python
def route_after_collect(state) -> str:
    """성명문 있으면 analyst(회의 모드), 없으면 news(일별 모드 — Fed 이월)."""
    return "analyst" if state["statement_path"] else "news"
```

And in `build_graph()`, change the conditional edge:

```python
    g.add_conditional_edges("collector", route_after_collect,
                            {"analyst": "analyst", "news": "news"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_daily_route.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/graph.py tests/test_daily_route.py
git commit -m "feat: daily-mode routing — no statement continues to news, not END"
```

---

### Task 3: news_node carries Fed tone forward in daily mode

When `analyst` was skipped (daily mode), `state["index"]` is empty. `news_node` must fill the Fed tone from carry-forward so `combine()` and signals have a Fed axis.

**Files:**
- Modify: `agents/graph.py` (`news_node` — add carry-forward when index empty)
- Test: `tests/test_daily_news_node.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_news_node.py
import os, sqlite3, tempfile
from agents import graph

def _seed_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.execute("INSERT INTO meetings VALUES ('2026-01-28','conf_weighted','meeting',0.20,0.3)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", path)

def test_news_node_fills_fed_from_carry_when_index_empty(monkeypatch):
    _seed_db(monkeypatch)
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)  # 실시간 뉴스 없음
    state = graph._init_state("2026-02-10")   # 회의 아님 → index 비어있음
    out = graph.news_node(state)
    assert out["index"].get("conf_weighted") == 0.20   # Jan 이월
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_daily_news_node.py -v`
Expected: FAIL — `assert None == 0.20` (news_node이 이월을 안 채움)

- [ ] **Step 3: Write minimal implementation**

At the top of `news_node` in `agents/graph.py`, before computing `fed`, add carry-forward when the index is empty:

```python
def news_node(state: State) -> State:
    date = state["date"]
    if not state["index"]:                       # 일별 모드: analyst 건너뜀 → Fed 이월
        from analysis.analyze_alignment import fed_tone_asof
        conn = db.connect(DB); db.init_db(conn)
        carry = fed_tone_asof(conn, date)
        conn.close()
        if carry is not None:
            state["index"] = {"conf_weighted": round(carry, 4)}
            state["log"].append(f"[news] Fed 이월 {carry:+.3f} (일별 모드)")
    fed = state["index"].get("conf_weighted") if state["index"] else None
    # ... (기존 news_node 나머지 그대로) ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_daily_news_node.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/graph.py tests/test_daily_news_node.py
git commit -m "feat: news_node carries Fed tone forward in daily mode"
```

---

### Task 4: market_node adds 2Y change; strategy_node adds signal D + offset=0

**Files:**
- Modify: `agents/graph.py` (`market_node`, `strategy_node`)
- Test: `tests/test_strategy_signal_d.py` (create)

- [ ] **Step 1: Write the failing test** (strategy fires signal D on raw tone vs same-day 2Y)

```python
# tests/test_strategy_signal_d.py
from agents import graph

def test_strategy_includes_tone_vs_rate(monkeypatch, tmp_path):
    # 톤 긍정(+0.30)인데 2년물 급등(+0.10%p) = 금리 동행 이탈 → 신호 D 발동
    import sqlite3
    dbp = tmp_path / "m.db"
    con = sqlite3.connect(dbp)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", str(dbp))     # 빈 meetings → prev_tone None (에러 없이)
    state = graph._init_state("2026-02-10")
    state["index"] = {"conf_weighted": 0.30}
    state["market"] = {"spx_ret_cc": 0.1, "vix_chg": 0.0, "ust2y_chg": 0.10}
    out = graph.strategy_node(state)
    assert "tone_vs_rate" in out["signals"]["fired"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_strategy_signal_d.py -v`
Expected: FAIL — `tone_vs_rate` not in fired (strategy에 D 없음)

- [ ] **Step 3: Write minimal implementation**

In `agents/graph.py` `market_node`, after computing the reaction, add the 2Y change (offset=0 for the daily agent):

```python
# market_node — 반응을 offset=0(당일)로, 2년물 변화도 함께
from analysis.analyze_alignment import get_reaction, get_ust2y_change
reac = get_reaction(conn, date, 0)               # 당일(offset=0) — positional(키워드명 불일치 회피)
rate_chg = get_ust2y_change(conn, date, 0)       # 2년물 변화; 2Y 데이터 없으면 None(신호 D 미발동)
if reac:
    rdate, spx, vixc = reac
    vlv = conn.execute("SELECT vix FROM market WHERE date=?", (rdate,)).fetchone()
    state["market"] = {"spx_ret_cc": spx, "vix_chg": vixc,
                       "vix": vlv[0] if vlv else None, "ust2y_chg": rate_chg,
                       "reaction_date": rdate}
```

In `strategy_node`, add signal D to the list:

```python
from analysis.signals import (signal_tone_shift, signal_divergence,
                              signal_tone_vs_vix, signal_tone_vs_rate, grade)
...
    sigs = [signal_tone_shift(prev_tone, tone),
            signal_divergence(tone, reaction),
            signal_tone_vs_vix(tone, vix_chg),
            signal_tone_vs_rate(tone, state["market"].get("ust2y_chg"))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_strategy_signal_d.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/graph.py tests/test_strategy_signal_d.py
git commit -m "feat: market_node 2Y + strategy signal D, offset=0 for daily agent"
```

---

### Task 5: reporting_node appends to accumulating daily CSVs

**Files:**
- Modify: `agents/graph.py` (`reporting_node` — append daily index + signal rows)
- Test: `tests/test_daily_append.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_append.py
import csv
from pathlib import Path
from agents import graph

def test_append_daily_row(tmp_path, monkeypatch):
    out = tmp_path / "daily_signals.csv"
    monkeypatch.setattr(graph, "DAILY_SIGNALS", out)
    graph.append_daily_signal({"date": "2026-07-07", "grade": "🔴 경고",
                               "index": 0.30, "fired": ["divergence"]})
    graph.append_daily_signal({"date": "2026-07-08", "grade": "🟢 안정",
                               "index": 0.10, "fired": []})
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 2                       # 누적됨
    assert rows[-1]["date"] == "2026-07-08"
    # 같은 날짜 재실행 시 덮어쓰기(중복 방지)
    graph.append_daily_signal({"date": "2026-07-08", "grade": "⚠️ 주의",
                               "index": 0.05, "fired": ["shift"]})
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 2 and rows[-1]["grade"] == "⚠️ 주의"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_daily_append.py -v`
Expected: FAIL — `AttributeError: module 'agents.graph' has no attribute 'append_daily_signal'`

- [ ] **Step 3: Write minimal implementation**

Add to `agents/graph.py` (near the top-level constants + reporting):

```python
DAILY_SIGNALS = ROOT / "outputs" / "daily_signals.csv"

def append_daily_signal(rec: dict, out=None):
    """일별 신호 1행 누적(같은 날짜는 덮어쓰기). 최신일이 마지막 행."""
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
```

Then call it in `reporting_node` (after the report is written):

```python
    append_daily_signal({"date": state["date"],
                         "grade": state["signals"].get("grade", "—"),
                         "index": (state["index"] or {}).get("conf_weighted"),
                         "fired": state["signals"].get("fired", [])})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_daily_append.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/graph.py tests/test_daily_append.py
git commit -m "feat: reporting_node appends accumulating daily_signals.csv"
```

---

### Task 6: Offline smoke — graph runs end-to-end on a daily (non-meeting) date

**Files:**
- Test: `tests/test_daily_smoke.py` (create)

- [ ] **Step 1: Write the failing test** (dummy engine, no network — daily date reaches END with a grade)

```python
# tests/test_daily_smoke.py
import os, sqlite3, tempfile
from agents import graph

def test_daily_date_runs_to_end(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.execute("INSERT INTO meetings VALUES ('2026-01-28','conf_weighted','meeting',0.20,0.3)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", path)
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)   # 뉴스 없음
    monkeypatch.setattr(graph.cm, "download_full_range", lambda d: (_ for _ in ()).throw(RuntimeError("offline")))
    app = graph.build_graph()
    result = app.invoke(graph._init_state("2026-02-10"))   # 회의 아님
    assert "grade" in result["signals"]           # strategy까지 관통
    assert result["report_path"]                  # reporting 도달
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_daily_smoke.py -v`
Expected: FAIL first if any wiring gap remains; otherwise PASS once Tasks 2–5 are in.

- [ ] **Step 3: Fix any wiring gaps** surfaced by the smoke test (e.g., a node that assumes `statement_path`). Keep changes minimal.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_daily_smoke.py agents/graph.py
git commit -m "test: offline smoke — daily date runs graph end-to-end"
```

---

### Task 7: Daily workflow drives the agent

**Files:**
- Modify: `scripts/run_news_daily.sh` (run the agent for today)
- Test: manual / CI (`workflow_dispatch`)

- [ ] **Step 1: Update the wrapper** — after the news index, run the agent for today so the daily index+signal reflect the unified flow:

```sh
# scripts/run_news_daily.sh  (add after news_scheduler / daily_index)
TODAY_ET="$(TZ=America/New_York date +%F)"       # 미국(ET) 날짜 기준 정렬
python3 - "$TODAY_ET" <<'PY'
import sys
from agents import graph
graph.orchestrate(dates=[sys.argv[1]])           # 오늘 1건 무인 실행
PY
```

- [ ] **Step 2: Run the wrapper locally (dummy engine ok)**

Run: `SENTIMENT_ENGINE=dummy sh scripts/run_news_daily.sh`
Expected: completes; `outputs/daily_signals.csv` has today's row.

- [ ] **Step 3: Confirm the workflow still commits the new output** — verify `.github/workflows/daily-news.yml` `git add` list includes `outputs/daily_signals.csv` (add it if missing).

- [ ] **Step 4: Commit**

```bash
git add scripts/run_news_daily.sh .github/workflows/daily-news.yml
git commit -m "feat: daily workflow drives the unified agent (orchestrate today)"
```

- [ ] **Step 5: Push + trigger once**

```bash
git push origin main
gh workflow run daily-news.yml
```
Expected: green run; deploy branch gets a `daily_signals.csv` commit.

---

## Notes for the engineer

- **Do not change** `REACTION_OFFSET` in `analyze_alignment.py` — the offset=1 meeting backtest (`signals.py` main) depends on it. The daily agent passes `offset=0` explicitly at the call sites (Task 4).
- **Signals use raw tone** (`conf_weighted`), never the z-standardized headline — θ thresholds are calibrated on raw. The z headline is display-only.
- **FRED 2Y** needs `FRED_API_KEY` (`.fredapi_key` locally / secret in CI). If absent, `get_ust2y_change` returns None → signal D simply doesn't fire (graceful).
- **Daily index CSV** (accumulating sentiment series) is already produced by the existing `analysis/daily_index.py` step in `run_news_daily.sh` (`outputs/daily_headline.csv`) — this plan adds only the **signal** CSV. No duplicate index writer needed.
- **2Y collection**: `market_node` calls `cm.download_full_range` + `upsert_market`. Verify the Signal-D merge wired FRED 2Y into that path; if 2Y is collected by a separate function, call it in `market_node` too so `get_ust2y_change` finds data. Absent 2Y → signal D silently off (acceptable).
- **Confidence gate (spec §신호):** deferred as a one-line refinement — in `strategy_node`, if `state["news"]` exists and `n_articles < 15`, override grade to `⚪ 관망`. Not blocking for v1 (grade already reflects fired signals); add after Task 6 if false alarms appear on low-article days.
- Dashboard display of `daily_signals.csv` is a **separate** task on the deploy branch (not in this plan).
