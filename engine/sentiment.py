"""감성 분석 엔진 — 금융 텍스트용 3분류 모델 추론.

dummy_sentiment.analyze 와 동일한 계약을 지킨다:
    analyze(text) -> {p_pos, p_neu, p_neg, score, entropy}
softmax 확률을 그대로 반환한다 (argmax 라벨만 쓰지 않음).

모델 가중치는 저장소에 포함하지 않는다(용량·배포 정책). 로컬 경로에서 로드하며,
경로는 FINBERT_MODEL_DIR 로 지정할 수 있다. 취득 방법은 팀 내부 안내를 따른다.

★라벨 매핑 (직접 추론으로 검증): config 의 id2label 이 LABEL_0/1/2 로 무명이라 명시한다.
    LABEL_0 = neutral  -> softmax[0] = p_neu
    LABEL_1 = positive -> softmax[1] = p_pos
    LABEL_2 = negative -> softmax[2] = p_neg
"""
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict

# 온도(temperature scaling): 기본 T=1.0 = 모델 출력을 그대로 사용.
#   지도교수 피드백(2026-07): 자체 라벨 기반 보정(T=3.1)은 제외하고 baseline 사용.
#   필요시 FINBERT_TEMPERATURE 로 조정.
TEMPERATURE = float(os.getenv("FINBERT_TEMPERATURE", "1.0"))
MODEL_TAG = "finbert-cal" if abs(TEMPERATURE - 1.0) > 1e-6 else "finbert-finetuned"

# 모델 디렉토리: 환경변수 우선, 없으면 저장소 루트의 models/ 아래 기본 경로
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
            f"감성 모델을 찾을 수 없습니다: {MODEL_DIR}\n"
            "모델 파일을 이 경로에 두거나 FINBERT_MODEL_DIR 로 경로를 지정하세요."
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
