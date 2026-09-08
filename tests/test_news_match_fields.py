"""관련성 판정 범위(MATCH_FIELDS) — 확장과 되돌리기가 둘 다 되는지.

2026-09: Marketaux 가 주는데 안 보던 snippet·keywords 를 판정 범위에 넣었다.
키워드 세트(F∧M)는 그대로고 **찾는 위치만** 넓혔다. 되돌리기가 쉬워야 한다는 게
착수 조건이었으므로, 그 되돌리기가 실제로 되는지를 여기서 못 박는다.

CSV 스키마 이관(6 → 8컬럼)도 함께 검증한다 — 이게 깨지면 헤더보다 필드가 많은
행이 붙어 DictReader 가 통째로 어긋난다(매일 도는 파이프라인이라 조용히 번진다).
"""
import csv
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import news_scrape as ns


def _reload(monkeypatch, value):
    """NEWS_MATCH_FIELDS 를 바꿔 모듈을 다시 읽는다(상수가 import 시점에 정해지므로)."""
    if value is None:
        monkeypatch.delenv("NEWS_MATCH_FIELDS", raising=False)
    else:
        monkeypatch.setenv("NEWS_MATCH_FIELDS", value)
    return importlib.reload(ns)


# 본문에만 정책 단어가 있는 기사 — 제목·설명만 보면 탈락, snippet 까지 보면 통과
ART = {
    "title": "Bond yields climb after jobs report",
    "description": "Traders reassessed the outlook for the year ahead.",
    "snippet": "The Fed is expected to hold its interest rate steady, analysts said.",
    "keywords": "Federal Reserve,monetary policy",
}


def test_default_is_wide(monkeypatch):
    """기본값은 확장 — snippet·keywords 까지 본다."""
    m = _reload(monkeypatch, None)
    assert m.MATCH_FIELDS == ("title", "description", "snippet", "keywords")
    assert m.relevant_of(ART)


def test_revert_by_env(monkeypatch):
    """환경변수만으로 예전 동작(제목+설명)으로 복귀 — 착수 조건이었던 되돌리기."""
    m = _reload(monkeypatch, "title,description")
    assert m.MATCH_FIELDS == ("title", "description")
    assert not m.relevant_of(ART)          # 예전 규칙에서는 탈락하던 기사


def test_conservative_snippet_only(monkeypatch):
    """중간 단계(snippet 만)도 선택 가능해야 한다."""
    m = _reload(monkeypatch, "title,description,snippet")
    assert m.relevant_of(ART)              # snippet 에 Fed + interest rate
    only_kw = dict(ART, snippet="")        # 근거가 keywords 에만 있으면
    assert not m.relevant_of(only_kw)      # 이 설정에서는 탈락


def test_two_arg_calls_unchanged(monkeypatch):
    """snippet·keywords 를 안 넘기면 예전과 똑같이 동작(하위호환).

    WSJ 백본(analysis/scope_impact.py)처럼 그 필드가 없는 자료에 그대로 쓴다.
    """
    m = _reload(monkeypatch, None)         # 확장 설정이어도
    assert m.is_relevant("Fed raises the fed funds rate", "")
    assert not m.is_relevant("Bond yields climb", "Traders reassessed the outlook")


def test_keyword_set_untouched(monkeypatch):
    """지도교수 지정 키워드는 건드리지 않았다 — F∧M 둘 다 요구."""
    m = _reload(monkeypatch, None)
    assert not m.relevant_of({"title": "ECB cuts interest rates"})       # M만, F 없음
    assert not m.relevant_of({"title": "The Federal Reserve issued a statement"})  # F만
    assert m.relevant_of({"title": "Fed debates monetary policy"})       # 둘 다


def test_schema_migration_adds_columns(tmp_path, monkeypatch):
    """구 6컬럼 CSV → 8컬럼 이관. 기존 행은 보존되고 빈값으로 채워진다."""
    m = _reload(monkeypatch, None)
    p = tmp_path / "fed_news.csv"
    old = ["date", "title", "description", "source", "url", "published_at"]
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(old)
        w.writerow(["2026-09-01", "T", "D", "s.com", "u1", "2026-09-01T00:00Z"])
    m._ensure_columns(p)

    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == m.COLUMNS
    assert rows[0]["title"] == "T"          # 구 데이터 보존
    assert rows[0]["snippet"] == ""         # 새 컬럼은 빈값
    assert len(rows) == 1

    m._ensure_columns(p)                    # 멱등 — 두 번 돌려도 그대로
    with open(p, encoding="utf-8-sig", newline="") as f:
        assert list(csv.DictReader(f))[0]["title"] == "T"


def test_migration_then_append_stays_aligned(tmp_path, monkeypatch):
    """이관 후 새 행을 붙여도 헤더와 어긋나지 않는다 — 실제 사고 지점."""
    m = _reload(monkeypatch, None)
    p = tmp_path / "fed_news.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "title", "description", "source", "url", "published_at"])
        w.writerow(["2026-09-01", "old", "D", "s.com", "u1", "2026-09-01T00:00Z"])
    m._ensure_columns(p)
    with open(p, "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(m._row({
            "date": "2026-09-02", "title": "new", "description": "D2",
            "source": "s.com", "url": "u2", "published_at": "2026-09-02T00:00Z",
            "snippet": "S2", "keywords": "K2"}))

    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["title"] for r in rows] == ["old", "new"]
    assert rows[1]["snippet"] == "S2" and rows[1]["keywords"] == "K2"
    assert rows[1]["url"] == "u2"           # 컬럼이 밀리지 않았다
    assert all(None not in r for r in rows)  # 헤더보다 긴 행 없음


def test_row_tolerates_missing_keys(monkeypatch):
    """구 코드가 만든 dict(snippet 없음)도 저장 가능해야 한다."""
    m = _reload(monkeypatch, None)
    row = m._row({"date": "d", "title": "t", "description": "x",
                  "source": "s", "url": "u", "published_at": "p"})
    assert len(row) == len(m.COLUMNS)
    assert row[-1] == "" and row[-2] == ""


def test_log_rejected_honors_patched_module_global(tmp_path, monkeypatch):
    """_log_rejected 가 모듈 전역 REJECTED 를 호출 시점에 본다.

    ★회귀 방지: 기본 인자를 out=REJECTED 로 두면 정의 시점 값이 굳어, 테스트가
      경로를 바꿔도 진짜 data/news/rejected_news.csv 에 쓴다. 2026-09 검증 중
      실기사 276행이 실제로 그렇게 들어갔다. append_rows 는 같은 이유로 이미
      None 을 쓰고 있었는데 이 함수만 남아 있었다.
    """
    m = _reload(monkeypatch, None)
    fake = tmp_path / "rej.csv"
    monkeypatch.setattr(m, "REJECTED", fake)
    raw = [{"date": "2026-09-05", "title": "Lakers win", "description": "NBA",
            "source": "s.com", "url": "u1", "published_at": "2026-09-05T00:00Z",
            "snippet": "", "keywords": ""}]
    n = m._log_rejected(raw, kept=[])
    assert n == 1
    assert fake.exists(), "패치한 경로에 쓰지 않았다 — 기본 인자가 굳은 것"
    rows = list(csv.DictReader(open(fake, encoding="utf-8-sig", newline="")))
    assert rows[0]["url"] == "u1"
    assert list(rows[0]) == m.COLUMNS


def teardown_module(module):
    """다른 테스트가 영향을 안 받게 기본 상태로 되돌린다."""
    import os
    os.environ.pop("NEWS_MATCH_FIELDS", None)
    importlib.reload(ns)
