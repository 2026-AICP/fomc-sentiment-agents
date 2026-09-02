"""notifier_node 배선 테스트 — DB·네트워크·모델 없이 state 를 직접 구성한다.

드라이런이므로 확인할 것은 두 가지다: ① 로그가 정확히 한 행씩 쌓이는가,
② 실제 발송 경로가 존재하지 않는가(agents/notifier.py 가 발송 모듈을 import 하지 않음).
"""
import csv

from agents import graph, notifier as nt
from analysis.signals import GRADE_ALERT, GRADE_ALIGNED, GRADE_CAUTION


def _state(date, grade, fired, n_articles=40, statement=""):
    return {"date": date, "statement_path": statement, "fed_final": False, "log": [],
            "signals": {"grade": grade, "fired": fired, "gate_reason": None,
                        "details": ["⚠️ 괴리 — 연준 톤 긍정(+0.202) vs 시장 급락(-0.85%)"],
                        "n_articles": n_articles, "ci_lo": -0.10, "ci_hi": 0.20}}


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def _today(monkeypatch, tmp_path, date):
    """오늘 날짜와 로그 경로를 고정 — 소급 발송 금지(§4)가 테스트를 좌우하므로."""
    monkeypatch.setattr(nt, "NOTIFICATION_LOG", tmp_path / "notification_log.csv")

    class _DT:
        @staticmethod
        def now(tz=None):
            import datetime as _d
            return _d.datetime.fromisoformat(date + "T22:00:00+00:00")
    monkeypatch.setattr(graph, "datetime", _DT)
    return tmp_path / "notification_log.csv"


def test_red_alert_logs_a_sent_row(tmp_path, monkeypatch):
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    out = graph.notifier_node(_state("2026-08-20", GRADE_ALERT, ["divergence"]))
    rows = _rows(p)
    assert len(rows) == 1
    assert rows[0]["suppressed_reason"] == "" and rows[0]["channel"] == "dryrun"
    assert rows[0]["n_recipients"] == "0"          # 드라이런 — 수신자 없음
    assert any("드라이런 발송" in line for line in out["log"])


def test_caution_logs_a_suppressed_row(tmp_path, monkeypatch):
    """억제된 날도 한 행 남는다 — 사유가 있어야 빈도를 로그만으로 읽는다(§7-1)."""
    p = _today(monkeypatch, tmp_path, "2026-08-24")
    graph.notifier_node(_state("2026-08-24", GRADE_CAUTION, ["tone_shift"]))
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_BELOW_LEVEL


def test_rerun_same_day_does_not_duplicate_a_send(tmp_path, monkeypatch):
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    st = _state("2026-08-20", GRADE_ALERT, ["divergence"])
    graph.notifier_node(st)
    graph.notifier_node(dict(st, log=[]))
    rows = _rows(p)
    assert [r["suppressed_reason"] for r in rows] == ["", nt.SUP_ALREADY_SENT]


def test_backfilled_date_is_never_sent(tmp_path, monkeypatch):
    """과거 날짜 재계산이 오늘 알림을 만들면 안 된다(§4 소급 발송 금지)."""
    p = _today(monkeypatch, tmp_path, "2026-09-01")
    graph.notifier_node(_state("2026-07-29", GRADE_ALERT, ["divergence"]))
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_NOT_TODAY


def test_correction_row_written_when_final_grade_differs(tmp_path, monkeypatch):
    """7/29 처럼 회의록 도착 후 🔴 → 🟢 로 뒤집힌 경우(§2-3)."""
    p = _today(monkeypatch, tmp_path, "2026-08-29")
    ds = tmp_path / "daily_signals.csv"
    ds.write_text("date,grade,index\n2026-07-29,🔴 경고,0.3971\n", encoding="utf-8")
    monkeypatch.setattr(graph, "DAILY_SIGNALS", ds)
    st = _state("2026-07-29", GRADE_ALIGNED, [])
    st["fed_final"] = True
    graph.notifier_node(st)
    rows = _rows(p)
    assert [r["kind"] for r in rows] == ["signal", "correction"]
    assert rows[1]["suppressed_reason"] == "" and rows[1]["grade"] == GRADE_ALIGNED


def test_first_record_is_not_a_correction(tmp_path, monkeypatch):
    """그 날짜가 처음 기록되는 중이면 정정이 아니라 최초 기록이다."""
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    monkeypatch.setattr(graph, "DAILY_SIGNALS", tmp_path / "empty.csv")
    st = _state("2026-08-20", GRADE_ALERT, ["divergence"])
    st["fed_final"] = True
    graph.notifier_node(st)
    assert [r["kind"] for r in _rows(p)] == ["signal"]


def test_no_send_path_exists():
    """실제 발송 모듈을 import 하지 않는다 — 실수로 켜질 경로가 없다."""
    src = open(nt.__file__, encoding="utf-8").read()
    for mod in ("smtplib", "resend", "requests", "sendgrid", "urllib"):
        assert f"import {mod}" not in src
