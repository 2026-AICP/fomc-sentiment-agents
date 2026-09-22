"""scripts/run_news_daily.sh ③ 에이전트 단계의 처리 순서 — 미완성 회의 재방문이 오늘보다 먼저.

사고 기록(2026-09-22): 9/16 회의 기자회견 원고가 이날 아침 처음 수집됐는데, ③이
[오늘] + [재방문] 순서로 돌아 9/21 신호가 기자회견을 흡수하기 **전**의 연준 값
(성명문 단독 +1.848)을 이월해 먼저 계산됐다. 바로 뒤 9/16 재방문이 기자회견을 결합해
연준 값을 +2.055 로 갱신했고, 그 뒤에 도는 ②(daily_index)는 새 값을 썼다.
그래서 같은 날 홈 탭(daily_signals 0.181)과 감성지수 탭(daily_headline 0.284)이 달랐다.
스크립트에 박힌 ③ 소스를 그대로 실행해 orchestrate 에 넘기는 날짜 순서를 본다.
"""
import re
import sys
from pathlib import Path

from agents import graph
from analysis import axis_status

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_news_daily.sh"


def _agent_step():
    """run_news_daily.sh 의 ③ 에이전트 단계(python3 - <<'PY' … PY) 소스."""
    m = re.search(r"<<'PY'[^\n]*\n(.*?)\nPY\n", SCRIPT.read_text(encoding="utf-8"), re.S)
    assert m, "run_news_daily.sh 에서 ③ 에이전트 단계를 찾지 못함"
    return m.group(1)


def _dates_passed(monkeypatch, today, pending):
    calls = []
    monkeypatch.setattr(graph, "orchestrate", lambda dates=None, **kw: calls.append(list(dates)))
    monkeypatch.setattr(axis_status, "pending_meetings", lambda *a, **kw: list(pending))
    monkeypatch.setattr(axis_status, "write_status", lambda *a, **kw: None)
    monkeypatch.setattr(sys, "argv", ["-", today])
    exec(compile(_agent_step(), str(SCRIPT), "exec"), {"__name__": "__main__"})
    return calls


def test_pending_meetings_are_revisited_before_today(monkeypatch):
    # 9/16 기자회견이 도착한 날 — 재방문이 먼저 돌아야 9/21 신호가 갱신된 연준 값을 쓴다
    assert _dates_passed(monkeypatch, "2026-09-21", ["2026-09-16"]) == [
        ["2026-09-16", "2026-09-21"]]


def test_today_runs_last_and_once_even_if_pending(monkeypatch):
    # FOMC 당일에는 오늘 회의도 미완성 목록에 있다 — 두 번 돌지 않고 마지막에 한 번
    assert _dates_passed(monkeypatch, "2026-09-16", ["2026-07-29", "2026-09-16"]) == [
        ["2026-07-29", "2026-09-16"]]
