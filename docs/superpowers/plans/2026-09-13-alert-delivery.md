# 알림 실제 발송 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 판정이 `send` 인 알림을 팀 고정 명단과 구독자에게 한 명씩 실제로 메일로 보내고, 대시보드 신호 탭에 공개 구독 폼을 둔다 — 두 스위치가 모두 꺼진 채로 머지한다.

**Architecture:** 판정은 기존 `agents/notifier.py`, 발송은 새 `agents/mailer.py` 가 맡는다. `agents/graph.py` 의 `notifier_node` 가 `send` 인 결정마다 `mailer.deliver()` 를 부르고 결과(채널·수신자 수·실패 수)를 로그에 남긴다. 발송은 환경변수 `ALERT_SEND="1"` 일 때만 네트워크를 쓴다. 대시보드는 React 컴포넌트 하나와 순수 함수 모듈 하나를 더하고 소스 상수로 끈다.

**Tech Stack:** Python 3.13 · pytest · requests · Resend HTTP API · Cloudflare Worker(`/api/export`, 기존) · React 18 + Vite · Node 24 내장 `node:test`

**Spec:** `docs/superpowers/specs/2026-09-13-alert-delivery-design.md`

## Global Constraints

- **구독자·팀 이메일 주소를 리포·로그·커밋 메시지 어디에도 넣지 않는다.** 리포가 PUBLIC 이다. 로그에는 수신자 "수"만 쓴다.
- **`agents/notifier.py` 는 발송 모듈을 import 하지 않는다.** `tests/test_notifier_node.py` 의 잠금(`smtplib`·`resend`·`requests`·`sendgrid`·`urllib`)을 깨지 않는다. 발송은 `agents/mailer.py` 에만 둔다.
- 스위치가 꺼져 있으면(`ALERT_SEND` 가 `"1"` 이 아니면) **네트워크 호출 0건, 로그는 지금과 동일**(`dryrun`, 발송 판정 행은 수신자 0).
- 발신 주소: `EconPilot <noreply@econpilot.org>`
- 해지 링크: `https://econpilot.org/api/unsubscribe?t=<unsub_token>`
- 명단 조회: `GET https://econpilot.org/api/export`, 헤더 `Authorization: Bearer <SUBSCRIBERS_TOKEN>`
- 팀 푸터 문구: `팀 고정 수신자입니다. 수신을 원치 않으면 팀에 알려주세요.`
- 수신자 사이 간격: 0.6초
- 폼 스위치 상수: `dashboard-web/src/lib/data.js` 의 `SUBSCRIBE_OPEN = false`
- 테스트 명령: `python -m pytest tests/ -q` (Python), `node --test dashboard-web/src/lib/subscribe.test.js` (대시보드)
- 커밋 메시지는 한국어. 끝에 다음 두 줄:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016WPyrTBW2aq3RPSob5jUE1
  ```

## File Structure

| 파일 | 책임 |
|---|---|
| `agents/notifier.py` (수정) | `render` 가 푸터를 인자로 받고, `append_log` 가 채널·수신자 수·실패 수를 인자로 받는다. `CHANNEL_EMAIL` 상수 |
| `agents/mailer.py` (신규) | 발송 스위치 · 팀 명단 파싱 · 구독자 조회 · 명단 합치기 · 개인별 발송. 네트워크 함수는 인자로 주입 |
| `agents/graph.py` (수정) | `notifier_node` 가 `send` 결정을 발송하고 **발송 뒤에** 로그 |
| `tests/conftest.py` (수정) | 테스트 중 `ALERT_SEND` 강제 해제 |
| `tests/test_mailer.py` (신규) | mailer 단위 테스트 — 네트워크 없음 |
| `.github/workflows/daily-news.yml` (수정) | 시크릿 3개·변수 1개 전달 |
| `dashboard-web/src/lib/data.js` (수정) | `SUBSCRIBE_OPEN` 상수 |
| `dashboard-web/src/lib/subscribe.js` (신규) | 신청 요청과 응답 문구 — 순수 함수 |
| `dashboard-web/src/lib/subscribe.test.js` (신규) | 위 모듈 테스트 (`node:test`) |
| `dashboard-web/src/components/SubscribeForm.jsx` (신규) | "알림 받기" 섹션 |
| `dashboard-web/src/pages/Signals.jsx` (수정) | 스위치가 켜졌을 때만 폼을 맨 위에 그림 |

---

### Task 1: notifier — 푸터 인자와 로그 수신자 수

**Files:**
- Modify: `agents/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `CHANNEL_EMAIL = "email"`
  - `render(d: Decision, footer: Optional[str] = None) -> tuple[str, str]` — `footer` 가 None 이면 기존 드라이런 푸터 `"수신거부: (구독 기능 준비 중 — 드라이런)"`
  - `append_log(d, path=None, channel=CHANNEL_DRYRUN, n_recipients=None, n_failed=None) -> None` — 두 수가 None 이면 기존 값(`send` 면 0, 아니면 빈칸)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_notifier.py` 의 import 블록에서 `LEVEL_CAUTION,` 줄 다음에 `CHANNEL_EMAIL,` 을 추가한다:

```python
from agents.notifier import (
    LOG_FIELDS,
    LEVEL_ALERT,
    LEVEL_CAUTION,
    CHANNEL_EMAIL,
```

파일 끝에 추가한다:

```python
# --- 실제 발송 연결 (알림 발송 설계 §5-2 · §7) ---------------------------------
def test_render_uses_given_footer_instead_of_dryrun_line():
    d = decide(TODAY, GRADE_ALERT, ["divergence"], **OK)
    _, body = render(d, footer="수신거부: https://econpilot.org/api/unsubscribe?t=abc")
    assert "https://econpilot.org/api/unsubscribe?t=abc" in body
    assert "드라이런" not in body

def test_render_default_footer_unchanged():
    d = decide(TODAY, GRADE_ALERT, ["divergence"], **OK)
    _, body = render(d)
    assert "수신거부: (구독 기능 준비 중 — 드라이런)" in body

def test_log_records_channel_and_counts(tmp_path):
    p = tmp_path / "notification_log.csv"
    append_log(decide(TODAY, GRADE_ALERT, ["divergence"], **OK), path=p,
               channel=CHANNEL_EMAIL, n_recipients=5, n_failed=1)
    row = list(csv.DictReader(open(p, encoding="utf-8")))[0]
    assert row["channel"] == "email"
    assert row["n_recipients"] == "5" and row["n_failed"] == "1"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_notifier.py -q`
Expected: FAIL — `ImportError: cannot import name 'CHANNEL_EMAIL'`

- [ ] **Step 3: 구현**

`agents/notifier.py` 에서 `CHANNEL_DRYRUN = "dryrun"` 줄 바로 다음에 추가한다:

```python
CHANNEL_EMAIL = "email"      # ALERT_SEND=1 로 실제 발송했을 때 (agents/mailer.py)
```

`render` 의 시그니처를 바꾼다:

```python
def render(d: Decision, footer: Optional[str] = None) -> tuple:
```

`render` 끝의 푸터 줄을 바꾼다. 기존:

```python
    lines += ["", DISCLAIMER, f"자세히 보기: {SIGNALS_URL}",
              "수신거부: (구독 기능 준비 중 — 드라이런)"]
```

다음으로:

```python
    # 실제 발송 시 mailer 가 수신자별 푸터(해지 링크 또는 팀 고정 안내)를 넘긴다.
    # 인자가 없으면 드라이런 푸터 그대로다.
    lines += ["", DISCLAIMER, f"자세히 보기: {SIGNALS_URL}",
              footer if footer is not None else "수신거부: (구독 기능 준비 중 — 드라이런)"]
```

`append_log` 시그니처와 기록부를 바꾼다. 시그니처:

```python
def append_log(d: Decision, path=None, channel=CHANNEL_DRYRUN,
               n_recipients=None, n_failed=None) -> None:
```

독스트링 끝(닫는 `"""` 바로 앞)에 한 단락을 더한다:

```python
    n_recipients · n_failed 는 실제 발송 결과(agents/mailer.py)다. 넘기지 않으면
    드라이런 값 — send 면 0, 억제면 빈칸 — 을 쓴다.
```

`w.writerow({...})` 바로 앞에 추가하고, writerow 의 두 필드를 변수로 바꾼다:

```python
    if n_recipients is None:
        n_recipients = 0 if d.send else ""
    if n_failed is None:
        n_failed = 0 if d.send else ""
```

```python
        w.writerow({"date": d.date, "kind": d.kind, "grade": d.grade,
                    "fired": ";".join(d.fired), "channel": channel,
                    "n_recipients": n_recipients,
                    "n_failed": n_failed,
                    "suppressed_reason": d.suppressed or ""})
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS (기존 테스트 포함)

- [ ] **Step 5: 커밋**

```bash
git add agents/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): 렌더 푸터 인자 · 로그 수신자 수 인자 — 실제 발송 연결 준비"
```

---

### Task 2: mailer — 명단과 개인별 발송

**Files:**
- Create: `agents/mailer.py`
- Test: `tests/test_mailer.py`

**Interfaces:**
- Consumes: `notifier.render(d, footer=)`, `notifier.CHANNEL_DRYRUN`, `notifier.CHANNEL_EMAIL`, `notifier.decide`, `notifier.decide_fed_meeting` (Task 1 및 기존)
- Produces:
  - `send_enabled(env=None) -> bool`
  - `parse_team(raw: str | None) -> list[str]`
  - `fetch_subscribers(token, get=requests.get) -> tuple[list[dict], str | None]`
  - `build_recipients(team: list[str], subscribers: list[dict]) -> list[dict]` — 원소 `{"email", "team", "unsub_token", "fed_events"}`
  - `wants(recipient: dict, decision) -> bool`
  - `deliver(decision, env=None, get=requests.get, post=requests.post, sleep=time.sleep) -> tuple[str, int, int, list[str]]` — `(channel, n_recipients, n_failed, notes)`. 예외를 던지지 않는다. notes 에는 주소를 넣지 않는다

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_mailer.py`:

```python
"""mailer 단위 테스트 — 네트워크 없음. get/post/sleep 를 가짜로 주입한다.

설계: docs/superpowers/specs/2026-09-13-alert-delivery-design.md §4 · §5
"""
from agents import mailer
from agents.notifier import decide, decide_fed_meeting
from analysis.signals import GRADE_ALERT, GRADE_NEUTRAL

TODAY = "2026-08-20"
OK = dict(n_articles=40, ci_lo=-0.10, ci_hi=0.20, today=TODAY)
ON = {"ALERT_SEND": "1", "RESEND_API_KEY": "k", "SUBSCRIBERS_TOKEN": "t",
      "ALERT_RECIPIENTS": "a@team.org, B@Team.org ,,a@team.org"}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _alert():
    return decide(TODAY, GRADE_ALERT, ["divergence"], **OK)


def _export(*subs):
    return lambda *a, **k: Resp(200, {"subscribers": list(subs), "count": len(subs)})


def _collect():
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return Resp(200, {"id": "x"})
    return calls, post


def _boom(*a, **k):
    raise AssertionError("네트워크를 쓰면 안 된다")


def test_dryrun_makes_no_network_calls():
    assert mailer.deliver(_alert(), env={}, get=_boom, post=_boom, sleep=_boom) == \
        ("dryrun", 0, 0, [])


def test_parse_team_normalizes_and_dedups():
    assert mailer.parse_team(" a@team.org, B@Team.org ,,a@team.org") == \
        ["a@team.org", "b@team.org"]


def test_team_wins_when_same_address_subscribed():
    r = mailer.build_recipients(["a@team.org"],
                                [{"email": "A@team.org", "unsub_token": "tok"}])
    assert len(r) == 1 and r[0]["team"] is True and r[0]["unsub_token"] is None


def test_one_request_per_recipient():
    """받는 사람끼리 주소가 보이면 안 된다 — 요청 1건당 수신자 1명."""
    calls, post = _collect()
    ch, n, failed, _ = mailer.deliver(
        _alert(), env=ON, post=post, sleep=lambda s: None,
        get=_export({"email": "prof@uni.ac.kr", "unsub_token": "tok"}))
    assert (ch, n, failed) == ("email", 3, 0)
    assert all(len(c["to"]) == 1 for c in calls)


def test_subscriber_gets_unsubscribe_link_team_does_not():
    calls, post = _collect()
    mailer.deliver(_alert(), env=ON, post=post, sleep=lambda s: None,
                   get=_export({"email": "prof@uni.ac.kr", "unsub_token": "tok"}))
    team = next(c for c in calls if c["to"] == ["a@team.org"])
    sub = next(c for c in calls if c["to"] == ["prof@uni.ac.kr"])
    assert mailer.TEAM_FOOTER in team["text"] and "headers" not in team
    assert "https://econpilot.org/api/unsubscribe?t=tok" in sub["text"]
    assert sub["headers"]["List-Unsubscribe"] == \
        "<https://econpilot.org/api/unsubscribe?t=tok>"
    assert sub["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert all(c["from"] == "EconPilot <noreply@econpilot.org>" for c in calls)


def test_export_failure_still_sends_to_team():
    calls, post = _collect()
    ch, n, failed, notes = mailer.deliver(
        _alert(), env=ON, post=post, sleep=lambda s: None,
        get=lambda *a, **k: Resp(500))
    assert (n, failed) == (2, 0)
    assert any("구독자 조회 실패" in x for x in notes)


def test_one_failure_does_not_stop_others():
    sent = []

    def post(url, json=None, headers=None, timeout=None):
        sent.append(json["to"][0])
        if len(sent) == 1:
            raise RuntimeError("resend down")
        return Resp(200)
    ch, n, failed, notes = mailer.deliver(_alert(), env=ON, post=post,
                                          sleep=lambda s: None, get=_export())
    assert (n, failed) == (2, 1) and len(sent) == 2


def test_fed_events_false_skips_fed_notices_only():
    calls, post = _collect()
    sub = {"email": "prof@uni.ac.kr", "unsub_token": "tok", "fed_events": False}
    env = dict(ON, ALERT_RECIPIENTS="")
    fm = decide_fed_meeting(TODAY, TODAY, grade=GRADE_NEUTRAL)
    assert mailer.deliver(fm, env=env, post=post, sleep=lambda s: None,
                          get=_export(sub))[1] == 0
    assert mailer.deliver(_alert(), env=env, post=post, sleep=lambda s: None,
                          get=_export(sub))[1] == 1


def test_missing_api_key_counts_everyone_failed():
    env = dict(ON, RESEND_API_KEY="")
    ch, n, failed, notes = mailer.deliver(_alert(), env=env, post=_boom,
                                          sleep=lambda s: None, get=_export())
    assert (ch, n, failed) == ("email", 2, 2)


def test_gap_between_recipients():
    gaps = []
    _, post = _collect()
    mailer.deliver(_alert(), env=ON, post=post, sleep=gaps.append,
                   get=_export({"email": "prof@uni.ac.kr", "unsub_token": "tok"}))
    assert gaps == [mailer.SEND_GAP_SEC, mailer.SEND_GAP_SEC]


def test_notes_never_contain_addresses():
    """로그로 흘러가는 문구에 주소가 섞이면 PUBLIC 리포 로그에 남는다."""
    def post(url, json=None, headers=None, timeout=None):
        return Resp(422)
    _, _, _, notes = mailer.deliver(_alert(), env=ON, post=post, sleep=lambda s: None,
                                    get=lambda *a, **k: Resp(401))
    assert notes and all("@" not in x for x in notes)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_mailer.py -q`
Expected: FAIL — `ImportError: cannot import name 'mailer' from 'agents'`

- [ ] **Step 3: 구현**

`agents/mailer.py`:

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS. `tests/test_notifier_node.py` 의 발송 모듈 import 금지 잠금도 통과해야 한다 (그 테스트는 `agents/notifier.py` 만 검사한다).

- [ ] **Step 5: 커밋**

```bash
git add agents/mailer.py tests/test_mailer.py
git commit -m "feat(mailer): 팀 고정 명단 + 구독자 개인별 발송, 스위치 꺼지면 네트워크 0"
```

---

### Task 3: graph 배선 · 테스트 안전장치 · 워크플로

**Files:**
- Modify: `agents/graph.py` (`notifier_node` 전체)
- Modify: `tests/conftest.py`
- Modify: `tests/test_notifier_node.py`
- Modify: `.github/workflows/daily-news.yml`

**Interfaces:**
- Consumes: `mailer.deliver(decision) -> (channel, n, failed, notes)` (Task 2), `notifier.append_log(..., channel, n_recipients, n_failed)`, `notifier.CHANNEL_DRYRUN`, `notifier.CHANNEL_EMAIL` (Task 1)
- Produces: 동작 변경만. 스위치가 꺼져 있으면 로그·로그 문구가 지금과 같다(`"드라이런 발송"` 문구 유지)

- [ ] **Step 1: 테스트 안전장치 — conftest**

`tests/conftest.py` 의 픽스처 본문 끝(`monkeypatch.setattr(vintage, ...)` 줄 다음)에 추가한다:

```python
    # 개발자 셸에 ALERT_SEND=1 이 켜져 있어도 테스트는 절대 실제 메일을 보내지 않는다.
    monkeypatch.delenv("ALERT_SEND", raising=False)
```

- [ ] **Step 2: 실패하는 노드 테스트 작성**

`tests/test_notifier_node.py` 의 import 줄을 바꾼다. 기존:

```python
from agents import graph, notifier as nt
```

다음으로:

```python
from agents import graph, mailer, notifier as nt
```

파일 끝에 추가한다:

```python
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


def test_delivery_exception_does_not_crash_node(tmp_path, monkeypatch):
    p = _today(monkeypatch, tmp_path, "2026-08-20")

    def boom(d):
        raise RuntimeError("resend down")
    monkeypatch.setattr(mailer, "deliver", boom)
    out = graph.notifier_node(_state("2026-08-20", GRADE_ALERT, ["divergence"]))
    assert _rows(p)[0]["channel"] == "email"
    assert any("발송 단계 예외" in line for line in out["log"])


def test_suppressed_decision_is_not_delivered(tmp_path, monkeypatch):
    _today(monkeypatch, tmp_path, "2026-08-20")

    def must_not_call(d):
        raise AssertionError("억제된 결정을 보내면 안 된다")
    monkeypatch.setattr(mailer, "deliver", must_not_call)
    graph.notifier_node(_state("2026-08-20", GRADE_ALIGNED, []))
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_notifier_node.py -q`
Expected: `test_sent_decision_logs_email_channel_and_counts` · `test_delivery_exception_does_not_crash_node` FAIL (graph 가 아직 mailer 를 부르지 않아 channel 이 `dryrun`)

- [ ] **Step 4: 구현 — `notifier_node` 교체**

`agents/graph.py` 의 `def notifier_node(state: State) -> State:` 부터 `# ── ⑥ Reporting ──` 바로 앞까지를 다음으로 통째로 바꾼다:

```python
def notifier_node(state: State) -> State:
    """규칙 기반 발송 판정 — 판단 없이 전달만 한다(§10-5).

    판정은 agents/notifier.py, 발송은 agents/mailer.py 가 한다. 실제 메일은 저장소
    변수 ALERT_SEND 가 "1" 일 때만 나가고, 그 외에는 드라이런이다
    (docs/superpowers/specs/2026-09-13-alert-delivery-design.md §6-1).

    판정마다 outputs/notification_log.csv 에 한 행을 남기되 **발송 뒤에** 쓴다 —
    수신자 수를 알아야 기록할 수 있다. 억제된 결정도 사유 코드와 함께 남긴다(§7-1).

    reporting 앞에 두는 이유: reporting 이 daily_signals.csv 를 쓰기 전이라
    _recorded_grade() 가 '이번 실행 이전'의 속보치를 읽는다. 정정 판정(§2-3)이
    자기 자신과 비교하는 사고를 막는다.
    """
    from agents import mailer, notifier as nt
    sig = state.get("signals") or {}
    if not sig:
        state["log"].append("[notifier] 등급 없음 → 건너뜀")
        return state

    def deliver_and_log(dec, label):
        """send 인 결정은 발송하고, 결과와 함께 로그 1행. 발송 예외는 삼킨다."""
        channel, n, failed = nt.CHANNEL_DRYRUN, None, None
        if dec.send:
            try:
                channel, n, failed, notes = mailer.deliver(dec)
            except Exception as e:      # 발송이 파이프라인을 죽이지 않는다 (설계 §5-4)
                channel, n, failed = nt.CHANNEL_EMAIL, 0, 0
                notes = [f"발송 단계 예외: {type(e).__name__}"]
            for msg in notes:
                state["log"].append(f"[mailer] {msg}")
        nt.append_log(dec, channel=channel, n_recipients=n, n_failed=failed)
        if not dec.send:
            state["log"].append(f"[notifier] {label} 미발송 — {dec.suppressed}")
            return
        subject, _ = nt.render(dec)
        if channel == nt.CHANNEL_DRYRUN:
            state["log"].append(f"[notifier] {label} 드라이런 발송 «{subject}»")
        else:
            state["log"].append(f"[notifier] {label} 발송 «{subject}» — 수신 {n} · 실패 {failed}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sent = nt.read_sent()
    d = nt.decide(state["date"], sig.get("grade", "—"), sig.get("fired") or [],
                  sig.get("n_articles"), sig.get("ci_lo"), sig.get("ci_hi"),
                  today=today, sent=sent, details=sig.get("details"),
                  news_only=not state["statement_path"],
                  has_market=bool(state.get("market")))

    # §2-2 FOMC 회의일 — 신호 메일과 같은 날이면 한 통으로 합친다.
    fm = None
    if state["statement_path"]:
        fm = nt.decide_fed_meeting(state["date"], today, grade=d.grade, sent=sent,
                                   signal_sends=d.send)
        if fm.suppressed == nt.SUP_MERGED:
            d.fed_event = "meeting"

    deliver_and_log(d, f"신호(신뢰도 {d.confidence})")
    if fm:
        deliver_and_log(fm, "FOMC 회의일 알림")

    # §2-3 정정 알림 — 확정판에서 등급이 '실제로' 바뀐 경우만. 그 날짜가 처음
    # 기록되는 중이면(_recorded_grade 가 None) 정정이 아니라 최초 기록이다.
    # §2-2 회의록 알림도 같은 가드를 쓴다 — 속보치 기록이 없는 회의(과거 재처리)에서
    # 회의록 알림이 울리지 않는다.
    if state.get("fed_final"):
        prev = _recorded_grade(state["date"])
        c = prev and nt.decide_correction(state["date"], prev, sig.get("grade"),
                                          today, sent=sent)
        mn = prev and nt.decide_fed_minutes(state["date"], sig.get("grade"), sent=sent,
                                            correction_sends=bool(c and c.send))
        if c and mn and mn.suppressed == nt.SUP_MERGED:
            c.fed_event = "minutes"
        if c:
            deliver_and_log(c, f"정정 {prev} → {sig.get('grade')}")
        if mn:
            deliver_and_log(mn, "FOMC 회의록 알림")
    return state


```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS. 기존 `test_red_alert_logs_a_sent_row` 가 `"드라이런 발송"` 문구와 `n_recipients == "0"` 을 확인하므로 스위치 꺼짐 동작이 그대로인지 여기서 걸린다.

- [ ] **Step 6: 워크플로 — 시크릿·변수 전달**

`.github/workflows/daily-news.yml` 의 job `env:` 에서 `FRED_API_KEY: ${{ secrets.FRED_API_KEY }}` 줄 바로 다음에 추가한다 (들여쓰기 6칸):

```yaml
      # 알림 실제 발송 (docs/superpowers/specs/2026-09-13-alert-delivery-design.md §10).
      # ALERT_SEND 는 Secret 이 아니라 저장소 변수(vars)라 커밋 없이 켜고 끈다.
      # "1" 이 아니면 agents/mailer.py 는 네트워크를 쓰지 않는다(드라이런).
      RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
      ALERT_RECIPIENTS: ${{ secrets.ALERT_RECIPIENTS }}   # 팀 고정 명단, 쉼표 구분
      SUBSCRIBERS_TOKEN: ${{ secrets.SUBSCRIBERS_TOKEN }} # Worker /api/export 인증
      ALERT_SEND: ${{ vars.ALERT_SEND }}
```

Run: `python -c "import yaml,io;yaml.safe_load(io.open('.github/workflows/daily-news.yml',encoding='utf-8'));print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 7: 커밋**

```bash
git add agents/graph.py tests/conftest.py tests/test_notifier_node.py .github/workflows/daily-news.yml
git commit -m "feat(graph): send 판정을 mailer 로 발송하고 결과를 로그에 — 스위치 꺼지면 드라이런 그대로"
```

---

### Task 4: 대시보드 "알림 받기" 섹션

**Files:**
- Create: `dashboard-web/src/lib/subscribe.js`
- Create: `dashboard-web/src/lib/subscribe.test.js`
- Create: `dashboard-web/src/components/SubscribeForm.jsx`
- Modify: `dashboard-web/src/lib/data.js`
- Modify: `dashboard-web/src/pages/Signals.jsx`

**Interfaces:**
- Consumes: Worker `POST https://econpilot.org/api/subscribe` — 본문 `{"email"}`, 응답 200/400/429/502 (기존)
- Produces: `SUBSCRIBE_OPEN` 상수, `messageFor(status)`, `submitSubscribe(email, fetchImpl) -> Promise<{ok, message}>`

- [ ] **Step 1: 실패하는 테스트 작성**

`dashboard-web/src/lib/subscribe.test.js`:

```js
// node --test dashboard-web/src/lib/subscribe.test.js
// dashboard-web/package.json 이 "type": "module" 이라 ESM import 가 그대로 돈다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { SUBSCRIBE_URL, messageFor, submitSubscribe } from "./subscribe.js";

test("messageFor: Worker 응답 코드와 1:1", () => {
  assert.match(messageFor(200), /신청되었습니다/);
  assert.match(messageFor(400), /이메일 주소를 확인/);
  assert.match(messageFor(429), /잠시 후 다시/);
  assert.match(messageFor(502), /메일 발송에 실패/);
  assert.match(messageFor(null), /연결에 실패/);
  assert.match(messageFor(500), /잠시 후 다시/);
});

test("submitSubscribe: 이메일만 JSON 으로 POST 하고 200 이면 ok", async () => {
  const calls = [];
  const fake = async (url, init) => { calls.push({ url, init }); return { status: 200 }; };
  const r = await submitSubscribe("prof@uni.ac.kr", fake);
  assert.equal(r.ok, true);
  assert.equal(calls[0].url, SUBSCRIBE_URL);
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { email: "prof@uni.ac.kr" });
});

test("submitSubscribe: 200 이 아니면 ok 아님", async () => {
  const r = await submitSubscribe("x", async () => ({ status: 400 }));
  assert.equal(r.ok, false);
  assert.match(r.message, /이메일 주소를 확인/);
});

test("submitSubscribe: 네트워크 오류는 연결 실패 문구", async () => {
  const r = await submitSubscribe("x", async () => { throw new TypeError("offline"); });
  assert.deepEqual(r, { ok: false, message: messageFor(null) });
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test dashboard-web/src/lib/subscribe.test.js`
Expected: FAIL — `Cannot find module ... subscribe.js`

- [ ] **Step 3: 순수 모듈 구현**

`dashboard-web/src/lib/subscribe.js`:

```js
// 구독 신청 — econpilot.org Worker 호출과 화면 문구.
// 문구는 Worker 응답 코드와 1:1 로 맞춘다 (docs/superpowers/specs/2026-09-13-alert-delivery-design.md §8).
// 이미 가입된 주소인지는 알리지 않는다 — Worker 가 항상 200 을 준다.
export const SUBSCRIBE_URL = "https://econpilot.org/api/subscribe";

export function messageFor(status) {
  switch (status) {
    case 200: return "신청되었습니다. 환영 메일을 확인해주세요 (스팸함도 확인해주세요).";
    case 400: return "이메일 주소를 확인해주세요.";
    case 429: return "잠시 후 다시 시도해주세요.";
    case 502: return "메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.";
    case null: return "연결에 실패했습니다.";
    default: return "잠시 후 다시 시도해주세요.";
  }
}

export async function submitSubscribe(email, fetchImpl = fetch) {
  try {
    const r = await fetchImpl(SUBSCRIBE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    return { ok: r.status === 200, message: messageFor(r.status) };
  } catch {
    return { ok: false, message: messageFor(null) };
  }
}
```

- [ ] **Step 4: 통과 확인**

Run: `node --test dashboard-web/src/lib/subscribe.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: 폼 스위치 상수**

`dashboard-web/src/lib/data.js` 에서 `const cache = {};` 줄 바로 앞에 추가한다:

```js
// 구독 폼 스위치 — Worker(econpilot.org/api/*) 배포를 확인한 뒤 true 로 바꾼다.
// 사이트는 deploy 브랜치에서 자동 빌드되므로, 배포 전에 폼이 보이면 신청이 전부
// 실패한다 (docs/superpowers/specs/2026-09-13-alert-delivery-design.md §6-2).
export const SUBSCRIBE_OPEN = false;

```

- [ ] **Step 6: 폼 컴포넌트**

`dashboard-web/src/components/SubscribeForm.jsx`:

```jsx
import { useState } from "react";
import { submitSubscribe } from "../lib/subscribe";

// 신호 탭 "알림 받기" — 이메일 하나만 받는다.
// 수집 안내문은 docs/notification_design.md §6-3 요구사항이다. 빼지 않는다.
export default function SubscribeForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);   // { ok, message }

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    const r = await submitSubscribe(email.trim());
    setResult(r);
    if (r.ok) setEmail("");
    setBusy(false);
  }

  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>알림 받기</div>
      <div style={{ fontSize: 13.5, marginBottom: 10 }}>
        경고 신호와 FOMC 일정(연 약 16회)을 이메일로 보내드립니다.
      </div>
      <form onSubmit={onSubmit} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input type="email" required value={email} placeholder="이메일 주소"
          aria-label="이메일 주소" onChange={(e) => setEmail(e.target.value)}
          style={{ flex: "1 1 220px", padding: "8px 10px", font: "inherit",
                   border: "1px solid var(--line)", borderRadius: 4,
                   background: "transparent", color: "inherit" }} />
        <button type="submit" disabled={busy}
          style={{ padding: "8px 16px", font: "inherit", fontWeight: 600,
                   cursor: busy ? "default" : "pointer", borderRadius: 4,
                   border: "1px solid var(--accent)", background: "var(--accent)",
                   color: "#fff", opacity: busy ? 0.6 : 1 }}>
          {busy ? "신청 중…" : "신청"}
        </button>
      </form>
      {result && (
        <div role="status" style={{ marginTop: 8, fontSize: 13.5,
             color: result.ok ? "var(--up)" : "var(--crit)" }}>
          {result.message}
        </div>
      )}
      <div className="cap" style={{ marginTop: 10, lineHeight: 1.7 }}>
        수집하는 정보: 이메일 주소 1개 · 사용 목적: 알림 발송 · 보관 기간: 프로젝트 종료 시 전량 삭제
        <br />
        해지: 모든 메일 하단 링크로 즉시 해지, 해지 시 주소 즉시 삭제
        <br />
        참고용이며 투자조언이 아닙니다.
      </div>
    </div>
  );
}
```

- [ ] **Step 7: 신호 탭에 연결**

`dashboard-web/src/pages/Signals.jsx` 의 앞 세 줄 import 를 바꾼다. 기존:

```jsx
import { useState } from "react";
import { useJson, fmt, gradeInfo, firedNames, stripEmoji } from "../lib/data";
import { Pill } from "../components/ui";
```

다음으로:

```jsx
import { useState } from "react";
import { useJson, fmt, gradeInfo, firedNames, stripEmoji, SUBSCRIBE_OPEN } from "../lib/data";
import { Pill } from "../components/ui";
import SubscribeForm from "../components/SubscribeForm";
```

`</p>` (소개 문단 끝) 과 `<h2 className="sec" style={{ marginTop: 8 }}>네 가지 규칙</h2>` 사이에 한 줄을 넣는다:

```jsx
      {SUBSCRIBE_OPEN && <SubscribeForm />}
```

- [ ] **Step 8: 빌드 확인**

Run: `cd dashboard-web && npm ci && npm run build`
Expected: `vite build` 성공, `dist/` 생성. `dist/` 는 `.gitignore` 대상이므로 커밋하지 않는다.

Run: `node --test dashboard-web/src/lib/subscribe.test.js`
Expected: PASS (4 tests)

- [ ] **Step 9: 커밋**

```bash
git add dashboard-web/src/lib/subscribe.js dashboard-web/src/lib/subscribe.test.js \
        dashboard-web/src/components/SubscribeForm.jsx dashboard-web/src/lib/data.js \
        dashboard-web/src/pages/Signals.jsx
git commit -m "feat(dashboard): 신호 탭 알림 받기 섹션 — 수집 안내문 포함, 스위치 꺼짐"
```

---

## 이 계획이 끝난 뒤 (사람 작업 — 태스크 아님)

1. **main · deploy 양쪽 반영.** 크론은 main 의 워크플로 파일을, 작업은 deploy 를 쓴다
2. **형준** — Worker 시크릿 `RESEND_API_KEY` · `SUBSCRIBERS_TOKEN` 등록 후 `npx wrangler deploy` (`workers/subscribe/README.md`)
3. **형준** — GitHub Secret `ALERT_RECIPIENTS`(처음엔 본인 1명) · `SUBSCRIBERS_TOKEN` 등록, 저장소 변수 `ALERT_SEND` 는 아직 만들지 않음
4. **형준** — Cloudflare 대시보드에서 `econpilot.org/api/subscribe` 요청 제한 규칙
5. **시험 발송** — `ALERT_SEND=1` 로 워크플로 수동 실행, 형준 1명 도착 확인
6. `ALERT_RECIPIENTS` 를 팀 명단으로 교체 → `SUBSCRIBE_OPEN = true` 커밋

5 이후로 메일이 실제로 나간다. 켜기 전에 한 번 더 확인받는다.
