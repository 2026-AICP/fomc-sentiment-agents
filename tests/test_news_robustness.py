"""뉴스 수집 견고화 검증 — 페이지 오류에도 전멸하지 않고 계속 수집(CI 안정성).

두 번에 걸쳐 고친 자리다. 셋을 구분해서 처리하는지를 고정한다.
  ① 예전: 한 페이지에서 예외가 나면 그대로 전파 → collect 전체 실패, 그 회차 0건 저장.
     → 재시도 + 부분보존으로 수정.
  ② 2026-08: 그 부분보존이 '거기서 전체 중단'이라, 80쪽으로 늘린 뒤 64쪽 ReadTimeout
     한 번에 남은 17쪽(51건)을 통째로 버렸다(240 요청 → 189 수신).
     → 실패한 페이지만 건너뛰고 계속 가도록 수정.
  ③ 단, 진짜로 API 가 죽었으면(쿼터 소진·장애) 남은 요청을 낭비하면 안 된다.
     → 연속 MAX_FAIL_STREAK 쪽 실패면 중단.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine.news_scrape as ns


def _art(page):
    return {"url": f"u{page}", "title": "Fed rate decision news", "description": "x" * 30,
            "date": "2026-01-01", "source": "s.com", "published_at": ""}


def _no_sleep(monkeypatch):
    monkeypatch.setattr(ns, "_api_key", lambda: "k")
    monkeypatch.setattr(ns.time, "sleep", lambda *a, **k: None)


def test_skips_failed_page_and_keeps_going(monkeypatch):
    """한 페이지가 계속 실패해도 그 페이지만 포기하고 나머지는 끝까지 받는다.

    예전엔 여기서 전체를 중단해 뒷 페이지를 통째로 버렸다(실측 51건 손실)."""
    _no_sleep(monkeypatch)

    def fake(key, fd, page):
        if page == 3:
            raise RuntimeError("네트워크 오류: ReadTimeout")
        return [_art(page)], 500

    monkeypatch.setattr(ns, "_one_page", fake)
    arts, found = ns.discover_news(days_back=3, pages=10, retries=1)
    assert [a["url"] for a in arts] == ["u1", "u2", "u4", "u5", "u6",
                                        "u7", "u8", "u9", "u10"]   # 3쪽만 빠짐
    assert found == 500


def test_aborts_after_consecutive_failures(monkeypatch):
    """연속으로 무너지면 API 이상으로 보고 중단 — 남은 요청(쿼터)을 낭비하지 않는다."""
    _no_sleep(monkeypatch)
    calls = []

    def fake(key, fd, page):
        calls.append(page)
        if page >= 3:                                  # 3쪽부터 전부 실패
            raise RuntimeError("Marketaux 실패 (HTTP 429): rate_limit")
        return [_art(page)], 500

    monkeypatch.setattr(ns, "_one_page", fake)
    arts, _ = ns.discover_news(days_back=3, pages=40, retries=1)
    assert [a["url"] for a in arts] == ["u1", "u2"]     # 받은 건 보존
    # 3·4·5 쪽에서 연속 3회 실패 → 중단. 40쪽까지 계속 두드리지 않는다.
    assert max(calls) == 2 + ns.MAX_FAIL_STREAK


def test_isolated_failures_do_not_trigger_abort(monkeypatch):
    """띄엄띄엄 실패는 '연속'이 아니므로 중단 사유가 아니다 — 간헐적 타임아웃 대응."""
    _no_sleep(monkeypatch)

    def fake(key, fd, page):
        if page in (2, 5, 8):                          # 연속이 아닌 3회 실패
            raise RuntimeError("네트워크 오류: ReadTimeout")
        return [_art(page)], 500

    monkeypatch.setattr(ns, "_one_page", fake)
    arts, _ = ns.discover_news(days_back=3, pages=10, retries=1)
    assert [a["url"] for a in arts] == ["u1", "u3", "u4", "u6", "u7", "u9", "u10"]


def test_retry_recovers_transient_error(monkeypatch):
    """page 2가 첫 시도 실패 후 재시도에서 성공 → 손실 없음."""
    _no_sleep(monkeypatch)
    state = {"failed": False}

    def fake(key, fd, page):
        if page == 2 and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("네트워크 오류: Timeout")
        if page > 3:
            return [], 500
        return [_art(page)], 500

    monkeypatch.setattr(ns, "_one_page", fake)
    arts, _ = ns.discover_news(days_back=3, pages=10, retries=2)
    assert [a["url"] for a in arts] == ["u1", "u2", "u3"]   # 재시도로 u2 복구


def test_stops_cleanly_on_empty_page(monkeypatch):
    """빈 페이지(결과 소진)에서 정상 종료 — 오류 아님."""
    _no_sleep(monkeypatch)

    def fake(key, fd, page):
        return ([_art(page)], 500) if page <= 3 else ([], 500)

    monkeypatch.setattr(ns, "_one_page", fake)
    arts, _ = ns.discover_news(days_back=3, pages=10)
    assert len(arts) == 3


def test_collect_warns_on_zero(monkeypatch, tmp_path, capsys):
    """수집 0건이면 경고 출력(CI에서 문제 가시화)."""
    _no_sleep(monkeypatch)
    monkeypatch.setattr(ns, "discover_news", lambda *a, **k: ([], 0))
    ns.collect(out=tmp_path / "fed_news.csv")
    assert "수집 0건" in capsys.readouterr().out
