"""뉴스 선정 규칙 — 지도교수 키워드 세트(F그룹 AND M그룹) 검증.

규칙(2026-07): 제목+설명에 **F그룹 1개 이상 AND M그룹 1개 이상**이 있어야 채택.
  F(2)  federal reserve, fed
  M(27) 정책·도구 9 + 의장 성 6 + 국내외 중앙은행/직위 12
data/wsj (2000~2021) 수집에 쓴 세트와 동일 → 과거 검증분과 라이브가 같은 기준.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.news_scrape import is_relevant

DESC = "a description clearly longer than twenty characters here"


def test_keeps_when_both_groups_present():
    """F와 M이 함께 있으면 채택."""
    assert is_relevant("Federal Reserve raises the fed funds rate", "")
    assert is_relevant("The Fed weighs quantitative easing", "")
    assert is_relevant("Fed Chair Powell on interest rates", "")
    assert is_relevant("Fed officials discuss the discount window", "")
    # 설명(description)에 M이 있어도 성립 — 판정 대상은 제목+설명
    assert is_relevant("The Fed meets this week", "officials debate monetary policy")


def test_drops_when_only_one_group():
    """한쪽 그룹만으로는 채택하지 않는다(AND 규칙)."""
    assert not is_relevant("The Federal Reserve issued a statement", "")      # F만
    assert not is_relevant("ECB and Bank of Japan cut interest rates", "")    # M만(연준 언급 없음)
    assert not is_relevant("The Fed is watching inflation closely", "")       # inflation 은 M 아님
    assert not is_relevant("Powell testifies before Congress", "")            # M만


def test_drops_offtopic_articles():
    assert not is_relevant("Lakers beat Celtics in overtime thriller", "NBA finals recap")
    assert not is_relevant("New iPhone launches next week", "Apple unveils camera upgrades")


def test_word_boundaries_avoid_false_positives():
    """짧은 앵커의 오탐 방지 — FedEx(F 아님) · warship(Warsh 아님)."""
    assert not is_relevant("FedEx raises shipping fees", "package delivery update")
    assert not is_relevant("Warship spotted off the coast", "navy patrol update")
    # warship 이 있어도 진짜 F+M 이면 채택돼야 한다(오탐 방지가 과차단이 되면 안 됨)
    assert is_relevant("Fed funds rate debate as warship news breaks", "")


def test_chair_surnames_including_current():
    """의장 성은 M 그룹 — 역대 + 현 의장(Warsh). 교수 표기 Volker 도 매치."""
    for name in ("Bernanke", "Volcker", "Volker", "Greenspan", "Yellen", "Powell", "Warsh"):
        assert is_relevant(f"The Fed under {name} shifted course", ""), name


def test_collect_filters_by_rule(tmp_path, monkeypatch):
    """collect() 가 F∧M 통과분만 저장한다."""
    import engine.news_scrape as ns
    raw = [
        {"date": "2026-06-17", "title": "Fed signals a cut to the fed funds rate",
         "description": DESC, "source": "reuters.com", "url": "r1",
         "published_at": "2026-06-17T18:00:00Z"},
        {"date": "2026-06-17", "title": "Lakers win game 7", "description": "NBA recap " + DESC,
         "source": "espn.com", "url": "e1", "published_at": "2026-06-17T19:00:00Z"},
        {"date": "2026-06-17", "title": "ECB trims interest rates", "description": DESC,
         "source": "ft.com", "url": "f1", "published_at": "2026-06-17T20:00:00Z"},  # M만 → 제외
    ]
    monkeypatch.setattr(ns, "discover_news", lambda *a, **k: (raw, len(raw)))
    # 탈락분도 임시 경로로 — 안 바꾸면 _log_rejected 가 실제
    # data/news/rejected_news.csv 에 쓴다(2026-09 발견, 테스트 격리 누락).
    monkeypatch.setattr(ns, "REJECTED", tmp_path / "rejected.csv")
    got, new, found = ns.collect(out=tmp_path / "fed_news.csv")
    assert {a["url"] for a in got} == {"r1"}
    with open(tmp_path / "fed_news.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert {r["url"] for r in rows} == {"r1"}
