"""통합(headline) 지수 — News 축 + Fed 축 결합.

검증(docs/news_fed_index.md §3): 두 축을 표준화(z-score) 후 50:50 결합이
VIX 상관 -0.534 로 각 축 단독(Fed -0.436 / News -0.386)보다 뚜렷이 나음
(2000-2021, 256개월; 성명문 220 + WSJ 38,869 기사로 재현).

두 축은 conf_weighted(둘 다 score=p_pos-p_neg 기반) 이지만 분산이 달라
(Fed σ≈0.165 ≫ News σ≈0.065) raw 로 섞으면 Fed 가 지배한다. 그래서 각 축을
과거 평균·표준편차로 z 표준화한 뒤 가중결합해 검증본(-0.534)을 재현한다.
z 파라미터: analysis/headline_norm.json (검증 스크립트가 산출·저장).

원칙: 뉴스가 없으면(과거 회의 등) headline = Fed 단독으로 우아하게 폴백.
      파라미터 파일이 없으면 z 없이 raw 로 degrade (크래시 없음).
"""
import json
from pathlib import Path
from typing import Optional

_NORM_PATH = Path(__file__).with_name("headline_norm.json")
_NORM: Optional[dict] = None


def _norm() -> dict:
    """z 파라미터 로드(1회 캐시). 파일 없거나 손상 시 {} → raw 폴백."""
    global _NORM
    if _NORM is None:
        try:
            _NORM = json.loads(_NORM_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _NORM = {}
    return _NORM


def _z(x: float, axis: str) -> float:
    """축 값을 z 표준화. 파라미터 없으면 원값 그대로(raw 폴백)."""
    p = _norm().get(axis)
    if not p or p.get("std", 0.0) <= 1e-9:
        return x
    return (x - p["mean"]) / p["std"]


def combine(fed: Optional[float], news: Optional[float], w_fed: float = 0.5) -> Optional[dict]:
    """Fed·News conf_weighted 점수 → 통합 결과 dict (없으면 None).

    각 축을 z 표준화(analysis/headline_norm.json)한 뒤 가중결합한다.
    - 둘 다 있음: z 가중평균 (기본 50:50, method=z_weighted).
    - 뉴스 없음:  Fed 단독 z (method=fed_only).
    - Fed 없음:   News 단독 z (method=news_only).
    반환 예: {headline, method, w_fed, w_news}.  headline 은 z 척도(0≈과거평균).
    """
    if fed is None and news is None:
        return None
    if news is None:
        return {"headline": _z(fed, "fed"), "method": "fed_only", "w_fed": 1.0, "w_news": 0.0}
    if fed is None:
        return {"headline": _z(news, "news"), "method": "news_only", "w_fed": 0.0, "w_news": 1.0}
    w_news = 1.0 - w_fed
    headline = w_fed * _z(fed, "fed") + w_news * _z(news, "news")
    tag = "z_weighted" if _norm().get("fed") else "raw_weighted"
    return {"headline": headline, "method": tag, "w_fed": w_fed, "w_news": w_news}
