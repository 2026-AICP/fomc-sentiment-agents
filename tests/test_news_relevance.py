"""2a 키워드 확장 — is_relevant 관련성 필터 검증.

넓힌 쿼리로 들어온 기사 중, 점수화 대상(제목+설명)이 실제 Fed·통화정책·핵심거시
주제인 것만 남기고 곁가지(스포츠·연예 등)는 버린다. collect() 통합도 확인.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.news_scrape import is_relevant

DESC = "a description clearly longer than twenty characters here"


def test_keeps_fed_monetary_articles():
    assert is_relevant("Fed holds interest rates steady", "Powell signals patience")
    assert is_relevant("FOMC minutes reveal a hawkish tilt", "")
    assert is_relevant("Traders eye a rate cut in September", "")
    assert is_relevant("Inflation cools to 2.5% in latest CPI report", "")
    assert is_relevant("Central bank weighs a 25 basis points move", "")
    assert is_relevant("Powell testifies before Congress", "dovish remarks on the economy")


def test_drops_offtopic_articles():
    assert not is_relevant("Lakers beat Celtics in overtime thriller", "NBA finals recap")
    assert not is_relevant("New iPhone launches next week", "Apple unveils camera upgrades")
    assert not is_relevant("Hurricane approaches the Florida coast", "storm warning issued")


def test_fed_word_boundary_no_false_positive():
    """'FedEx' 같은 건 'fed' 앵커로 오인하지 않는다(단어경계)."""
    assert not is_relevant("FedEx raises shipping fees", "package delivery update")


def test_cpi_pce_word_boundary():
    """cpi·pce 는 단어로만 매칭(임의 문자열 속 포함 아님)."""
    assert is_relevant("Latest CPI print surprises markets", "")
    assert not is_relevant("Recipe for spicy noodles", "")   # 'cpi'/'pce' 부분문자열 아님


def test_collect_filters_irrelevant(tmp_path, monkeypatch):
    """collect() 가 관련 기사만 저장하고 곁가지는 드롭한다."""
    import engine.news_scrape as ns
    raw = [
        {"date": "2026-06-17", "title": "Fed signals a rate cut", "description": DESC,
         "source": "reuters.com", "url": "r1", "published_at": "2026-06-17T18:00:00Z"},
        {"date": "2026-06-17", "title": "Lakers win game 7", "description": "NBA recap " + DESC,
         "source": "espn.com", "url": "e1", "published_at": "2026-06-17T19:00:00Z"},
    ]
    monkeypatch.setattr(ns, "discover_news", lambda *a, **k: (raw, 2))
    got, new, found = ns.collect(out=tmp_path / "fed_news.csv")
    assert {a["url"] for a in got} == {"r1"}          # Fed 기사만, 스포츠 드롭
    # 저장된 CSV 에도 관련 기사만
    with open(tmp_path / "fed_news.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert {r["url"] for r in rows} == {"r1"}
