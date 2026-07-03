"""scheduler 순수 로직 테스트 — 미처리(pending) 회의 탐지."""
from agents.scheduler import pending_dates


def test_pending_excludes_dates_with_report(tmp_path):
    (tmp_path / "report_2020-01-29.md").write_text("x", encoding="utf-8")
    all_dates = ["2020-01-29", "2020-03-15", "2020-04-29"]
    pend = pending_dates(all_dates, tmp_path)
    assert pend == ["2020-03-15", "2020-04-29"]   # 리포트 있는 1건 제외


def test_pending_all_when_no_reports(tmp_path):
    all_dates = ["2021-01-27", "2021-03-17"]
    assert pending_dates(all_dates, tmp_path) == all_dates


def test_pending_empty_when_all_done(tmp_path):
    for d in ("2021-01-27", "2021-03-17"):
        (tmp_path / f"report_{d}.md").write_text("x", encoding="utf-8")
    assert pending_dates(["2021-01-27", "2021-03-17"], tmp_path) == []
