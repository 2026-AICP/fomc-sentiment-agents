"""strategy_node 의 신뢰도 게이트 배선 테스트 (질문 5 피드백).

기존 analysis/news_signals.py 의 confident() 게이트는 daily_signals.csv 를 만드는
실제 파이프라인(agents/graph.py::strategy_node)에는 연결돼 있지 않아, 기사 수가
적어도(예: 6건) '주의' 경보가 그대로 발동하는 문제가 있었다. 이 테스트는 그 배선을
DB·네트워크 없이(state 딕셔너리를 직접 구성해) 고정한다.
"""
from agents import graph
from analysis.signals import GRADE_CAUTION, GRADE_WATCH


def _state(tone, vix_chg, news=None):
    return {"date": "2026-08-13", "index": {"conf_weighted": tone},
            "headline": {"headline": tone, "method": "z_weighted"},
            "market": {"spx_ret_cc": None, "vix_chg": vix_chg, "ust2y_chg": None},
            "news": news, "log": []}


def test_caution_downgraded_to_watch_when_articles_too_few(tmp_path, monkeypatch):
    monkeypatch.setattr(graph, "DAILY_SIGNALS", tmp_path / "daily_signals.csv")
    state = _state(tone=0.30, vix_chg=1.5, news={"n_articles": 6, "ci_lo": -0.9, "ci_hi": 0.9})
    out = graph.strategy_node(state)
    assert out["signals"]["grade"] == GRADE_WATCH
    assert out["signals"]["gate_reason"]
    # 측정치는 보존 — headline 지수 자체는 게이트와 무관하게 그대로.
    assert out["headline"]["headline"] == 0.30


def test_caution_kept_when_articles_sufficient(tmp_path, monkeypatch):
    monkeypatch.setattr(graph, "DAILY_SIGNALS", tmp_path / "daily_signals.csv")
    state = _state(tone=0.30, vix_chg=1.5, news={"n_articles": 40, "ci_lo": -0.05, "ci_hi": 0.05})
    out = graph.strategy_node(state)
    assert out["signals"]["grade"] == GRADE_CAUTION
    assert out["signals"]["gate_reason"] is None


def test_no_news_component_skips_gate(tmp_path, monkeypatch):
    """뉴스 축이 아예 없는 날(Fed 단독)은 기사수 게이트 대상이 아니다."""
    monkeypatch.setattr(graph, "DAILY_SIGNALS", tmp_path / "daily_signals.csv")
    state = _state(tone=0.30, vix_chg=1.5, news=None)
    out = graph.strategy_node(state)
    assert out["signals"]["grade"] == GRADE_CAUTION
    assert out["signals"]["gate_reason"] is None
