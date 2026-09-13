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
