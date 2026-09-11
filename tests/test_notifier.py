"""Notifier 단위테스트 (네트워크·DB·파일 의존 최소, 결정적).

docs/notification_design.md §2(발동)·§4(억제)·§5(내용 규격)·§7-1(로그 스키마) 을 고정한다.
로그가 PUBLIC 리포에 커밋되므로 스키마·사유 코드를 여기서 잠근다.
"""
import csv
import re

from agents.notifier import (
    LOG_FIELDS,
    LEVEL_ALERT,
    LEVEL_CAUTION,
    SUP_ALREADY_SENT,
    SUP_BELOW_LEVEL,
    SUP_NO_ARTICLES,
    SUP_NO_MARKET,
    SUP_NOT_ACTIONABLE,
    SUP_NOT_TODAY,
    SUP_UNCHANGED,
    append_log,
    confidence_label,
    decide,
    decide_correction,
    read_sent,
    render,
)
from analysis.signals import GRADE_ALERT, GRADE_ALIGNED, GRADE_CAUTION, GRADE_NEUTRAL, GRADE_WATCH

TODAY = "2026-08-20"
OK = dict(n_articles=40, ci_lo=-0.10, ci_hi=0.20, today=TODAY)


# --- §2-1 발동 기준 ---------------------------------------------------------
def test_red_alert_sends_on_default_level():
    d = decide(TODAY, GRADE_ALERT, ["divergence"], level=LEVEL_ALERT, **OK)
    assert d.send and d.suppressed is None

def test_caution_suppressed_on_default_level():
    d = decide(TODAY, GRADE_CAUTION, ["tone_shift"], level=LEVEL_ALERT, **OK)
    assert not d.send and d.suppressed == SUP_BELOW_LEVEL

def test_caution_sends_when_subscriber_opts_down():
    d = decide(TODAY, GRADE_CAUTION, ["tone_shift"], level=LEVEL_CAUTION, **OK)
    assert d.send


# --- §4 억제 조건 -----------------------------------------------------------
def test_watch_grade_never_sends():
    """신뢰도 게이트로 관망까지 내려간 날은 발송 금지."""
    d = decide(TODAY, GRADE_WATCH, ["divergence"], level=LEVEL_CAUTION, **OK)
    assert not d.send and d.suppressed == SUP_NOT_ACTIONABLE

def test_neutral_and_aligned_never_send():
    for g in (GRADE_NEUTRAL, GRADE_ALIGNED):
        assert decide(TODAY, g, [], level=LEVEL_CAUTION, **OK).suppressed == SUP_NOT_ACTIONABLE

def test_collection_failure_suppresses():
    d = decide(TODAY, GRADE_ALERT, ["divergence"],
               n_articles=0, ci_lo=None, ci_hi=None, today=TODAY)
    assert not d.send and d.suppressed == SUP_NO_ARTICLES

def test_backfill_never_sends():
    """소급 발송 금지 — 과거 날짜를 재계산해도 오늘 알림이 되면 안 된다."""
    d = decide("2026-08-13", GRADE_ALERT, ["divergence"], **OK)
    assert not d.send and d.suppressed == SUP_NOT_TODAY

def test_duplicate_suppressed():
    d = decide(TODAY, GRADE_ALERT, ["divergence"], sent={(TODAY, "signal")}, **OK)
    assert not d.send and d.suppressed == SUP_ALREADY_SENT


# --- §2-3 정정 알림 ---------------------------------------------------------
def test_correction_sends_when_grade_changed():
    d = decide_correction("2026-07-29", GRADE_ALERT, GRADE_ALIGNED, TODAY)
    assert d.send and d.prev_grade == GRADE_ALERT and d.grade == GRADE_ALIGNED

def test_correction_silent_when_grade_same():
    d = decide_correction("2026-07-29", GRADE_ALERT, GRADE_ALERT, TODAY)
    assert not d.send and d.suppressed == SUP_UNCHANGED

def test_correction_none_without_final():
    assert decide_correction("2026-07-29", GRADE_ALERT, "", TODAY) is None

# --- §4 시장 데이터 없는 날 -------------------------------------------------
def test_no_market_suppresses(tmp_path):
    """주말·휴장일·수집실패 — 비교할 시장이 없으면 보내지 않는다."""
    d = decide(TODAY, GRADE_ALERT, ["divergence"], has_market=False, **OK)
    assert not d.send and d.suppressed == SUP_NO_MARKET

def test_no_market_checked_before_grade():
    """등급보다 먼저 본다 — 로그에 '휴장'이 아니라 '등급'이 남으면 빈도를 못 읽는다."""
    d = decide(TODAY, GRADE_ALIGNED, [], has_market=False, **OK)
    assert d.suppressed == SUP_NO_MARKET      # grade_not_actionable 이 아니라

def test_market_present_still_sends():
    d = decide(TODAY, GRADE_ALERT, ["divergence"], has_market=True, **OK)
    assert d.send and d.suppressed is None

def test_correction_silent_when_neither_grade_is_alert():
    """전후 어느 쪽도 🔴 이 아니면 정정을 보내지 않는다.

    원본이 ⚠️ 였다면 기본 발송 등급(🔴)에 미달해 애초에 나가지 않았다.
    나가지도 않은 알림의 정정을 보내면 받는 쪽에 맥락이 없다.
    """
    d = decide_correction("2026-07-29", GRADE_CAUTION, GRADE_ALIGNED, TODAY)
    assert not d.send and d.suppressed == SUP_NOT_ACTIONABLE

def test_correction_sends_when_final_becomes_alert():
    """확정판에서 🔴 이 되면 보낸다 — 원본이 🔴 이 아니었어도."""
    d = decide_correction("2026-07-29", GRADE_ALIGNED, GRADE_ALERT, TODAY)
    assert d.send and d.suppressed is None


# --- §5 신뢰도 라벨 (data.js confidenceLevel() 과 같은 규칙) ------------------
def test_confidence_low_on_few_articles():
    assert confidence_label(14, -0.1, 0.1) == "낮음"

def test_confidence_low_on_wide_ci():
    assert confidence_label(100, -0.5, 0.2) == "낮음"      # 폭 0.70 > 0.60

def test_confidence_high_needs_both():
    assert confidence_label(30, -0.2, 0.2) == "높음"        # 30건 · 폭 0.40
    assert confidence_label(29, -0.2, 0.2) == "보통"        # 건수 미달
    assert confidence_label(30, -0.21, 0.20) == "보통"      # 폭 0.41 초과

def test_confidence_boundary_at_gate():
    assert confidence_label(15, -0.3, 0.3) == "보통"        # 정확히 15건 · 폭 0.60


# --- §5 내용 규격 -----------------------------------------------------------
def test_subject_carries_grade():
    subject, _ = render(decide(TODAY, GRADE_ALERT, ["divergence"], **OK))
    assert GRADE_ALERT in subject

# 측정값 패턴 — 부호붙은 수, 소수, %, pt, N건. "2년물" 같은 이름의 숫자는 측정값이 아니다.
MEASUREMENT = re.compile(r"[+-]\s*\d|\d+\.\d|\d+\s*%|\d+\s*pt|\d+\s*건")


def test_body_carries_no_measurements():
    """지수·CI 폭·기사 수 제외(§5) — 상세보기(사이트)에서만 본다."""
    d = decide(TODAY, GRADE_ALERT, ["divergence"], **OK)
    d.details = ["⚠️ 괴리 — 연준 톤 긍정(+0.202) vs 시장 급락(-0.85%)"]
    _, body = render(d)
    assert not MEASUREMENT.search(body.replace(TODAY, "")), body
    assert "괴리" in body and "톤 긍정" in body            # 문구는 살아 있어야 한다

def test_body_strips_every_signal_detail():
    """네 신호의 실제 detail 형식을 모두 통과시킨다."""
    d = decide(TODAY, GRADE_ALERT, ["divergence"], **OK)
    d.details = ["🔼 톤 개선 (+0.237)",
                 "⚠️ 괴리 — 연준 톤 긍정(+0.202) vs 시장 급락(-0.85%)",
                 "⚠️ 동행 이탈 — 톤 부정인데 VIX 급락(-1.11)",
                 "⚠️ 금리 동행 이탈 — 톤 부정인데 2년물 급락(-0.07%p)"]
    _, body = render(d)
    assert not MEASUREMENT.search(body.replace(TODAY, "")), body
    assert "2년물" in body                                  # 이름의 숫자는 남는다

def test_body_has_disclaimer_and_unsubscribe():
    _, body = render(decide(TODAY, GRADE_ALERT, ["divergence"], **OK))
    assert "투자조언이 아닙니다" in body and "수신거부" in body

def test_between_meetings_says_news_not_fed_tone():
    """§4 — Fed 축이 상수인 구간의 tone_shift 는 '뉴스 감성 변화'로 적는다."""
    d = decide(TODAY, GRADE_CAUTION, ["tone_shift"], level=LEVEL_CAUTION,
               details=["🔼 톤 개선"], news_only=True, **OK)
    _, body = render(d)
    assert "뉴스 감성 개선" in body and "톤 개선" not in body


# --- §7-1 로그 스키마 (PUBLIC 리포에 커밋된다) --------------------------------
def test_log_schema_is_locked():
    assert LOG_FIELDS == ["date", "kind", "grade", "fired", "channel",
                          "n_recipients", "n_failed", "suppressed_reason"]

def test_log_writes_sent_and_suppressed_rows(tmp_path):
    p = tmp_path / "notification_log.csv"
    append_log(decide(TODAY, GRADE_ALERT, ["divergence", "tone_vs_vix"], **OK), path=p)
    append_log(decide(TODAY, GRADE_CAUTION, ["tone_shift"], **OK), path=p)
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert [r["suppressed_reason"] for r in rows] == ["", SUP_BELOW_LEVEL]
    assert rows[0]["channel"] == "dryrun" and rows[0]["n_recipients"] == "0"
    assert rows[0]["fired"] == "divergence;tone_vs_vix"
    assert read_sent(p) == {(TODAY, "signal")}

def test_log_appends_without_overwriting(tmp_path):
    p = tmp_path / "notification_log.csv"
    append_log(decide(TODAY, GRADE_ALERT, ["divergence"], **OK), path=p)
    append_log(decide_correction("2026-07-29", GRADE_ALERT, GRADE_ALIGNED, TODAY), path=p)
    assert len(list(csv.DictReader(open(p, encoding="utf-8")))) == 2

def test_read_sent_ignores_suppressed_rows(tmp_path):
    """억제된 행은 '보냈다'로 치지 않는다.

    오전에 수집이 실패해 no_articles 로 한 줄 남은 날, 오후에 재실행하면
    already_sent 로 막히던 버그. 한 통도 안 나갔는데 그날 복구가 불가능했다.
    """
    p = tmp_path / "notification_log.csv"
    append_log(decide(TODAY, GRADE_ALERT, ["divergence"], n_articles=0,
                      ci_lo=-0.1, ci_hi=0.2, today=TODAY), path=p)
    assert read_sent(p) == set()          # 억제된 행뿐 → 비어 있어야 한다

    d = decide(TODAY, GRADE_ALERT, ["divergence"], sent=read_sent(p), **OK)
    assert d.send, "억제만 기록된 날은 재실행에서 발송돼야 한다"

def test_read_sent_blocks_real_duplicate(tmp_path):
    """실제로 나간 날은 여전히 막는다 — 중복 발송 방지는 유지."""
    p = tmp_path / "notification_log.csv"
    append_log(decide(TODAY, GRADE_ALERT, ["divergence"], **OK), path=p)
    assert read_sent(p) == {(TODAY, "signal")}

    d = decide(TODAY, GRADE_ALERT, ["divergence"], sent=read_sent(p), **OK)
    assert not d.send and d.suppressed == SUP_ALREADY_SENT
