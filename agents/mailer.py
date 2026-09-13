"""알림 실제 발송 — 명단 조회 · 개인별 발송 · 드라이런 스위치.

판정은 agents/notifier.py 가 한다. 이 모듈은 판정이 send 인 결정을 받아 부치기만 한다.
notifier.py 가 발송 모듈을 import 하지 않는다는 잠금(tests/test_notifier_node.py)을
지키려고 발송을 여기에 따로 둔다.

설계: docs/superpowers/specs/2026-09-13-alert-delivery-design.md

★받는 사람 주소를 로그·notes·예외 메시지 어디에도 넣지 않는다. notes 는 파이프라인
  로그로 흘러가고, 그 로그는 PUBLIC 리포에 커밋될 수 있다.
"""
import os
import time

import requests

from agents import notifier as nt

FROM = "EconPilot <noreply@econpilot.org>"
RESEND_URL = "https://api.resend.com/emails"
EXPORT_URL = "https://econpilot.org/api/export"
UNSUB_BASE = "https://econpilot.org/api/unsubscribe?t="
TEAM_FOOTER = "팀 고정 수신자입니다. 수신을 원치 않으면 팀에 알려주세요."
FED_KINDS = ("fed_meeting", "fed_minutes")
SEND_GAP_SEC = 0.6     # Resend API 초당 요청 제한 아래로 (설계 §5-1)
TIMEOUT = 15


def send_enabled(env=None) -> bool:
    """저장소 변수 ALERT_SEND 가 정확히 "1" 일 때만 실제 발송 (설계 §6-1)."""
    env = os.environ if env is None else env
    return env.get("ALERT_SEND", "") == "1"


def _norm(email):
    return email.strip().lower()


def parse_team(raw) -> list:
    """GitHub Secret ALERT_RECIPIENTS — 쉼표 구분. 정규화하고 빈칸·중복을 뺀다."""
    seen, out = set(), []
    for part in (raw or "").split(","):
        e = _norm(part)
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def fetch_subscribers(token, get=requests.get):
    """Worker 구독자 명단. (레코드 리스트, 오류 문구 또는 None). 예외를 던지지 않는다.

    실패해도 호출부는 팀원에게는 보낸다 — 명단 조회 실패로 경고 메일 전체가
    사라지는 것이 더 나쁘다 (설계 §4).
    """
    if not token:
        return [], "SUBSCRIBERS_TOKEN 없음 — 구독자 조회 생략"
    try:
        r = get(EXPORT_URL, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    except Exception as e:
        return [], f"구독자 조회 실패: {type(e).__name__}"
    if r.status_code != 200:
        return [], f"구독자 조회 실패: HTTP {r.status_code}"
    try:
        return list(r.json().get("subscribers") or []), None
    except Exception:
        return [], "구독자 조회 실패: 응답 형식 오류"


def build_recipients(team, subscribers) -> list:
    """팀 ∪ 구독자. 같은 주소는 한 번만이고, 겹치면 팀이 이긴다 (해지 토큰 없이)."""
    out, seen = [], set()
    for e in team:
        out.append({"email": e, "team": True, "unsub_token": None, "fed_events": True})
        seen.add(e)
    for s in subscribers:
        if not isinstance(s, dict):
            continue
        e = _norm(s.get("email") or "")
        if not e or e in seen:
            continue
        seen.add(e)
        out.append({"email": e, "team": False, "unsub_token": s.get("unsub_token"),
                    "fed_events": s.get("fed_events", True) is not False})
    return out


def wants(recipient, decision) -> bool:
    """fed_events=false 구독자는 FOMC 일정 알림만 뺀다 (설계 §5-3).
    신호·정정 메일에 합쳐진 일정은 신호 메일이므로 보낸다."""
    return not (decision.kind in FED_KINDS and not recipient["fed_events"])


def _payload(recipient, decision):
    if recipient["team"]:
        footer, headers = TEAM_FOOTER, {}
    else:
        url = UNSUB_BASE + (recipient["unsub_token"] or "")
        footer = f"수신거부: {url}"
        headers = {"List-Unsubscribe": f"<{url}>",
                   "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    subject, body = nt.render(decision, footer=footer)
    payload = {"from": FROM, "to": [recipient["email"]], "subject": subject, "text": body}
    if headers:
        payload["headers"] = headers
    return payload


def deliver(decision, env=None, get=requests.get, post=requests.post, sleep=time.sleep):
    """decision 을 받는 사람마다 한 통씩 보낸다.

    반환 (channel, n_recipients, n_failed, notes). 스위치가 꺼져 있으면 네트워크를
    쓰지 않고 ("dryrun", 0, 0, []). 어떤 경우에도 예외를 던지지 않는다 — 발송이
    파이프라인을 죽이지 않는다 (설계 §5-4). 일부가 실패해도 재시도하지 않는다.
    """
    env = os.environ if env is None else env
    if not send_enabled(env):
        return nt.CHANNEL_DRYRUN, 0, 0, []

    notes = []
    team = parse_team(env.get("ALERT_RECIPIENTS"))
    subs, err = fetch_subscribers(env.get("SUBSCRIBERS_TOKEN"), get=get)
    if err:
        notes.append(err)
    targets = [r for r in build_recipients(team, subs) if wants(r, decision)]

    key = env.get("RESEND_API_KEY")
    if not key:
        notes.append("RESEND_API_KEY 없음 — 전원 실패로 기록")
        return nt.CHANNEL_EMAIL, len(targets), len(targets), notes

    failed = 0
    for i, rcp in enumerate(targets):
        if i:
            sleep(SEND_GAP_SEC)
        try:
            r = post(RESEND_URL, json=_payload(rcp, decision),
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
            if not 200 <= r.status_code < 300:
                failed += 1
        except Exception:
            failed += 1          # 한 명의 실패가 나머지를 멈추지 않는다
    if failed:
        notes.append(f"발송 실패 {failed}/{len(targets)}")
    return nt.CHANNEL_EMAIL, len(targets), failed, notes
