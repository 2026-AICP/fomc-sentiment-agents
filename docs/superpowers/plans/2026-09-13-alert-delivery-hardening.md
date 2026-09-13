# 알림 발송 보강 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 발송을 켜기 전에 최종 리뷰 Important 3건을 막는다 — 전원 실패를 "보냄"으로 남기지 않고, 로그 push 실패로 인한 중복 발송을 막고, 판정을 건너뛰는 시험 발송 경로를 만든다.

**Architecture:** ① `graph.notifier_node` 의 `deliver_and_log` 가 한 명도 못 받은 결정에 `send_failed` 사유를 붙인다(`read_sent` 가 세지 않으므로 재판정). ② `mailer.deliver` 가 요청마다 해시 기반 `Idempotency-Key` 를 보내고 `subject_prefix` 를 받는다. 시험 발송 스크립트·워크플로가 그걸 쓴다. ③ `daily-news.yml` 의 deploy push 를 rebase 후 3회 재시도로 바꾼다.

**Tech Stack:** Python 3.11+ · pytest · requests · Resend HTTP API · GitHub Actions

**Spec:** `docs/superpowers/specs/2026-09-13-alert-delivery-design.md` (§5-4, §5-5, §10-1, §11-9~11)

## Global Constraints

- 받는 사람 주소를 로그·notes·print·커밋 어디에도 넣지 않는다. 리포가 PUBLIC 이다.
- `agents/notifier.py` 는 발송 모듈(`smtplib`·`resend`·`requests`·`sendgrid`·`urllib`)을 import 하지 않는다.
- `ALERT_SEND` 가 `"1"` 이 아니면 파이프라인은 네트워크 호출 0건, 로그는 지금과 동일.
- 사유 코드 문자열: `send_failed`
- 시험 발송 제목 접두어: `[시험] `
- 시험 발송은 구독자에게 가지 않는다(`SUBSCRIBERS_TOKEN` 제거), 알림 로그에 쓰지 않는다.
- 테스트 명령: `python -m pytest tests/ -q` (Windows 에서는 `PYTHONIOENCODING=utf-8`)
- 커밋 메시지는 한국어, 끝에:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016WPyrTBW2aq3RPSob5jUE1
  ```

---

### Task 1: 한 명도 못 받은 알림은 `send_failed`

**Files:**
- Modify: `agents/notifier.py` (사유 코드 상수, `read_sent` 독스트링)
- Modify: `agents/graph.py` (`notifier_node` 안의 `deliver_and_log`)
- Test: `tests/test_notifier.py`, `tests/test_notifier_node.py`

**Interfaces:**
- Consumes: `mailer.deliver(dec) -> (channel, n_recipients, n_failed, notes)` (기존)
- Produces: `notifier.SUP_SEND_FAILED = "send_failed"`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_notifier.py` import 블록에서 `SUP_MERGED,` 다음 줄에 `SUP_SEND_FAILED,` 를 넣고, 파일 끝에 추가:

```python
def test_read_sent_skips_send_failed(tmp_path):
    """한 명도 못 받은 알림은 '보냄'이 아니다 — 다음 실행에서 다시 판정된다(설계 §5-4)."""
    p = tmp_path / "notification_log.csv"
    d = decide(TODAY, GRADE_ALERT, ["divergence"], **OK)
    d.suppressed = SUP_SEND_FAILED
    append_log(d, path=p, channel=CHANNEL_EMAIL, n_recipients=2, n_failed=2)
    assert SUP_SEND_FAILED == "send_failed"
    assert read_sent(p) == set()
```

`tests/test_notifier_node.py` 에서:

기존 `test_sent_decision_logs_email_channel_and_counts` 의 `assert row["n_recipients"] == "3" and row["n_failed"] == "1"` 줄 다음에 추가 (일부 실패는 여전히 보냄):

```python
    assert row["suppressed_reason"] == ""            # 일부 실패는 '보냄' — 재시도 없음
```

기존 `test_delivery_exception_does_not_crash_node` 의 `assert _rows(p)[0]["channel"] == "email"` 줄 다음에 추가:

```python
    assert _rows(p)[0]["suppressed_reason"] == nt.SUP_SEND_FAILED
```

파일 끝에 추가:

```python
def test_total_failure_is_send_failed_and_retried_on_rerun(tmp_path, monkeypatch):
    """전원 실패면 send_failed — 같은 날 재실행에서 다시 보낸다(설계 §5-4)."""
    p = _today(monkeypatch, tmp_path, "2026-08-20")
    calls = []

    def all_fail(d):
        calls.append(d.kind)
        return ("email", 2, 2, ["발송 실패 2/2"])
    monkeypatch.setattr(mailer, "deliver", all_fail)
    st = _state("2026-08-20", GRADE_ALERT, ["divergence"])
    out = graph.notifier_node(st)
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_notifier.py tests/test_notifier_node.py -q`
Expected: FAIL — `ImportError: cannot import name 'SUP_SEND_FAILED'`

- [ ] **Step 3: notifier 구현**

`agents/notifier.py` 의 `SUP_MERGED = ...` 줄 바로 다음에 추가:

```python
SUP_SEND_FAILED = "send_failed"          # 발송 시도했으나 한 명도 못 받음 — 다음 실행에서 재판정
```

`read_sent` 독스트링의 마지막 단락(`채널로는 거르지 않는다. ...`) 다음, 닫는 `"""` 앞에 추가:

```python
    send_failed(한 명도 못 받은 발송)도 사유가 있는 행이라 세지 않는다 — 받은 사람이
    없으니 다시 보내도 두 통이 가지 않는다(설계 §5-4). 일부만 실패한 행은 사유가
    비어 있어 '보냄'으로 센다.
```

- [ ] **Step 4: graph 구현**

`agents/graph.py` 의 `def deliver_and_log(dec, label):` 부터 그 함수 끝(`state["log"].append(f"[notifier] {label} 발송 «{subject}» — 수신 {n} · 실패 {failed}")` 줄)까지를 다음으로 바꾼다:

```python
    def deliver_and_log(dec, label):
        """send 인 결정은 발송하고, 결과와 함께 로그 1행. 발송 예외는 삼킨다.

        한 명도 받지 못했으면(수신자 0명 · 전원 실패 · 발송 단계 예외) send_failed 로
        남긴다. read_sent 가 사유 있는 행을 세지 않으므로 다음 실행에서 다시 판정된다 —
        받은 사람이 없으니 두 통이 갈 일도 없다(설계 §5-4). 일부만 실패하면 '보냄'이다.
        """
        channel, n, failed = nt.CHANNEL_DRYRUN, None, None
        if dec.send:
            try:
                channel, n, failed, notes = mailer.deliver(dec)
            except Exception as e:      # 발송이 파이프라인을 죽이지 않는다 (설계 §5-4)
                channel, n, failed = nt.CHANNEL_EMAIL, 0, 0
                notes = [f"발송 단계 예외: {type(e).__name__}"]
            for msg in notes:
                state["log"].append(f"[mailer] {msg}")
            if channel == nt.CHANNEL_EMAIL and (n == 0 or failed == n):
                dec.suppressed = nt.SUP_SEND_FAILED
        nt.append_log(dec, channel=channel, n_recipients=n, n_failed=failed)
        if dec.suppressed == nt.SUP_SEND_FAILED:
            state["log"].append(f"[notifier] {label} 발송 실패 — 받은 사람 없음 "
                                f"(수신 {n} · 실패 {failed}), 다음 실행에서 재시도")
            return
        if not dec.send:
            state["log"].append(f"[notifier] {label} 미발송 — {dec.suppressed}")
            return
        subject, _ = nt.render(dec)
        if channel == nt.CHANNEL_DRYRUN:
            state["log"].append(f"[notifier] {label} 드라이런 발송 «{subject}»")
        else:
            state["log"].append(f"[notifier] {label} 발송 «{subject}» — 수신 {n} · 실패 {failed}")
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add agents/notifier.py agents/graph.py tests/test_notifier.py tests/test_notifier_node.py
git commit -m "fix(notifier): 한 명도 못 받은 알림은 send_failed 로 남겨 다음 실행에서 재판정"
```

---

### Task 2: 중복 방지 키 · 시험 발송 경로

**Files:**
- Modify: `agents/mailer.py`
- Create: `scripts/send_test_alert.py`
- Create: `.github/workflows/test-alert.yml`
- Test: `tests/test_mailer.py`, `tests/test_send_test_alert.py` (신규)

**Interfaces:**
- Consumes: `notifier.decide(...)`, `notifier.render(d, footer=)` (기존)
- Produces: `mailer.deliver(decision, env=None, get=..., post=..., sleep=..., subject_prefix="")` — 반환 형식 동일

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_mailer.py` 파일 끝에 추가:

```python
def _keyed():
    seen = []

    def post(url, json=None, headers=None, timeout=None):
        seen.append({"to": json["to"][0], "subject": json["subject"],
                     "key": headers["Idempotency-Key"]})
        return Resp(200)
    return seen, post


def test_idempotency_key_stable_per_mail_and_recipient():
    """같은 알림을 같은 사람에게 다시 요청하면 같은 키 → Resend 가 24시간 안 중복을 막는다."""
    seen, post = _keyed()
    for _ in range(2):
        mailer.deliver(_alert(), env=ON, post=post, sleep=lambda s: None, get=_export())
    assert [s["key"] for s in seen[:2]] == [s["key"] for s in seen[2:]]
    assert seen[0]["key"] != seen[1]["key"]              # 수신자마다 다른 키
    assert all("@" not in s["key"] for s in seen)        # 키에 주소가 드러나지 않는다


def test_subject_prefix_changes_subject_and_key():
    """시험 발송이 같은 날 실제 알림의 중복 방지 키를 선점하면 안 된다."""
    seen, post = _keyed()
    env = dict(ON, ALERT_RECIPIENTS="a@team.org")
    mailer.deliver(_alert(), env=env, post=post, sleep=lambda s: None, get=_export())
    mailer.deliver(_alert(), env=env, post=post, sleep=lambda s: None, get=_export(),
                   subject_prefix="[시험] ")
    assert seen[1]["subject"] == "[시험] " + seen[0]["subject"]
    assert seen[0]["key"] != seen[1]["key"]
```

`tests/test_send_test_alert.py` 신규:

```python
"""시험 발송 스크립트 — 구독자에게 가지 않고, 알림 로그에 쓰지 않는다(설계 §10-1).

scripts/ 는 패키지가 아니라 경로로 불러온다.
"""
import importlib.util
from pathlib import Path

from agents import notifier as nt
from analysis.signals import GRADE_ALERT

_path = Path(__file__).resolve().parents[1] / "scripts" / "send_test_alert.py"
_spec = importlib.util.spec_from_file_location("send_test_alert", _path)
sta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sta)


def test_env_drops_subscribers_and_forces_send():
    env = sta.build_env({"SUBSCRIBERS_TOKEN": "t", "ALERT_SEND": "", "RESEND_API_KEY": "k"})
    assert "SUBSCRIBERS_TOKEN" not in env
    assert env["ALERT_SEND"] == "1" and env["RESEND_API_KEY"] == "k"


def test_decision_is_a_sendable_alert():
    d = sta.build_decision("2026-09-14")
    assert d.send and d.grade == GRADE_ALERT and d.date == "2026-09-14"


def test_main_passes_prefix_and_writes_no_log():
    got = {}

    def fake(d, env=None, subject_prefix=""):
        got.update(env=env, prefix=subject_prefix)
        return ("email", 1, 0, [])
    assert sta.main({"SUBSCRIBERS_TOKEN": "t"}, deliver=fake) == 0
    assert got["prefix"] == "[시험] " and "SUBSCRIBERS_TOKEN" not in got["env"]
    assert not nt.NOTIFICATION_LOG.exists()        # conftest 가 tmp 경로로 돌려둔 로그


def test_main_fails_unless_everyone_received():
    assert sta.main({}, deliver=lambda d, env=None, subject_prefix="": ("email", 0, 0, [])) == 1
    assert sta.main({}, deliver=lambda d, env=None, subject_prefix="": ("email", 2, 1, [])) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_mailer.py tests/test_send_test_alert.py -q`
Expected: FAIL — `KeyError: 'Idempotency-Key'` 와 `FileNotFoundError` (스크립트 없음)

- [ ] **Step 3: mailer 구현**

`agents/mailer.py`:

import 줄 `import os` 앞에 `import hashlib` 을 추가한다.

`_payload` 를 다음으로 바꾼다:

```python
def _payload(recipient, decision, subject_prefix=""):
    if recipient["team"]:
        footer, headers = TEAM_FOOTER, {}
    else:
        url = UNSUB_BASE + (recipient["unsub_token"] or "")
        footer = f"수신거부: {url}"
        headers = {"List-Unsubscribe": f"<{url}>",
                   "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    subject, body = nt.render(decision, footer=footer)
    payload = {"from": FROM, "to": [recipient["email"]],
               "subject": subject_prefix + subject, "text": body}
    if headers:
        payload["headers"] = headers
    return payload


def _idempotency_key(recipient, decision, subject_prefix=""):
    """Resend 중복 방지 키 (설계 §5-5). 같은 알림·같은 사람이면 같은 키.

    해시라 주소가 드러나지 않는다. 접두어가 들어가므로 시험 발송이 같은 날 실제
    알림의 키를 선점하지 않는다. Resend 는 24시간 동안 키를 기억한다.
    """
    raw = "|".join([subject_prefix, decision.kind, decision.date, recipient["email"]])
    return "econpilot-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
```

`deliver` 시그니처를 바꾼다:

```python
def deliver(decision, env=None, get=requests.get, post=requests.post, sleep=time.sleep,
            subject_prefix=""):
```

독스트링 끝(닫는 `"""` 앞)에 한 줄 추가:

```python
    subject_prefix 는 시험 발송(scripts/send_test_alert.py)용 제목 접두어다.
```

발송 루프의 `post(...)` 호출을 다음으로 바꾼다:

```python
            r = post(RESEND_URL, json=_payload(rcp, decision, subject_prefix),
                     headers={"Authorization": f"Bearer {key}",
                              "Idempotency-Key": _idempotency_key(rcp, decision, subject_prefix)},
                     timeout=TIMEOUT)
```

- [ ] **Step 4: 시험 발송 스크립트**

`scripts/send_test_alert.py`:

```python
"""시험 발송 — 가짜 🔴 알림 한 통을 팀 고정 명단에게만 보낸다.

실제 파이프라인으로는 시험이 안 된다. 그날 등급이 경고가 아니면 판정이 send 가
아니고, 경고 날이면 크론이 이미 드라이런 행을 남겨 already_sent 로 막힌다. 그래서
판정을 건너뛰고 mailer.deliver 를 직접 부른다.

  · 구독자에게는 가지 않는다 — SUBSCRIBERS_TOKEN 을 env 에서 지운다
  · outputs/notification_log.csv 에 쓰지 않는다 — 발송 빈도 기록을 오염시키지 않는다
  · 제목 앞에 [시험] 이 붙고, Resend 중복 방지 키도 실제 알림과 다르다
  · ALERT_SEND 스위치와 무관하게 보낸다 — 이 스크립트를 실행하는 것 자체가 의사표시다
  · 한 명이라도 실패하거나 받은 사람이 없으면 종료 코드 1

실행: Actions → Test alert email → Run workflow (.github/workflows/test-alert.yml)
설계: docs/superpowers/specs/2026-09-13-alert-delivery-design.md §10-1
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import mailer, notifier as nt  # noqa: E402
from analysis.signals import GRADE_ALERT  # noqa: E402

SUBJECT_PREFIX = "[시험] "


def build_env(environ):
    env = dict(environ)
    env["ALERT_SEND"] = "1"
    env.pop("SUBSCRIBERS_TOKEN", None)
    return env


def build_decision(today):
    return nt.decide(today, GRADE_ALERT, ["divergence"], n_articles=40,
                     ci_lo=-0.10, ci_hi=0.20, today=today,
                     details=["시험 발송입니다 — 실제 신호가 아닙니다."])


def main(environ=None, deliver=None):
    environ = os.environ if environ is None else environ
    deliver = mailer.deliver if deliver is None else deliver
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    channel, n, failed, notes = deliver(build_decision(today), env=build_env(environ),
                                        subject_prefix=SUBJECT_PREFIX)
    for msg in notes:
        print(f"[mailer] {msg}")
    print(f"시험 발송 — 수신 {n} · 실패 {failed}")
    return 0 if n > 0 and failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 시험 발송 워크플로**

`.github/workflows/test-alert.yml`:

```yaml
name: Test alert email

# 알림 실제 발송 시험 — 가짜 🔴 알림 한 통을 팀 고정 명단(ALERT_RECIPIENTS)에게만 보낸다.
# 구독자에게는 가지 않고(SUBSCRIBERS_TOKEN 을 넘기지 않는다), 알림 로그에도 쓰지 않는다.
# 한 명이라도 실패하면 잡이 실패로 끝난다.
# 설계: docs/superpowers/specs/2026-09-13-alert-delivery-design.md §10-1
on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      # agents/notifier.py · analysis/signals.py 는 표준 라이브러리만 쓴다. 발송에 requests 만 필요.
      - name: Install dependencies
        run: pip install requests

      - name: Send test alert
        env:
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          ALERT_RECIPIENTS: ${{ secrets.ALERT_RECIPIENTS }}
        run: python scripts/send_test_alert.py
```

Run: `python -c "import yaml,io;yaml.safe_load(io.open('.github/workflows/test-alert.yml',encoding='utf-8'));print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 6: 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add agents/mailer.py scripts/send_test_alert.py .github/workflows/test-alert.yml tests/test_mailer.py tests/test_send_test_alert.py
git commit -m "feat(mailer): Resend 중복 방지 키 · 팀 전용 시험 발송 워크플로"
```

---

### Task 3: deploy push 재시도

**Files:**
- Modify: `.github/workflows/daily-news.yml` ("Commit refreshed daily outputs" 단계)

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (워크플로 동작만)

- [ ] **Step 1: push 줄 교체**

`.github/workflows/daily-news.yml` 에서 다음 한 줄(들여쓰기 12칸):

```
            git push origin HEAD:deploy/streamlit-dashboard
```

을 다음으로 바꾼다 (들여쓰기 12칸 유지):

```
            # 알림 메일은 이미 나갔다. 여기서 push 가 실패하면 notification_log.csv 와
            # fomc.db 가 러너와 함께 사라져, 다음 실행이 같은 회의록·정정 메일을 또
            # 보낸다(설계 §5-5). 실행 중 누가 deploy 에 푸시한 경우가 흔한 원인이라
            # 최신 deploy 위로 rebase 해 최대 3번 시도한다. rebase 충돌은 사람이 봐야
            # 하므로 멈추고 잡을 실패로 표시한다.
            for i in 1 2 3; do
              if git push origin HEAD:deploy/streamlit-dashboard; then
                break
              fi
              if [ "$i" = 3 ]; then
                echo "::error::deploy push 3회 실패 — 알림 로그가 저장되지 않았다. 다음 실행 전에 확인할 것"
                exit 1
              fi
              if ! git pull --rebase origin deploy/streamlit-dashboard; then
                git rebase --abort || true
                echo "::error::deploy rebase 충돌 — 알림 로그가 저장되지 않았다. 다음 실행 전에 확인할 것"
                exit 1
              fi
              sleep 5
            done
```

- [ ] **Step 2: 검증**

Run: `python -c "import yaml,io;yaml.safe_load(io.open('.github/workflows/daily-news.yml',encoding='utf-8'));print('YAML OK')"`
Expected: `YAML OK`

push 단계 셸만 뽑아 문법 확인:

Run: `python -c "import yaml,io;s=[x for x in yaml.safe_load(io.open('.github/workflows/daily-news.yml',encoding='utf-8'))['jobs']['news']['steps'] if x.get('name')=='Commit refreshed daily outputs'][0]['run'];io.open('_push_step.sh','w',encoding='utf-8').write(s)" && bash -n _push_step.sh && echo "SH OK" && rm _push_step.sh`
Expected: `SH OK`

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/daily-news.yml
git commit -m "fix(ci): deploy push 실패 시 rebase 후 3회 재시도 — 로그 유실로 인한 중복 발송 방지"
```
