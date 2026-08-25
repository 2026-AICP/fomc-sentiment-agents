"""신뢰도 게이트 — 표본이 얇을 때 경보만 막고 지수는 유지하는지 검증.

기사가 1~2건인 날은 일별 지수가 크게 튀어 헛경보가 난다(실측 +7.09 사례).
지수를 지우면 시계열에 구멍이 생기므로, 값은 남기고 등급만 '관망'으로 바꾼다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.graph import GRADE_HOLD, strategy_node
from analysis.news_signals import confident


def _state(news):
    return {"date": "2026-08-05", "index": {"conf_weighted": 0.29},
            "headline": {"headline": 7.09, "method": "z_weighted"},
            "market": {"spx_ret_cc": -1.2, "vix_chg": 2.0, "ust2y_chg": 0.15},
            "news": news, "signals": {}, "log": [], "errors": []}


def test_confident_blocks_small_sample():
    ok, why = confident(1, None, None)
    assert not ok and "1건" in why


def test_confident_passes_enough_articles():
    ok, _ = confident(60, -0.07, 0.26)
    assert ok


def test_gate_holds_alert_but_keeps_index():
    r = strategy_node(_state({"n_articles": 1, "ci_lo": None, "ci_hi": None}))
    assert r["signals"]["grade"] == GRADE_HOLD          # 경보는 보류
    assert r["signals"]["fired"]                        # 측정 결과는 남음
    assert r["headline"]["headline"] == 7.09            # 지수는 그대로


def test_no_gate_when_sample_sufficient():
    r = strategy_node(_state({"n_articles": 60, "ci_lo": -0.07, "ci_hi": 0.26}))
    assert r["signals"]["grade"] != GRADE_HOLD
    assert r["signals"]["gate_reason"] is None


def test_fed_only_day_is_not_gated():
    """뉴스가 없어 Fed 단독으로 계산된 날은 뉴스 표본과 무관 → 게이트 대상 아님."""
    s = _state({"n_articles": 1, "ci_lo": None, "ci_hi": None})
    s["headline"]["method"] = "fed_only"
    r = strategy_node(s)
    assert r["signals"]["grade"] != GRADE_HOLD
