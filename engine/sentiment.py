"""진짜 FinBERT 감성 엔진 자리 (Phase 3에서 구현).

dummy_sentiment.analyze 와 동일한 계약을 지켜야 한다:
    analyze(text) -> {p_pos, p_neu, p_neg, score, entropy}
구현 시 softmax 확률을 그대로 반환할 것 (작년처럼 argmax 라벨만 쓰지 말 것).
"""
from typing import Dict

MODEL_TAG = "finbert-base"


def analyze(sentence: str) -> Dict[str, float]:
    raise NotImplementedError("Phase 3: FinBERT 엔진 구현 예정")
