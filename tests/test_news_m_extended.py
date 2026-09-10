"""M그룹 확장(2026-09, 조교 승인) — 원본 보존·확장 동작·되돌리기.

지도교수 지정 27개는 손대지 않고 _M_EXT 로만 넓혔다. 원본이 그대로 남아 있는지와
NEWS_M_EXTENDED=0 으로 정확히 원복되는지가 이 파일의 핵심이다 — 지정 사항이라
"확장을 껐더니 미묘하게 다른 규칙이 됐다"가 생기면 안 된다.
"""
import importlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import news_scrape as ns

# 지도교수 지정 원본 27개 (2026-07). 여기 하드코딩해 두고 대조한다 —
# 코드가 바뀌어도 이 목록이 변하면 테스트가 깨지도록.
BASE_TERMS = [
    "money supply", "open market operation", "quantitative easing",
    "monetary policy", "fed funds rate", "overnight lending rate",
    "interest rate", "lender of last resort", "discount window",
    "central bank", "fed chairman", "bernanke", "volcker", "greenspan",
    "yellen", "powell", "warsh", "european central bank", "ecb",
    "bank of england", "bank of japan", "boj", "bank of china",
    "bundesbank", "bank of france", "bank of italy",
]


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("NEWS_M_EXTENDED", raising=False)
    else:
        monkeypatch.setenv("NEWS_M_EXTENDED", value)
    return importlib.reload(ns)


@pytest.mark.parametrize("term", BASE_TERMS)
def test_base_terms_survive_extension(monkeypatch, term):
    """원본 27개는 확장을 켜도 그대로 동작한다."""
    m = _reload(monkeypatch, None)
    assert m.relevant_of({"title": f"The Fed and {term} today"}), term


@pytest.mark.parametrize("term", BASE_TERMS)
def test_base_terms_work_when_reverted(monkeypatch, term):
    """확장을 꺼도 원본 27개는 그대로다."""
    m = _reload(monkeypatch, "0")
    assert m.relevant_of({"title": f"The Fed and {term} today"}), term


def test_revert_restores_exact_original(monkeypatch):
    """NEWS_M_EXTENDED=0 이면 패턴이 원본과 **문자 그대로** 같아야 한다."""
    m = _reload(monkeypatch, "0")
    assert m.M_EXTENDED is False
    assert m._M_RE.pattern == m._M_BASE


@pytest.mark.parametrize("title", [
    "Fed signals a rate cut",                      # rate cut
    "Fed weighs a rate hike in September",         # rate hike
    "FOMC holds rates as Fed weighs data",         # FOMC
    "US Fed Beige Book reveals data center boom",  # Beige Book
    "The S&P 500 could retest lows as Fed meeting looms",   # Fed meeting
    "Fed's Williams ties bond yields to strong economy",    # 지역 연은 총재
    "Fed Governor Bowman adjusts rate stance",
])
def test_extension_recovers_policy_articles(monkeypatch, title):
    """확장이 실제로 놓치던 정책 기사를 잡는다."""
    m = _reload(monkeypatch, None)
    assert m.relevant_of({"title": title}), title


@pytest.mark.parametrize("title", [
    "Fed officials await June minutes",
    "Federal Reserve releases June minutes",
    "Fed's June minutes show a split",
    "Fed watchers read the minutes of the meeting",
])
def test_minutes_narrow_form_matches_real_headlines(monkeypatch, title):
    """minutes 는 연준 문맥이 붙은 형태를 잡는다(사이 단어 3개까지)."""
    m = _reload(monkeypatch, None)
    assert m.relevant_of({"title": title}), title


@pytest.mark.parametrize("title", [
    "Stocks jumped in the final 30 minutes as Fed watchers waited",
    "The Fed rally faded in the last 20 minutes of trading",
])
def test_minutes_does_not_match_time_expressions(monkeypatch, title):
    """'30 minutes' 류 시간 표현은 걸리지 않는다 — 좁힌 이유다."""
    m = _reload(monkeypatch, None)
    assert not m.relevant_of({"title": title}), title


@pytest.mark.parametrize("title", [
    "Fed grows more hawkish on inflation",
    "A dovish Fed keeps markets calm",
    "Fed tightening cycle nears its end",
])
def test_deferred_terms_not_included(monkeypatch, title):
    """tightening/easing/dovish/hawkish 는 이번 확장에 넣지 않았다(조교 의견).

    나중에 추가 표본 검토 후 결정한다. 그때까지 조용히 들어가지 않도록 못 박는다.
    """
    m = _reload(monkeypatch, None)
    assert not m.relevant_of({"title": title}), title


def test_f_group_still_required(monkeypatch):
    """확장해도 F∧M 구조는 그대로 — 연준 언급이 없으면 탈락."""
    m = _reload(monkeypatch, None)
    assert not m.relevant_of({"title": "ECB signals a rate cut"})
    assert not m.relevant_of({"title": "Williams says the economy is strong"})
    assert m.relevant_of({"title": "Fed's Williams says the economy is strong"})


def test_extension_is_pure_superset(monkeypatch):
    """확장은 원본의 상위집합이다 — 원본이 통과시키던 것을 막지 않는다."""
    base = _reload(monkeypatch, "0")
    samples = [f"The Fed and {t} today" for t in BASE_TERMS]
    passed_base = [s for s in samples if base.relevant_of({"title": s})]
    ext = _reload(monkeypatch, None)
    for s in passed_base:
        assert ext.relevant_of({"title": s}), s


def teardown_module(module):
    import os
    os.environ.pop("NEWS_M_EXTENDED", None)
    importlib.reload(ns)
