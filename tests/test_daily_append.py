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
    # 같은 날짜 재실행 시 덮어쓰기(중복 방지)
    graph.append_daily_signal({"date": "2026-07-08", "grade": "⚠️ 주의",
                               "index": 0.05, "fired": ["shift"]})
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 2 and rows[-1]["grade"] == "⚠️ 주의"
