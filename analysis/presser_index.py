"""기자회견(presser) 톤 산출 — data/pressers/*.txt 의 의장 발언을 성명문과 동일 방식으로 점수화.

문장별 FinBERT(T=3.1) → 확신도가중(conf_weighted, index/aggregate 공식과 동일).
성명문과 apples-to-apples 라서 '성명문 vs presser' 비교(Step 3)의 재료가 된다.

  presser_tone(date) → {conf_weighted, confidence, n_sentences} 또는 None(파일 없음)

실행:  python3 analysis/presser_index.py 2026-06-17
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESSER_DIR = ROOT / "data" / "pressers"
LN3 = math.log(3)               # 3클래스 최대 엔트로피(확신도 정규화)


def presser_path(date: str) -> Path:
    return PRESSER_DIR / f"FOMC_presconf_{date}.txt"


def has_presser(date: str) -> bool:
    return presser_path(date).exists()


def presser_tone(date: str, analyze=None):
    """presser 의장 발언 → {conf_weighted, confidence, n_sentences} 또는 None.

    analyze: 문장→{score, entropy, ...} 스코어러. 기본은 engine.sentiment(FinBERT T=3.1)로
    성명문과 동일(비교 공정). 테스트는 가짜 스코어러를 주입해 모델 없이 검증.
    """
    p = presser_path(date)
    if not p.exists():
        return None
    sents = [s for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]
    if not sents:
        return None
    if analyze is None:
        from engine.sentiment import analyze
    scores, weights = [], []
    for s in sents:
        r = analyze(s)
        scores.append(r["score"])
        weights.append(max(0.0, 1.0 - r["entropy"] / LN3))
    wsum = sum(weights) or 1.0
    cw = sum(sc * w for sc, w in zip(scores, weights)) / wsum
    return {"conf_weighted": cw, "confidence": wsum / len(weights), "n_sentences": len(sents)}


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-06-17"
    res = presser_tone(date)
    if res is None:
        raise SystemExit(f"presser 파일 없음: {presser_path(date)}\n"
                         "먼저 engine/presser_scrape.py 로 수집하세요.")
    print(f"{date} presser 톤: {res['conf_weighted']:+.4f}  "
          f"(확신도 {res['confidence']:.3f} · {res['n_sentences']}문장)")
