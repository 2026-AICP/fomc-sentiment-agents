"""HRS(2017) 기준 보강 — F그룹 (iii), M그룹 (ii) 표기 변형.

출처: Husted·Rogers·Sun(2017), "Monetary Policy Uncertainty",
      Fed IFDP No.1215 · https://policyuncertainty.com/monetary.html

  (ii)  "monetary policy(ies)" or "interest rate(s)" or "Federal fund(s) rate"
        or "Fed fund(s) rate"          → M그룹
  (iii) "Federal Reserve" or "the Fed" or "Federal Open Market Committee"
        or "FOMC"                      → F그룹

이 파일이 지키는 것:
  · BBD M 집합 26개가 어떤 토글 조합에서도 그대로 동작한다(원본 보존)
  · HRS 항목이 실제로 걸린다
  · NEWS_HRS_TERMS=0 으로 그 층만 정확히 빠진다
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import news_scrape as ns

# BBD MPU 의 M 집합 26개 (policyuncertainty.com/bbd_monetary.html 원문).
# 표기까지 원문 그대로 — Volker 오탈자 포함.
# 이 중 "federal reserve"·"the fed" 는 우리 구현에서 **F그룹**으로 분리돼 있다
# (원문은 26개가 한 목록이지만 우리는 F∧M 구조라 연준 식별어를 떼어냈다).
# 따라서 M 항목으로 테스트하면 안 된다 — BBD_F 로 따로 검사한다.
BBD_F = ["federal reserve", "the fed"]
BBD_M = [
    "money supply", "open market operations",
    "quantitative easing", "monetary policy", "fed funds rate",
    "overnight lending rate", "Bernanke", "Volker", "Greenspan", "central bank",
    "interest rates", "fed chairman", "fed chair", "lender of last resort",
    "discount window", "European Central Bank", "ECB", "Bank of England",
    "Bank of Japan", "BOJ", "Bank of China", "Bundesbank", "Bank of France",
    "Bank of Italy",
]


def _reload(monkeypatch, hrs=None):
    if hrs is None:
        monkeypatch.delenv("NEWS_HRS_TERMS", raising=False)
    else:
        monkeypatch.setenv("NEWS_HRS_TERMS", hrs)
    return importlib.reload(ns)


@pytest.mark.parametrize("term", BBD_M)
@pytest.mark.parametrize("hrs", ["1", "0"])
def test_bbd_m_terms_survive_every_toggle(monkeypatch, term, hrs):
    """BBD M 항목은 토글과 무관하게 걸린다 — 원본은 무슨 일이 있어도 보존."""
    m = _reload(monkeypatch, hrs)
    assert m.relevant_of({"title": f"The Fed and {term}"}), (term, hrs)


@pytest.mark.parametrize("term", BBD_F)
@pytest.mark.parametrize("hrs", ["1", "0"])
def test_bbd_f_terms_survive_every_toggle(monkeypatch, term, hrs):
    """연준 식별어는 F그룹으로 동작한다(M 이 함께 있어야 통과하는 구조는 유지)."""
    m = _reload(monkeypatch, hrs)
    assert m._F_RE.search(term), (term, hrs)
    assert m.relevant_of({"title": f"{term} and monetary policy"}), (term, hrs)


@pytest.mark.parametrize("title", [
    "Federal Open Market Committee weighs interest rates",   # (iii) 정식 명칭
    "FOMC signals steady interest rates",                    # (iii) 약어
])
def test_hrs_f_group_terms(monkeypatch, title):
    """(iii) 의 정식 명칭·약어가 F그룹으로 동작한다."""
    m = _reload(monkeypatch)
    assert m.relevant_of({"title": title}), title


@pytest.mark.parametrize("title", [
    "Fed holds the federal funds rate steady",   # 정식 표기 — BBD 목록엔 없던 변형
    "Fed holds the fed funds rate steady",       # BBD 원문 표기
    "Fed reviews the federal fund rate",         # 단수
    "Fed reviews the fed fund rate",             # 단수
])
def test_hrs_fed_funds_rate_variants(monkeypatch, title):
    """(ii) 연방기금금리의 네 가지 표기를 모두 잡는다."""
    m = _reload(monkeypatch)
    assert m.relevant_of({"title": title}), title


def test_hrs_layer_can_be_disabled(monkeypatch):
    """NEWS_HRS_TERMS=0 이면 그 층만 빠진다 — BBD 표기는 남는다."""
    m = _reload(monkeypatch, hrs="0")
    assert m.HRS_TERMS is False
    assert m._M_RE.pattern == m._M_BASE                 # M 은 BBD 원본 그대로
    assert m.relevant_of({"title": "Fed holds the fed funds rate steady"})
    assert not m.relevant_of({"title": "Fed holds the federal funds rate steady"})


def test_fomc_is_in_f_group(monkeypatch):
    """FOMC 는 F그룹이다 (HRS 기준 (iii) 위치).

    M그룹에 두면 "FOMC + 다른 M단어"를 요구해 원 설계보다 좁아진다.
    """
    m = _reload(monkeypatch, hrs="0")
    assert m._F_RE.search("FOMC meets today")
    # 단독 M 항목으로서의 FOMC 는 제거됐다 — 패턴 문자열 대신 동작으로 검사한다
    # (정규식 이스케이프를 문자열 비교로 확인하면 깨지기 쉽다).
    assert not m._M_RE.search("FOMC"), "FOMC 가 아직 M 그룹에 있다"
    # FOMC 만으로는 부족하고 M 이 함께 있어야 하는 F∧M 구조는 그대로
    assert not m.relevant_of({"title": "FOMC meets today"})
    assert m.relevant_of({"title": "FOMC holds interest rates"})


def test_f_and_m_structure_unchanged(monkeypatch):
    """보강해도 F∧M 구조는 그대로 — 한쪽만 있으면 탈락."""
    m = _reload(monkeypatch)
    assert not m.relevant_of({"title": "ECB cuts interest rates"})        # M만
    assert not m.relevant_of({"title": "The Fed issued a statement"})     # F만
    assert m.relevant_of({"title": "The Fed cut interest rates"})


def teardown_module(module):
    import os
    os.environ.pop("NEWS_HRS_TERMS", None)
    importlib.reload(ns)


# ── 제거된 조교 추천분이 되살아나지 않는지 (2026-09-10) ──────────────────────
# 지도교수 지침에 따라 출처를 대지 못한 표현을 뺐다. 나중에 무심코 다시 들어오면
# 근거 없는 확장이 조용히 부활하므로 여기서 막는다. 되살릴 때는 이 테스트를
# 의도적으로 고치게 되고, 그 순간 근거를 함께 남기게 된다.
@pytest.mark.parametrize("title", [
    "Fed signals a rate cut",                         # rate cut
    "Fed weighs a rate hike in September",            # rate hike
    "US Fed Beige Book reveals a data center boom",   # Beige Book
    "Fed officials await June minutes",               # minutes
    "The S&P 500 slips as Fed meeting looms",         # Fed meeting
    "Fed's Williams ties bond yields to the economy", # 위원 성
    "Fed Governor Bowman adjusts her stance",         # 위원 성
])
def test_unsourced_terms_stay_removed(monkeypatch, title):
    """출처 없는 표현으로만 걸리던 기사는 다시 통과하지 않는다."""
    m = _reload(monkeypatch)
    assert not m.relevant_of({"title": title}), title
