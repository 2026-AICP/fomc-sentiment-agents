"""더미 감성 엔진 (Phase 2 thin-slice 용).

계약(contract): analyze(text) -> {p_pos, p_neu, p_neg, score, entropy}
  - p_pos + p_neu + p_neg == 1
  - entropy >= 0
Phase 3에서 진짜 FinBERT 엔진이 이 계약을 그대로 지키면 교체 끝.

랜덤이 아니라 텍스트 해시 기반으로 '결정적'(같은 입력 → 같은 출력).
"""
import hashlib
import math
from typing import Dict

MODEL_TAG = "dummy"


def analyze(sentence: str) -> Dict[str, float]:
    h = hashlib.sha256(sentence.encode("utf-8")).digest()
    a, b, c = h[0] + 1, h[1] + 1, h[2] + 1   # 0 방지
    total = a + b + c
    p_pos, p_neu, p_neg = a / total, b / total, c / total
    score = p_pos - p_neg
    entropy = -sum(p * math.log(p) for p in (p_pos, p_neu, p_neg))
    return {
        "p_pos": p_pos,
        "p_neu": p_neu,
        "p_neg": p_neg,
        "score": score,
        "entropy": entropy,
    }
