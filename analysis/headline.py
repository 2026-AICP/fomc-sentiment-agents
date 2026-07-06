"""통합(headline) 지수 — News 축 + Fed 축 결합.

검증(docs/news_fed_index.md §3): 두 축을 표준화(z-score) 후 50:50 결합이
VIX 상관 -0.534 로 각 축 단독(Fed -0.436 / News -0.386)보다 뚜렷이 나음
(2000-2021 256개월; 성명문 220 + WSJ 38,869 기사로 재현).

두 축은 conf_weighted(둘 다 score=p_pos-p_neg 기반)이지만 분산이 달라
(Fed σ≈0.165 ≫ News σ≈0.065) raw 로 섞으면 Fed 가 지배한다. 그래서 각 축을
평균·표준편차로 z 표준화한 뒤 결합해 검증본(-0.534)을 재현한다.

z 파라미터(각 축 mean/std) 우선순위:
  1) combine(...) 에 명시한 fed_stats·news_stats  (예: 런타임 zstats() 결과)
  2) analysis/headline_norm.json  (build_headline_norm.py 로 산출·커밋된 검증본)
  3) 둘 다 없으면 raw 가중평균으로 degrade (크래시 없음)

원칙: 뉴스가 없으면(과거 회의 등) headline = Fed 단독으로 우아하게 폴백.
"""
import json
from pathlib import Path
from typing import Optional, Sequence, Tuple

Stats = Tuple[float, float]  # (mean, std)

_NORM_PATH = Path(__file__).with_name("headline_norm.json")
_NORM: Optional[dict] = None


def zstats(values: Sequence[Optional[float]]) -> Optional[Stats]:
    """히스토리 → (평균, 표준편차). 값 2개 미만이면 None(표준화 불가).

    런타임 표본에서 z 파라미터를 구할 때 사용. 표본이 작으면 잠정값이라
    검증본(headline_norm.json)을 쓰는 편이 안정적이다.
    """
    xs = [v for v in values if v is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)   # 표본분산
    return (m, var ** 0.5)


def _norm() -> dict:
    """검증본 z 파라미터 로드(1회 캐시). 파일 없거나 손상 시 {} → raw 폴백."""
    global _NORM
    if _NORM is None:
        try:
            _NORM = json.loads(_NORM_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _NORM = {}
    return _NORM


def _axis_stats(axis: str) -> Optional[Stats]:
    """headline_norm.json 에서 축(fed/news)의 (mean, std) 반환. 없으면 None."""
    p = _norm().get(axis)
    if not p or p.get("std", 0.0) <= 1e-9:
        return None
    return (p["mean"], p["std"])


def _z(v: float, stats: Optional[Stats]) -> float:
    """stats=(mean,std) 로 z 표준화. stats 없으면 원값 그대로(raw 폴백)."""
    if not stats or stats[1] <= 0:
        return v
    return (v - stats[0]) / stats[1]


def combine(fed: Optional[float], news: Optional[float], w_fed: float = 0.5,
            fed_stats: Optional[Stats] = None,
            news_stats: Optional[Stats] = None) -> Optional[dict]:
    """Fed·News conf_weighted 점수 → 통합 결과 dict (없으면 None).

    각 축을 z 표준화 후 가중결합. z 파라미터는 인자(fed_stats/news_stats) →
    headline_norm.json → (없으면) raw 순으로 결정한다.
    - 둘 다 있음: z 가중평균(method=z_weighted), 파라미터 없으면 raw_weighted
    - 뉴스 없음:  Fed 단독(method=fed_only)
    - Fed 없음:   News 단독(method=news_only)
    반환: {headline, method, w_fed, w_news}. z 적용 시 headline 은 z 척도(0≈과거평균).
    """
    if fed is None and news is None:
        return None
    fs = fed_stats or _axis_stats("fed")
    ns = news_stats or _axis_stats("news")
    if news is None:
        return {"headline": _z(fed, fs), "method": "fed_only", "w_fed": 1.0, "w_news": 0.0}
    if fed is None:
        return {"headline": _z(news, ns), "method": "news_only", "w_fed": 0.0, "w_news": 1.0}
    w_news = 1.0 - w_fed
    if fs and ns:
        headline = w_fed * _z(fed, fs) + w_news * _z(news, ns)
        return {"headline": headline, "method": "z_weighted", "w_fed": w_fed, "w_news": w_news}
    return {"headline": w_fed * fed + w_news * news, "method": "raw_weighted",
            "w_fed": w_fed, "w_news": w_news}
