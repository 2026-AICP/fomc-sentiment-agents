"""Notifier — 발송 판정과 본문 생성 (docs/notification_design.md §2·§4·§5·§7-1).

**드라이런이다.** 실제 발송은 하지 않는다 — 이 파일은 smtplib 도 resend 도 import
하지 않으므로 호출할 발송 함수 자체가 없다. 남기는 것은 outputs/notification_log.csv
한 행뿐이고, 인프라(§10-2~4)가 붙은 뒤에 send() 를 얹는다.

판정(decide·decide_correction)과 렌더(render)는 **순수 함수**다. 네트워크·DB·파일에
의존하지 않으므로 단위테스트가 결정적이다. 파일을 만지는 것은 append_log·read_log 뿐.

로그는 리포에 커밋된다(§7-1). 리포가 PUBLIC 이고 히스토리는 지워도 남으므로:
  · 구독자 식별 정보는 어떤 필드에도 넣지 않는다 — n_recipients 는 '수' 하나뿐이다
  · suppressed_reason 은 자유 문자열이 아니라 아래 고정 코드만 쓴다. 예외 메시지·
    기사 제목 같은 게 새어 들어갈 경로를 원천 차단한다
  · 컬럼 집합은 tests/test_notifier.py 가 잠근다
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from analysis.news_signals import DEFAULT as NEWS_TH
from analysis.signals import GRADE_ALERT, GRADE_CAUTION

ROOT = Path(__file__).resolve().parents[1]
NOTIFICATION_LOG = ROOT / "outputs" / "notification_log.csv"

LOG_FIELDS = ["date", "kind", "grade", "fired", "channel",
              "n_recipients", "n_failed", "suppressed_reason"]

# 발송 채널. 인프라 이전이라 지금 쓰이는 값은 dryrun 뿐이다(§1 의 email/push 확장 예정).
CHANNEL_DRYRUN = "dryrun"

# 억제 사유 — 고정 코드. 새 사유가 필요하면 여기 상수를 늘린다(자유 문자열 금지).
SUP_NOT_TODAY = "not_today"              # §4 소급 발송 금지
SUP_NO_ARTICLES = "no_articles"          # §4 수집 실패일
SUP_NOT_ACTIONABLE = "grade_not_actionable"   # §4 ⚪ 관망·중립·🟢 정합
SUP_BELOW_LEVEL = "level_below_alert"    # §2-1 기본값 🔴, ⚠️ 는 구독자 옵트다운
SUP_ALREADY_SENT = "already_sent"        # 같은 날짜·종류 재발송 금지
SUP_UNCHANGED = "grade_unchanged"        # §2-3 등급이 그대로인 확정판 전환

LEVEL_ALERT = "alert"        # 🔴 만
LEVEL_CAUTION = "caution"    # ⚠️ 이상

# data.js 의 confidenceLevel() 과 같은 규칙이어야 한다(§5). 게이트 임계값(15건·0.60)은
# news_signals 에서 가져오고, '높음' 조건만 여기 상수로 둔다 — 두 구현이 어긋나면
# tests/test_notifier.py 가 깨진다.
HIGH_MIN_ARTICLES = 30
HIGH_MAX_CI_WIDTH = 0.40

DISCLAIMER = "참고용이며 투자조언이 아닙니다."
PROVISIONAL = "회의록 반영 전 잠정치입니다."
SIGNALS_URL = "https://aicp-econpilot.github.io/#/signals"


@dataclass
class Decision:
    """발송 판정 결과. send=False 면 suppressed 에 사유 코드가 담긴다."""
    date: str
    kind: str                      # signal / correction
    grade: str
    fired: list
    send: bool
    suppressed: Optional[str] = None
    details: list = None           # 발동 신호의 detail 문자열
    confidence: str = "보통"
    news_only: bool = False        # 회의 사이 구간 — Fed 축 불변(§4)
    prev_grade: Optional[str] = None   # kind=correction 일 때 정정 전 등급


def confidence_label(n_articles, ci_lo, ci_hi) -> str:
    """신뢰도 높음/보통/낮음 — dashboard-web/src/lib/data.js 의 confidenceLevel() 과 동일."""
    n = n_articles or 0
    width = (ci_hi - ci_lo) if (ci_lo is not None and ci_hi is not None) else None
    if n < NEWS_TH.min_articles or (width is not None and width > NEWS_TH.ci_max):
        return "낮음"
    if n >= HIGH_MIN_ARTICLES and width is not None and width <= HIGH_MAX_CI_WIDTH:
        return "높음"
    return "보통"


def decide(date, grade, fired, n_articles, ci_lo, ci_hi, today,
           level=LEVEL_ALERT, sent=(), details=None, news_only=False) -> Decision:
    """일별 신호 알림을 보낼지. 순수 함수 — sent 는 이미 발송된 (date, kind) 집합."""
    d = Decision(date=date, kind="signal", grade=grade, fired=list(fired or []),
                 send=False, details=list(details or []),
                 confidence=confidence_label(n_articles, ci_lo, ci_hi),
                 news_only=news_only)

    if date != today:                              # §4 소급 발송 금지
        d.suppressed = SUP_NOT_TODAY
    elif (date, "signal") in sent:
        d.suppressed = SUP_ALREADY_SENT
    elif not n_articles:                           # §4 수집 실패일(0건·None)
        d.suppressed = SUP_NO_ARTICLES
    elif grade not in (GRADE_ALERT, GRADE_CAUTION):    # ⚪ 관망·중립·🟢 정합
        d.suppressed = SUP_NOT_ACTIONABLE
    elif grade == GRADE_CAUTION and level == LEVEL_ALERT:
        d.suppressed = SUP_BELOW_LEVEL
    else:
        d.send = True
    return d


def decide_correction(date, grade, grade_final, today, sent=()) -> Optional[Decision]:
    """§2-3 정정 알림 — grade_final 이 grade 와 **다를 때만**.

    회의록이 3주 뒤 도착해 과거 등급이 바뀌는 경우다. 소급 발송 금지(§4)의 예외가
    아니다 — 정정을 '오늘 알게 된 사실'로 보내므로 date 는 원래 신호일이지만 발송
    시점은 확정판이 도착한 날이다. grade_final 이 없으면 판정 자체를 하지 않는다.
    """
    if not grade_final:
        return None
    d = Decision(date=date, kind="correction", grade=grade_final, fired=[],
                 send=False, prev_grade=grade)
    if (date, "correction") in sent:
        d.suppressed = SUP_ALREADY_SENT
    elif grade_final == grade:
        d.suppressed = SUP_UNCHANGED
    else:
        d.send = True
    return d


# analysis/signals.py 의 detail 은 측정값을 괄호로 달고 온다
#   예) "⚠️ 괴리 — 연준 톤 긍정(+0.202) vs 시장 급락(-0.85%)"
# §5 는 지수·CI 폭·기사 수를 알림에서 제외하라고 못 박았으므로 그대로 실을 수 없다.
# 괄호 안에 숫자가 있는 덩어리만 통째로 걷어낸다 — 문구("괴리", "톤 긍정")는 남는다.
_NUMERIC_PAREN = re.compile(r"\s*\([^)]*\d[^)]*\)")


def strip_measurements(s: str) -> str:
    return _NUMERIC_PAREN.sub("", s)


def render(d: Decision) -> tuple:
    """(제목, 본문). §5 규격 — 숫자는 넣지 않는다.

    지수·CI 폭·기사 수는 사이트의 '상세보기'에만 있다. 이메일만 상세해지면 그 구분이
    무너진다(질문 3 피드백). 제목에 등급을 넣는 것은 받은편지함에서 열지 않고도
    판단할 수 있어야 하기 때문이다.
    """
    if d.kind == "correction":
        subject = f"[정정] {d.date} 등급이 {d.prev_grade} → {d.grade} 로 변경"
        lines = [f"{d.date} 신호의 등급이 확정판에서 바뀌었습니다.",
                 f"{d.prev_grade} → {d.grade}",
                 "",
                 "회의록이 도착해 Fed 축이 확정되면서 재평가된 결과입니다.",
                 "과거 실시간 값은 덮어쓰지 않고 정정 기록으로 남깁니다."]
    else:
        subject = f"{d.grade} · {d.date}"
        # §4 — 회의 사이 구간의 tone_shift 는 Fed 톤이 아니라 뉴스 감성이 움직인 것이다.
        reason = " · ".join(strip_measurements(x) for x in d.details) if d.details             else "발동 신호 없음"
        if d.news_only:
            reason = reason.replace("톤 개선", "뉴스 감성 개선").replace("톤 악화", "뉴스 감성 악화")
        lines = [f"{d.date} 등급: {d.grade}",
                 reason,
                 "",
                 f"신뢰도 {d.confidence}",
                 PROVISIONAL]

    lines += ["", DISCLAIMER, f"자세히 보기: {SIGNALS_URL}",
              "수신거부: (구독 기능 준비 중 — 드라이런)"]
    return subject, "\n".join(lines)


def read_log(path=None) -> set:
    """이미 기록된 (date, kind) 집합. 파일이 없으면 빈 집합."""
    p = Path(path or NOTIFICATION_LOG)
    if not p.exists():
        return set()
    with open(p, encoding="utf-8") as f:
        return {(r["date"], r["kind"]) for r in csv.DictReader(f)}


def append_log(d: Decision, path=None, channel=CHANNEL_DRYRUN) -> None:
    """§7-1 발송 로그 1행 append. 억제된 날도 남긴다 — 사유가 있어야 빈도가 읽힌다.

    덮어쓰지 않는다(질문 6 원칙의 연장). 개인 식별 정보는 어떤 컬럼에도 없다.
    """
    p = Path(path or NOTIFICATION_LOG)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"date": d.date, "kind": d.kind, "grade": d.grade,
                    "fired": ";".join(d.fired), "channel": channel,
                    "n_recipients": 0 if d.send else "",   # 드라이런이라 항상 0
                    "n_failed": 0 if d.send else "",
                    "suppressed_reason": d.suppressed or ""})
