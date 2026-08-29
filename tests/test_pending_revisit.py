"""재방문 목록 판정 — '파일 수집'이 아니라 '확정판 기록' 기준인지 고정.

2026-08 사고의 회귀 방지: 회의록 파일이 수집 단계에서 도착한 순간 회의가 '완성'으로
바뀌어 재방문 목록에서 빠졌고, 톤 산출·3축 결합이 영영 실행되지 않았다(2026-07-29).
파일이 다 있어도 확정판(fed_composite_final)이 없으면 재방문 대상이어야 한다.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis import axis_status as ax


def _db(tmp_path, finalized):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, "
                "index_value REAL, confidence REAL)")
    for d in finalized:
        con.execute("INSERT INTO meetings VALUES (?, 'fed_composite_final', 'meeting', 0.5, 1.0)", (d,))
    con.commit(); con.close()
    return p


def test_files_complete_but_no_final_is_still_pending(tmp_path, monkeypatch):
    """파일 3축이 다 있어도 확정판이 없으면 재방문 대상 — 사고 시나리오 그대로."""
    monkeypatch.setattr(ax, "DB", _db(tmp_path, finalized=[]))
    monkeypatch.setattr(ax, "meeting_dates", lambda: ["2026-07-29"])
    assert ax.pending_meetings(months=6) == ["2026-07-29"]


def test_finalized_meeting_is_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(ax, "DB", _db(tmp_path, finalized=["2026-06-17"]))
    monkeypatch.setattr(ax, "meeting_dates", lambda: ["2026-06-17", "2026-07-29"])
    assert ax.pending_meetings(months=6) == ["2026-07-29"]


def test_old_meetings_outside_window_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(ax, "DB", _db(tmp_path, finalized=[]))
    monkeypatch.setattr(ax, "meeting_dates", lambda: ["2020-01-29", "2026-07-29"])
    assert ax.pending_meetings(months=6) == ["2026-07-29"]
