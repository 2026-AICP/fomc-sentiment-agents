"""통합(headline) 지수 — News 축 + Fed 축 결합.

검증(docs/news_fed_index.md §3): 두 축을 표준화(z-score) 후 50:50 결합이
VIX 상관 -0.52 로 각 축 단독(-0.43/-0.38)보다 뚜렷이 나음.

현 단계(뼈대): 두 conf_weighted 점수(둘 다 score=p_pos-p_neg 기반, 동일 [-1,1]
척도)를 raw 가중평균으로 결합. 흐름부터 관통시키는 게 목적.
다듬기(refine): 과거 평균·표준편차로 z 표준화 후 결합(검증본 -0.52 재현).
   → z 파라미터(각 축 mean/std)는 outputs 검증본에서 주입 예정.

원칙: 뉴스가 없으면(과거 회의 등) headline = Fed 단독으로 우아하게 폴백.
"""
from typing import Optional


def combine(fed: Optional[float], news: Optional[float], w_fed: float = 0.5) -> Optional[dict]:
    """Fed·News conf_weighted 점수 → 통합 결과 dict (없으면 None).

    - 둘 다 있음: raw 가중평균 (기본 50:50).
    - 뉴스 없음:  Fed 단독 (method=fed_only).
    - Fed 없음:   News 단독 (method=news_only).
    반환 예: {headline, method, w_fed, w_news}.
    """
    if fed is None and news is None:
        return None
    if news is None:
        return {"headline": fed, "method": "fed_only", "w_fed": 1.0, "w_news": 0.0}
    if fed is None:
        return {"headline": news, "method": "news_only", "w_fed": 0.0, "w_news": 1.0}
    w_news = 1.0 - w_fed
    return {"headline": w_fed * fed + w_news * news, "method": "raw_weighted",
            "w_fed": w_fed, "w_news": w_news}
