"""#4 Step 3(B1) 배선 — news_node가 FOMC일 & presser 있으면 성명문 vs 기자회견 괴리 계산,
리포트가 렌더 (모델 없이 monkeypatch)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agents import graph
from reports.report import _news_section

FAKE_PT = {"conf_weighted": 0.06, "confidence": 0.5, "n_sentences": 255}
NO_PP = {"cutoff": None, "pre": None, "post": None, "shift": None}


def _fomc_state():
    st = graph._init_state("2026-06-17")
    st["statement_path"] = "/x/FOMC_2026-06-17.txt"       # FOMC일
    st["index"] = {"conf_weighted": 0.33}                 # 성명문 톤
    return st


def test_news_node_computes_presser_gap_on_fomc_day(monkeypatch):
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)
    monkeypatch.setattr(graph, "index_pre_post", lambda **kw: NO_PP)
    monkeypatch.setattr(graph, "has_presser", lambda d: True)   # 트랜스크립트 있음
    monkeypatch.setattr(graph, "presser_tone", lambda date, analyze=None: FAKE_PT)
    out = graph.news_node(_fomc_state())
    assert out["presser"]["statement_tone"] == 0.33
    assert out["presser"]["tone"] == 0.06
    assert abs(out["presser"]["gap"] - (0.06 - 0.33)) < 1e-9   # 괴리 = presser - 성명문
    assert any("성명문" in l and "기자회견" in l for l in out["log"])


def test_news_node_skips_presser_when_no_transcript(monkeypatch):
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)
    monkeypatch.setattr(graph, "index_pre_post", lambda **kw: NO_PP)
    monkeypatch.setattr(graph, "has_presser", lambda d: False)  # 트랜스크립트 아직 없음
    called = {"n": 0}

    def _spy(date, analyze=None):
        called["n"] += 1
        return FAKE_PT

    monkeypatch.setattr(graph, "presser_tone", _spy)
    out = graph.news_node(_fomc_state())
    assert called["n"] == 0                                # 없으면 호출 안 함
    assert not out["presser"]


def test_report_renders_presser_gap():
    presser = {"statement_tone": 0.33, "tone": 0.06, "gap": -0.27, "n_sentences": 255}
    text = "\n".join(_news_section(None, None, None, presser))
    assert "성명문 vs 기자회견" in text
    assert "-0.270" in text                                # 괴리 표시
    assert "255문장" in text
