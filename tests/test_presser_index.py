"""presser 톤 산출 검증 — conf_weighted 공식 + 확신도 가중 (모델 없이 가짜 스코어러)."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analysis.presser_index as pi


def _seed(tmp_path, monkeypatch, text):
    d = tmp_path / "pressers"
    d.mkdir()
    (d / "FOMC_presconf_2026-06-17.txt").write_text(text, encoding="utf-8")
    monkeypatch.setattr(pi, "PRESSER_DIR", d)


def test_conf_weighted_average(tmp_path, monkeypatch):
    """엔트로피 동일하면 conf_weighted = 단순 평균."""
    _seed(tmp_path, monkeypatch, "hawkish line\ndovish line\n")

    def fake(s):
        return {"score": -0.5 if "hawkish" in s else 0.5, "entropy": 0.0}

    res = pi.presser_tone("2026-06-17", analyze=fake)
    assert res["n_sentences"] == 2
    assert res["conf_weighted"] == pytest.approx(0.0)     # (-0.5 + 0.5)/2
    assert res["confidence"] == pytest.approx(1.0)        # entropy 0 → w=1


def test_low_confidence_sentence_downweighted(tmp_path, monkeypatch):
    """최대 엔트로피(불확실) 문장은 가중치 0 → 지수에 영향 없음."""
    _seed(tmp_path, monkeypatch, "confident line\nuncertain line\n")

    def fake(s):
        if "confident" in s:
            return {"score": 1.0, "entropy": 0.0}          # w=1
        return {"score": -1.0, "entropy": math.log(3)}     # w=0 (최대 엔트로피)

    res = pi.presser_tone("2026-06-17", analyze=fake)
    assert res["conf_weighted"] == pytest.approx(1.0)      # 불확실 문장 무시 → +1.0
    assert res["confidence"] == pytest.approx(0.5)         # 평균 가중치 (1+0)/2


def test_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, "PRESSER_DIR", tmp_path)       # 빈 디렉토리
    assert pi.presser_tone("2099-01-01", analyze=lambda s: {}) is None


def test_none_when_empty_file(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, "\n  \n")                 # 공백뿐
    assert pi.presser_tone("2026-06-17", analyze=lambda s: {}) is None
