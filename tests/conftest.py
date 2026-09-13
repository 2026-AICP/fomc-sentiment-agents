"""모든 테스트에서 운영 산출물 경로를 임시 폴더로 격리한다.

agents/graph.py 는 운영 파일 경로를 모듈 상수로 박아두고 있어, 노드를 직접 부르는
테스트가 그 상수를 갈아끼우는 걸 잊으면 **진짜 파일에 쓴다.** 실제로 세 테스트가
그랬다(2026-09-13 확인):

  test_daily_smoke     → outputs/daily_signals.csv · notification_log.csv ·
                         vintage_meetings.csv
  test_daily_prepost   → data/fomc.db
  test_daily_presser   → data/fomc.db

넷 다 deploy 브랜치에서 봇이 강제 커밋하는 운영 파일이다. daily_signals.csv 는
속보치를 절대 고치지 않는 기록(조교 질문 6)이고, notification_log.csv 는 발송
빈도의 유일한 외부 증거다. main 에서는 대부분 gitignore 라 git status 에 뜨지 않아
오염이 가려져 있었다 — 테스트마다 기억하게 두지 않고 여기서 일괄로 막는다.

경로를 인자로 직접 넘기는 테스트(append_log(path=...) 등)는 영향이 없다.
테스트가 자기 경로를 다시 monkeypatch 하면 그쪽이 이긴다.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_production_outputs(monkeypatch, tmp_path):
    from agents import graph, notifier
    from analysis import vintage

    monkeypatch.setattr(graph, "DB", tmp_path / "fomc.db")
    monkeypatch.setattr(graph, "DAILY_SIGNALS", tmp_path / "daily_signals.csv")
    monkeypatch.setattr(notifier, "NOTIFICATION_LOG", tmp_path / "notification_log.csv")
    monkeypatch.setattr(vintage, "MEETING_VINTAGE", tmp_path / "vintage_meetings.csv")
    # 개발자 셸에 ALERT_SEND=1 이 켜져 있어도 테스트는 절대 실제 메일을 보내지 않는다.
    monkeypatch.delenv("ALERT_SEND", raising=False)
