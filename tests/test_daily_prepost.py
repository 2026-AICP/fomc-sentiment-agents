"""2d Step 2 배선 — news_node가 FOMC일에 pre/post 계산, 리포트가 렌더(모델 없이 monkeypatch)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agents import graph
from reports.report import _news_section

FAKE_PP = {
    "cutoff": "2026-06-17T18:00:00",
    "pre": {"conf_weighted": 0.10, "ci_lo": 0.0, "ci_hi": 0.2, "n_articles": 3},
    "post": {"conf_weighted": 0.40, "ci_lo": 0.3, "ci_hi": 0.5, "n_articles": 5},
    "shift": 0.30,
}


def test_news_node_computes_prepost_on_fomc_day(monkeypatch):
    state = graph._init_state("2026-06-17")
    state["statement_path"] = "/x/FOMC_2026-06-17.txt"    # FOMC일 표식
    state["index"] = {"conf_weighted": 0.30}              # analyst 결과 있음(DB 불필요)
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)
    monkeypatch.setattr(graph, "index_pre_post", lambda **kw: FAKE_PP)
    out = graph.news_node(state)
    assert out["pre_post"]["shift"] == 0.30
    assert any("발표 전/후" in l for l in out["log"])


def test_news_node_skips_prepost_on_nonfomc_day(monkeypatch):
    state = graph._init_state("2026-06-18")               # statement_path 비어있음 = 회의 아님
    state["index"] = {"conf_weighted": 0.30}
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)
    called = {"n": 0}

    def _spy(**kw):
        called["n"] += 1
        return FAKE_PP

    monkeypatch.setattr(graph, "index_pre_post", _spy)
    out = graph.news_node(state)
    assert called["n"] == 0                                # 회의 아니면 호출 안 함
    assert not out["pre_post"]


def test_report_renders_prepost():
    text = "\n".join(_news_section(None, None, FAKE_PP))
    assert "발표 전/후" in text
    assert "+0.300" in text                                # shift 표시
    assert "3건" in text and "5건" in text                 # pre/post 기사수


def test_report_prepost_one_sided():
    pp = {"pre": None, "post": {"conf_weighted": 0.4, "n_articles": 5}, "shift": None}
    text = "\n".join(_news_section(None, None, pp))
    assert "발표 후만 수집" in text
