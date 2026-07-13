"""뉴스 수집 견고화 검증 — 페이지 오류에도 전멸하지 않고 부분수집 보존(CI 안정성).

문제였던 것: discover_news 가 한 페이지에서 예외가 나면 그대로 전파 → collect 전체 실패
→ 그 회차 0건 저장(라이브가 4건/일이던 유력 원인). 이제 재시도 + 부분보존.
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


def test_partial_save_on_persistent_page_error(monkeypatch):
    """page 3이 계속 실패해도 예외 전파 없이 page 1~2 보존."""
    _no_sleep(monkeypatch)

    def fake(key, fd, page):
        if page == 3:
            raise RuntimeError("Marketaux 실패 (HTTP 429): rate_limit")
        return [_art(page)], 500

    monkeypatch.setattr(ns, "_one_page", fake)
    arts, found = ns.discover_news(days_back=3, pages=10, retries=1)
    assert [a["url"] for a in arts] == ["u1", "u2"]   # 부분 보존(전멸 아님), 예외 없이 반환
    assert found == 500


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
