"""진짜 FinBERT 감성 엔진 (Phase 3 — 베이스라인).

dummy_sentiment.analyze 와 동일한 계약을 지킨다:
    analyze(text) -> {p_pos, p_neu, p_neg, score, entropy}
softmax 확률을 그대로 반환한다 (작년처럼 argmax 라벨만 쓰지 않음).

모델: 작년 팀이 파인튜닝한 FinBERT (base = yiyanghkust/finbert-pretrain).
  - 공개 ProsusAI/finbert 가 아니라 FOMC·PhraseBank·FiQA 로 파인튜닝된 버전.
  - 가중치(419MB)는 git 에 올리지 않는다. 로컬 경로로 로드한다.

★라벨 매핑 (검증 완료): config 의 id2label 이 LABEL_0/1/2 로 무명이라 의미를 명시한다.
    LABEL_0 = neutral  -> softmax[0] = p_neu
    LABEL_1 = positive -> softmax[1] = p_pos
    LABEL_2 = negative -> softmax[2] = p_neg
  (작년 reference 노트북 + 직접 추론 검증으로 확인. ProsusAI/finbert 와는 순서가 다름.)
"""
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict

# 온도 보정(temperature scaling): human label 150문장으로 캘리브레이션.
#   T=1.0 → 원본(과신, ECE 0.257). T=3.1 → 보정(ECE 0.07~0.10, 2-fold CV).
#   확신도 가중 인덱스가 정직하려면 보정 필요. T=1 로 두면 베이스라인 복원.
TEMPERATURE = float(os.getenv("FINBERT_TEMPERATURE", "3.1"))
MODEL_TAG = "finbert-cal" if abs(TEMPERATURE - 1.0) > 1e-6 else "finbert-finetuned"

# 모델 디렉토리: 환경변수 우선, 없으면 저장소 루트의 models/finbert-finetuned/
_DEFAULT_DIR = Path(__file__).resolve().parents[1] / "models" / "finbert-finetuned"
MODEL_DIR = os.getenv("FINBERT_MODEL_DIR", str(_DEFAULT_DIR))

# 검증된 라벨 인덱스 (위 docstring 참조)
_NEU, _POS, _NEG = 0, 1, 2


@lru_cache(maxsize=1)
def _load():
    """모델·토크나이저 1회 로드 (캐시)."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if not Path(MODEL_DIR).exists():
        raise FileNotFoundError(
            f"FinBERT 모델을 찾을 수 없습니다: {MODEL_DIR}\n"
            "드롭박스의 파인튜닝 모델을 이 경로에 두거나 FINBERT_MODEL_DIR 로 지정하세요."
        )
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    model.eval()
    return tok, model, torch


def analyze(sentence: str) -> Dict[str, float]:
    tok, model, torch = _load()
    inputs = tok(sentence, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits / TEMPERATURE, dim=-1)[0].tolist()  # 온도 보정

    p_neu, p_pos, p_neg = probs[_NEU], probs[_POS], probs[_NEG]
    score = p_pos - p_neg
    entropy = -sum(p * math.log(p) for p in (p_pos, p_neu, p_neg) if p > 0)
    return {
        "p_pos": p_pos,
        "p_neu": p_neu,
        "p_neg": p_neg,
        "score": score,
        "entropy": entropy,
    }
