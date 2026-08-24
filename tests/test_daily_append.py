import csv
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


def test_realtime_fields_never_overwritten_on_revisit(tmp_path, monkeypatch):
    """질문 6 피드백: "과거 실시간 값을 덮어쓰면 안 된다." 같은 날짜 재방문(예: minutes
    도착 후 재처리)해도 최초 기록된 grade/index(속보치)는 그대로여야 한다."""
    out = tmp_path / "daily_signals.csv"
    monkeypatch.setattr(graph, "DAILY_SIGNALS", out)
    graph.append_daily_signal({"date": "2026-07-08", "grade": "⚠️ 주의",
                               "index": 0.05, "fired": ["shift"]})
    graph.append_daily_signal({"date": "2026-07-08", "grade": "🔴 경고",
                               "index": 0.99, "fired": ["divergence"]})   # 재방문(is_final 아님)
    row = {r["date"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}["2026-07-08"]
    assert row["grade"] == "⚠️ 주의" and float(row["index"]) == 0.05
    assert row["grade_final"] == "" and row["index_final"] == ""


def test_finalization_adds_final_fields_without_touching_realtime(tmp_path, monkeypatch):
    """의사록 도착으로 3축이 다 차면(is_final=True) grade_final/index_final 만 채워지고,
    같은 행의 속보치(grade/index)는 절대 바뀌지 않는다(절충안: 속보치·확정판 이원화)."""
    out = tmp_path / "daily_signals.csv"
    monkeypatch.setattr(graph, "DAILY_SIGNALS", out)
    graph.append_daily_signal({"date": "2026-08-05", "grade": "⚠️ 주의", "index": -0.12,
                               "fired": ["shift"], "fed_axes": ["statement"]})
    graph.append_daily_signal({"date": "2026-08-05", "grade": "🟢 정합", "index": -0.30,
                               "fired": [], "fed_axes": ["statement", "presser", "minutes"],
                               "is_final": True})
    row = {r["date"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}["2026-08-05"]
    assert row["grade"] == "⚠️ 주의" and float(row["index"]) == -0.12         # 속보치 불변
    assert row["grade_final"] == "🟢 정합" and float(row["index_final"]) == -0.30
    assert row["fed_axes"] == "statement;presser;minutes"
    assert row["finalized_at"]
