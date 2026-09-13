"""Notifier — 발송 판정과 본문 생성 (docs/notification_design.md §2·§4·§5·§7-1).

**판정만 한다.** 이 파일은 smtplib·resend·requests 를 import 하지 않는다. 실제 발송은
agents/mailer.py 가 맡고, 저장소 변수 ALERT_SEND 가 "1" 일 때만 나간다
(docs/superpowers/specs/2026-09-13-alert-delivery-design.md). 그 외에는 드라이런이다.

판정(decide·decide_correction)과 렌더(render)는 **순수 함수**다. 네트워크·DB·파일에
의존하지 않으므로 단위테스트가 결정적이다. 파일을 만지는 것은 append_log·read_sent 뿐.

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

# 발송 채널. ALERT_SEND 가 꺼져 있으면 dryrun, 켜져 있으면 email (push 는 §1 확장 예정).
CHANNEL_DRYRUN = "dryrun"
CHANNEL_EMAIL = "email"      # ALERT_SEND=1 로 실제 발송했을 때 (agents/mailer.py)

# 억제 사유 — 고정 코드. 새 사유가 필요하면 여기 상수를 늘린다(자유 문자열 금지).
SUP_NOT_TODAY = "not_today"              # §4 소급 발송 금지
SUP_NO_ARTICLES = "no_articles"          # §4 수집 실패일
SUP_NO_MARKET = "no_market_data"         # 주말·휴장일·시장 수집 실패 — 비교 대상 없음
SUP_NOT_ACTIONABLE = "grade_not_actionable"   # §4 ⚪ 관망·중립·🟢 정합
SUP_BELOW_LEVEL = "level_below_alert"    # §2-1 기본값 🔴, ⚠️ 는 구독자 옵트다운
SUP_ALREADY_SENT = "already_sent"        # 같은 날짜·종류 재발송 금지
SUP_UNCHANGED = "grade_unchanged"        # §2-3 등급이 그대로인 확정판 전환
SUP_MERGED = "merged_same_day"           # §2-2 같은 날 같은 회의의 다른 메일에 합쳐짐

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
    kind: str                      # signal / correction / fed_meeting / fed_minutes
    grade: str
    fired: list
    send: bool
    suppressed: Optional[str] = None
    details: list = None           # 발동 신호의 detail 문자열
    confidence: str = "보통"
    news_only: bool = False        # 회의 사이 구간 — Fed 축 불변(§4)
    prev_grade: Optional[str] = None   # kind=correction 일 때 정정 전 등급
    fed_event: Optional[str] = None    # 이 메일에 합쳐진 Fed 일정 — "meeting" / "minutes"


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
           level=LEVEL_ALERT, sent=(), details=None, news_only=False,
           has_market=True) -> Decision:
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
    elif not has_market:
        # 시장 데이터가 없는 날. 주말·미국 휴장일·수집 실패 셋을 구분하지 않는다 —
        # 로그에 쓸 수 있는 것은 "비교할 시장이 없었다"까지이고, 셋 다 보내지
        # 않을 이유로는 같다. 알림은 톤을 시장 반응과 견주는 것이라 견줄 것이
        # 없으면 성립하지 않는다.
        #
        # 등급 판정보다 **앞**에 둔다. 뒤에 두면 🟢·⚪ 인 휴장일이
        # grade_not_actionable 로 먼저 걸려 휴장이었다는 사실이 로그에서 사라진다.
        # 이 로그는 발송 빈도를 읽으려고 남기는 것이므로 사유가 정확해야 한다.
        #
        # 실질적으로 걸리는 것은 ⚠️ 뿐이다 — divergence 는 |시장반응| ≥ 0.80% 를
        # 요구하므로 휴장일엔 애초에 켜지지 않는다. 그래도 등급과 무관하게 막는다.
        d.suppressed = SUP_NO_MARKET
    elif grade not in (GRADE_ALERT, GRADE_CAUTION):    # ⚪ 관망·중립·🟢 정합
        d.suppressed = SUP_NOT_ACTIONABLE
    elif grade == GRADE_CAUTION and level == LEVEL_ALERT:
        d.suppressed = SUP_BELOW_LEVEL
    else:
        d.send = True
    return d


def decide_correction(date, grade, grade_final, today, sent=()) -> Optional[Decision]:
    """§2-3 정정 알림 — grade_final 이 grade 와 **다르고**, 전후 중 하나가 🔴 일 때만.

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
    elif GRADE_ALERT not in (grade, grade_final):
        # 전후 어느 쪽도 🔴 이 아니면 보내지 않는다. 원본이 ⚠️ 였다면 기본 발송
        # 등급(§2-1)에 미달해 애초에 나가지 않았고, 나가지도 않은 알림의 정정은
        # 받는 쪽에 맥락이 없다. 반대로 확정판이 🔴 이면 원본과 무관하게 보낸다.
        d.suppressed = SUP_NOT_ACTIONABLE
    else:
        d.send = True
    return d


# analysis/signals.py 의 detail 은 측정값을 괄호로 달고 온다
#   예) "⚠️ 괴리 — 연준 톤 긍정(+0.202) vs 시장 급락(-0.85%)"
# §5 는 지수·CI 폭·기사 수를 알림에서 제외하라고 못 박았으므로 그대로 실을 수 없다.
# 괄호 안에 숫자가 있는 덩어리만 통째로 걷어낸다 — 문구("괴리", "톤 긍정")는 남는다.
_NUMERIC_PAREN = re.compile(r"\s*\([^)]*\d[^)]*\)")


def decide_fed_meeting(date, today, grade="", sent=(), signal_sends=False) -> Decision:
    """§2-2 FOMC 회의일 알림 — 성명문·기자회견을 한 통으로.

    같은 날 같은 회의에 메일이 두 통 가지 않게 한다(조교 피드백 2026-09-10).
    그날 🔴 신호 메일이 나가면 일정은 그 메일에 합치고(merged), 신호가 조용하면
    일정 알림이 따로 1통 나간다. 등급·게이트·휴장은 보지 않는다 — 일정 통보라서다.
    """
    d = Decision(date=date, kind="fed_meeting", grade=grade, fired=[], send=False)
    if date != today:                              # 회의록 재방문 실행 등
        d.suppressed = SUP_NOT_TODAY
    elif (date, "fed_meeting") in sent or (date, "signal") in sent:
        # 신호 메일이 이미 나갔다면 일정은 거기 합쳐져 나간 것이다.
        d.suppressed = SUP_ALREADY_SENT
    elif signal_sends:
        d.suppressed = SUP_MERGED
    else:
        d.send = True
    return d


def decide_fed_minutes(date, grade_final, sent=(), correction_sends=False) -> Decision:
    """§2-2 회의록 공개 알림 — **실제 도착일** 기준.

    예정일로 보내면 "공개"라고 했는데 아직 없는 날이 생긴다(2026-08-03 회의 회의록은
    3주가 지나도 오지 않았다, §3). 회의록 도착은 곧 확정판이 나오는 날이라 정정
    알림(§2-3)과 겹칠 수 있다 — 정정이 나가면 그 메일에 합친다.

    date 는 회의일이고 발송은 도착일이므로 not_today 를 걸지 않는다(정정과 같다).
    과거 회의 재처리에서 울리지 않게 하는 가드는 호출부(graph)가 건다 — 그 회의의
    속보치 기록이 있을 때만 부른다.
    """
    d = Decision(date=date, kind="fed_minutes", grade=grade_final, fired=[], send=False)
    if (date, "fed_minutes") in sent or (date, "correction") in sent:
        d.suppressed = SUP_ALREADY_SENT
    elif correction_sends:
        d.suppressed = SUP_MERGED
    else:
        d.send = True
    return d


def strip_measurements(s: str) -> str:
    return _NUMERIC_PAREN.sub("", s)


def render(d: Decision, footer: Optional[str] = None) -> tuple:
    """(제목, 본문). §5 규격 — 숫자는 넣지 않는다.

    지수·CI 폭·기사 수는 사이트의 '상세보기'에만 있다. 이메일만 상세해지면 그 구분이
    무너진다(질문 3 피드백). 제목에 등급을 넣는 것은 받은편지함에서 열지 않고도
    판단할 수 있어야 하기 때문이다.
    """
    if d.kind == "fed_meeting":
        subject = f"[FOMC] {d.date} 결과 발표"
        lines = [f"오늘은 FOMC 결과 발표일입니다 (성명문 · 기자회견).",
                 f"오늘의 신호: {d.grade}" if d.grade else "오늘의 신호: 산출 전",
                 "",
                 "회의록은 약 3주 뒤 공개되며, 그때 확정판 등급을 다시 알립니다.",
                 PROVISIONAL]
    elif d.kind == "fed_minutes":
        subject = f"[FOMC] {d.date} 회의 회의록 반영"
        lines = [f"{d.date} FOMC 회의록이 공개되었습니다.",
                 f"회의록까지 반영한 확정판 등급: {d.grade} (속보치와 같음)"]
    elif d.kind == "correction":
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

    # §2-2 같은 날 같은 회의 — 일정 알림이 이 메일에 합쳐졌으면 제목·첫 줄로 드러낸다.
    if d.fed_event == "meeting":
        subject = f"[FOMC] {subject}"
        lines.insert(0, "오늘은 FOMC 결과 발표일입니다 (성명문 · 기자회견).")
    elif d.fed_event == "minutes":
        subject = subject.replace("[정정]", "[FOMC 회의록 · 정정]", 1)
        lines.insert(0, f"{d.date} FOMC 회의록이 공개되었습니다.")

    # 실제 발송 시 mailer 가 수신자별 푸터(해지 링크 또는 팀 고정 안내)를 넘긴다.
    # 인자가 없으면 드라이런 푸터 그대로다.
    lines += ["", DISCLAIMER, f"자세히 보기: {SIGNALS_URL}",
              footer if footer is not None else "수신거부: (구독 기능 준비 중 — 드라이런)"]
    return subject, "\n".join(lines)


def read_sent(path=None) -> set:
    """**실제로 나간** (date, kind) 집합. 파일이 없으면 빈 집합.

    억제된 행(`suppressed_reason` 이 있는 행)은 세지 않는다. append_log 는
    안 보낸 날도 사유와 함께 남기므로(§7-1), 기록된 행을 전부 '보냈다'로 치면
    **한 통도 안 나간 날이 재실행에서 already_sent 로 막힌다** — 오전에 수집이
    실패해 no_articles 로 한 줄 남으면 오후 재실행으로 복구할 수 없었다.

    채널로는 거르지 않는다. 드라이런에서도 "보냈을 날"은 중복 기록을 막아야
    발송을 켠 뒤와 같은 규칙으로 돈다.
    """
    p = Path(path or NOTIFICATION_LOG)
    if not p.exists():
        return set()
    with open(p, encoding="utf-8") as f:
        return {(r["date"], r["kind"]) for r in csv.DictReader(f)
                if not r["suppressed_reason"]}


def append_log(d: Decision, path=None, channel=CHANNEL_DRYRUN,
               n_recipients=None, n_failed=None) -> None:
    """§7-1 발송 로그 1행 append. 억제된 날도 남긴다 — 사유가 있어야 빈도가 읽힌다.

    덮어쓰지 않는다(질문 6 원칙의 연장). 개인 식별 정보는 어떤 컬럼에도 없다.

    **하루 1행은 정상 운영 시의 관찰이지 불변식이 아니다.** 억제된 날을 같은 날
    재실행하면 행이 하나 더 쌓인다(read_sent 참조) — 두 번 시도한 사실이 남는
    것이므로 맞는 동작이다. 발송 빈도를 셀 때는 (date, kind) 로 중복을 제거할 것.

    n_recipients · n_failed 는 실제 발송 결과(agents/mailer.py)다. 넘기지 않으면
    드라이런 값 — send 면 0, 억제면 빈칸 — 을 쓴다.
    """
    p = Path(path or NOTIFICATION_LOG)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        if n_recipients is None:
            n_recipients = 0 if d.send else ""
        if n_failed is None:
            n_failed = 0 if d.send else ""
        w.writerow({"date": d.date, "kind": d.kind, "grade": d.grade,
                    "fired": ";".join(d.fired), "channel": channel,
                    "n_recipients": n_recipients,
                    "n_failed": n_failed,
                    "suppressed_reason": d.suppressed or ""})
