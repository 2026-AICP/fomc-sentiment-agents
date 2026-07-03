"""runlog 단위테스트 — 기록/읽기 왕복 + 성공률 집계(순수)."""
from agents.runlog import append_run, read_runs, summarize


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "runs.jsonl"
    append_run({"date": "2020-01-29", "ok": True, "status": "ok", "duration_s": 4.2}, path=p)
    append_run({"date": "2020-03-15", "ok": False, "status": "실패: x", "duration_s": 1.0}, path=p)
    runs = read_runs(p)
    assert len(runs) == 2
    assert runs[0]["date"] == "2020-01-29"
    assert "ts" in runs[0]                       # ts 자동 부여


def test_read_missing_file_is_empty(tmp_path):
    assert read_runs(tmp_path / "nope.jsonl") == []


def test_summarize_counts_and_rate():
    runs = [
        {"ok": True, "status": "ok", "duration_s": 2.0},
        {"ok": True, "status": "ok", "duration_s": 4.0},
        {"ok": False, "status": "부분오류(1)", "duration_s": 3.0},
        {"ok": False, "status": "실패: market", "duration_s": 1.0},
    ]
    s = summarize(runs)
    assert s["total"] == 4
    assert s["ok"] == 2
    assert s["partial"] == 1
    assert s["failed"] == 1
    assert abs(s["success_rate"] - 0.5) < 1e-9
    assert abs(s["avg_duration_s"] - 2.5) < 1e-9


def test_summarize_empty():
    s = summarize([])
    assert s["total"] == 0 and s["success_rate"] == 0.0
