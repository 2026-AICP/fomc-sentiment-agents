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

# 온도(temperature scaling): 기본 T=1.0 = 원본 FinBERT(작년 파인튜닝 그대로).
#   지도교수 피드백(2026-07): 자체 라벨 기반 보정(T=3.1)은 제외 — 모델에 이미
#   내장된 기존 라벨을 신뢰하고 baseline 사용. 필요시 FINBERT_TEMPERATURE 로 조정.
TEMPERATURE = float(os.getenv("FINBERT_TEMPERATURE", "1.0"))
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
    # GPU 있으면 GPU, 없으면 CPU 자동 (로컬=CPU / UNIST HPC=GPU 둘 다 동작)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    return tok, model, torch, device


def analyze(sentence: str) -> Dict[str, float]:
    tok, model, torch, device = _load()
    inputs = tok(sentence, return_tensors="pt", truncation=True, max_length=256).to(device)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits / TEMPERATURE, dim=-1)[0].tolist()  # 온도 적용 (기본 T=1 = 원본)

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
