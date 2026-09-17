"""notifier_node 배선 테스트 — DB·네트워크·모델 없이 state 를 직접 구성한다.

확인할 것: ① 로그가 판정마다 한 행씩, 발송 뒤에 쌓이는가 ② 판정 모듈에 발송 경로가
섞이지 않았는가(agents/notifier.py 가 발송 모듈을 import 하지 않음 — 발송은 agents/mailer.py)
③ 발송 결과(채널·수신자 수·실패 수)가 로그에 남고 발송 예외가 노드를 죽이지 않는가.
"""
import csv

from agents import graph, mailer, notifier as nt
from analysis.signals import GRADE_ALERT, GRADE_ALIGNED, GRADE_CAUTION


def _state(date, grade, fired, n_articles=40, statement="", market=True):
    """market=False 면 주말·휴장일·시장 수집 실패를 흉내낸다(§4 no_market_data)."""
    return {"date": date, "statement_path": statement, "fed_final": False, "log": [],
            "market": {"spx_ret_cc": -0.85, "vix_chg": 1.2} if market else {},
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


def test_red_alert_logs_a_sent_row(tmp_path, monkeypatch, capsys):
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    out = graph.notifier_node(_state("2026-08-20", GRADE_ALERT, ["divergence"]))
    rows = _rows(p)
    assert len(rows) == 1
    assert rows[0]["suppressed_reason"] == "" and rows[0]["channel"] == "dryrun"
    assert rows[0]["n_recipients"] == "0"          # 드라이런 — 수신자 없음
    assert any("드라이런 발송" in line for line in out["log"])
    assert "::error::" not in capsys.readouterr().out


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

def test_meeting_day_quiet_signal_sends_fed_notice(tmp_path, monkeypatch):
    """회의일인데 신호가 조용하면 — 신호는 억제, 일정 알림 1통."""
    p = _today(monkeypatch, tmp_path, "2026-07-29")
    graph.notifier_node(_state("2026-07-29", GRADE_ALIGNED, [], statement="stmt.txt"))
    rows = {r["kind"]: r["suppressed_reason"] for r in _rows(p)}
    assert rows["signal"] == nt.SUP_NOT_ACTIONABLE
    assert rows["fed_meeting"] == ""


def test_meeting_day_red_alert_is_one_mail(tmp_path, monkeypatch):
    """회의일에 🔴 — 신호 메일 1통에 일정이 합쳐지고, 일정 행은 merged."""
    p = _today(monkeypatch, tmp_path, "2026-07-29")
    graph.notifier_node(_state("2026-07-29", GRADE_ALERT, ["divergence"], statement="stmt.txt"))
    rows = {r["kind"]: r["suppressed_reason"] for r in _rows(p)}
    assert rows["signal"] == "" and rows["fed_meeting"] == nt.SUP_MERGED
    assert sum(1 for r in _rows(p) if r["suppressed_reason"] == "") == 1


def _record(date, grade):
    """재방문 판정이 읽는 속보치 기록 — conftest 가 graph.DAILY_SIGNALS 를 임시로 돌린다."""
    with open(graph.DAILY_SIGNALS, "w", encoding="utf-8", newline="") as f:
        f.write("date,grade" + chr(10) + f"{date},{grade}" + chr(10))


def test_minutes_day_with_correction_is_one_mail(tmp_path, monkeypatch):
    """회의록 도착 + 등급 🔴→🟢 — 정정 메일 1통, 회의록 알림은 merged."""
    p = _today(monkeypatch, tmp_path, "2026-08-19")
    _record("2026-07-29", GRADE_ALERT)
    st = dict(_state("2026-07-29", GRADE_ALIGNED, [], statement="stmt.txt"), fed_final=True)
    graph.notifier_node(st)
    rows = {r["kind"]: r["suppressed_reason"] for r in _rows(p)}
    assert rows["correction"] == "" and rows["fed_minutes"] == nt.SUP_MERGED


def test_minutes_day_without_change_sends_minutes_notice(tmp_path, monkeypatch):
    """회의록 도착인데 등급 그대로 — 정정은 없고 회의록 알림 1통."""
    p = _today(monkeypatch, tmp_path, "2026-08-19")
    _record("2026-07-29", GRADE_ALIGNED)
    st = dict(_state("2026-07-29", GRADE_ALIGNED, [], statement="stmt.txt"), fed_final=True)
    graph.notifier_node(st)
    rows = {r["kind"]: r["suppressed_reason"] for r in _rows(p)}
    assert rows["correction"] == nt.SUP_UNCHANGED and rows["fed_minutes"] == ""


def test_minutes_notice_needs_realtime_record(tmp_path, monkeypatch):
    """속보치 기록이 없는 회의(과거 재처리)에는 회의록 알림을 보내지 않는다 — 소급 방지."""
    p = _today(monkeypatch, tmp_path, "2026-08-19")
    st = dict(_state("2008-10-29", GRADE_ALIGNED, [], statement="stmt.txt"), fed_final=True)
    graph.notifier_node(st)
    assert "fed_minutes" not in {r["kind"] for r in _rows(p)}


def test_weekend_logs_no_market_row(tmp_path, monkeypatch):
    """시장 데이터가 없는 날은 등급과 무관하게 막힌다 — 2026-08-22 는 토요일."""
    p = _today(monkeypatch, tmp_path, "2026-08-22")
    graph.notifier_node(_state("2026-08-22", GRADE_ALERT, ["divergence"], market=False))
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_NO_MARKET


def test_backfilled_date_is_never_sent(tmp_path, monkeypatch):
    """과거 날짜 재계산이 오늘 알림을 만들면 안 된다(§4 소급 발송 금지)."""
    p = _today(monkeypatch, tmp_path, "2026-09-01")
    graph.notifier_node(_state("2026-07-29", GRADE_ALERT, ["divergence"]))
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_NOT_TODAY


def test_utc_midnight_boundary_keeps_todays_alert(tmp_path, monkeypatch):
    """크론 지연으로 notifier 가 UTC 자정을 넘겨 돌아도(00:01Z) ET 오늘이면 발송된다.

    2026-09-16 회의일 알림이 정확히 이렇게 유실됐다 — 파이프라인 날짜는
    ET(run_news_daily.sh 의 TODAY_ET = 9/16)인데 notifier 의 '오늘'이 UTC(9/17)라서
    당일 알림이 not_today 로 억제됐다. '오늘'은 파이프라인과 같은 시계(ET)여야 한다.
    """
    monkeypatch.setattr(nt, "NOTIFICATION_LOG", tmp_path / "notification_log.csv")

    class _DT:
        @staticmethod
        def now(tz=None):
            import datetime as _d
            instant = _d.datetime.fromisoformat("2026-09-17T00:01:00+00:00")
            return instant.astimezone(tz) if tz else instant
    monkeypatch.setattr(graph, "datetime", _DT)
    graph.notifier_node(_state("2026-09-16", GRADE_ALIGNED, [], statement="stmt.txt"))
    rows = {r["kind"]: r["suppressed_reason"] for r in _rows(tmp_path / "notification_log.csv")}
    assert rows["fed_meeting"] == ""               # not_today 로 죽으면 안 된다
    assert rows["signal"] == nt.SUP_NOT_ACTIONABLE  # 등급 억제는 그대로


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
    assert [r["kind"] for r in rows] == ["signal", "correction", "fed_minutes"]
    assert rows[1]["suppressed_reason"] == "" and rows[1]["grade"] == GRADE_ALIGNED
    # §2-2 회의록 알림은 같은 날 정정 메일에 합쳐진다 — 나가는 메일은 정정 1통뿐.
    assert rows[2]["suppressed_reason"] == nt.SUP_MERGED
    assert sum(1 for r in rows if r["suppressed_reason"] == "") == 1


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


# --- 실제 발송 연결 (알림 발송 설계 §5 · §7) ----------------------------------
def test_sent_decision_logs_email_channel_and_counts(tmp_path, monkeypatch):
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    monkeypatch.setattr(mailer, "deliver",
                        lambda d: ("email", 3, 1, ["발송 실패 1/3"]))
    out = graph.notifier_node(_state("2026-08-20", GRADE_ALERT, ["divergence"]))
    row = _rows(p)[0]
    assert row["channel"] == "email"
    assert row["n_recipients"] == "3" and row["n_failed"] == "1"
    assert any("[mailer] 발송 실패 1/3" in line for line in out["log"])
    assert row["suppressed_reason"] == ""            # 일부 실패는 '보냄' — 재시도 없음


def test_delivery_exception_does_not_crash_node(tmp_path, monkeypatch):
    p = _today(monkeypatch, tmp_path, "2026-08-20")

    def boom(d):
        raise RuntimeError("resend down")
    monkeypatch.setattr(mailer, "deliver", boom)
    out = graph.notifier_node(_state("2026-08-20", GRADE_ALERT, ["divergence"]))
    assert _rows(p)[0]["channel"] == "email"
    assert any("발송 단계 예외" in line for line in out["log"])
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_SEND_FAILED


def test_suppressed_decision_is_not_delivered(tmp_path, monkeypatch):
    _today(monkeypatch, tmp_path, "2026-08-20")

    def must_not_call(d):
        raise AssertionError("억제된 결정을 보내면 안 된다")
    monkeypatch.setattr(mailer, "deliver", must_not_call)
    graph.notifier_node(_state("2026-08-20", GRADE_ALIGNED, []))


def test_total_failure_is_send_failed_and_not_counted_as_sent(tmp_path, monkeypatch, capsys):
    """전원 실패면 send_failed — '보냄'으로 세지 않아 같은 날 재실행이 막히지 않고, 실행 화면에 경고가 뜬다(설계 §5-4)."""
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    calls = []

    def all_fail(d):
        calls.append(d.kind)
        return ("email", 2, 2, ["발송 실패 2/2"])
    monkeypatch.setattr(mailer, "deliver", all_fail)
    st = _state("2026-08-20", GRADE_ALERT, ["divergence"])
    out = graph.notifier_node(st)
    assert "::error::" in capsys.readouterr().out
    row = _rows(p)[0]
    assert row["suppressed_reason"] == nt.SUP_SEND_FAILED
    assert row["channel"] == "email" and row["n_failed"] == "2"
    assert any("받은 사람 없음" in line for line in out["log"])
    assert nt.read_sent() == set()
    graph.notifier_node(dict(st, log=[]))
    assert calls == ["signal", "signal"]


def test_zero_recipients_is_send_failed(tmp_path, monkeypatch):
    """명단이 비어 0명에게 '보낸' 것은 보낸 것이 아니다."""
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    monkeypatch.setattr(mailer, "deliver",
                        lambda d: ("email", 0, 0, ["구독자 조회 실패: HTTP 500"]))
    graph.notifier_node(_state("2026-08-20", GRADE_ALERT, ["divergence"]))
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_SEND_FAILED
