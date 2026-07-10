"""presser 히스토리 백필 분석 — "기자회견 톤이 성명문보다 신중한가?"

data/pressers/*.txt 전부를 배치 FinBERT(T=3.1)로 점수화 → presser 톤(conf_weighted).
fomc.db 의 성명문 톤과 짝지어 괴리(presser − 성명문)를 여러 회의로 검정한다:
  · 부호검정(sign test): 'presser < 성명문' 회의 비율이 우연(50%)과 다른가
  · 평균 괴리 + Wilcoxon 부호순위 검정

성명문과 동일 공식(문장별 → 확신도가중)이라 apples-to-apples.
실행: python3 analysis/presser_backfill.py   (산출: outputs/presser_tones.csv)
"""
import csv
import math
import sqlite3
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PRESSER_DIR = ROOT / "data" / "pressers"
DB = ROOT / "data" / "fomc.db"
OUT = ROOT / "outputs" / "presser_tones.csv"
LN3 = math.log(3)
BATCH, MAXLEN = 32, 256


def _load():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from engine.sentiment import MODEL_DIR, TEMPERATURE
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    model.eval()
    return tok, model, torch, TEMPERATURE


def _conf_weighted(sents, tok, model, torch, T):
    """문장 리스트 → 확신도가중 톤 (성명문 aggregate 공식과 동일, 배치 추론)."""
    from engine.sentiment import _NEU, _POS, _NEG
    scores, weights = [], []
    with torch.no_grad():
        for i in range(0, len(sents), BATCH):
            enc = tok(sents[i:i + BATCH], return_tensors="pt",
                      truncation=True, max_length=MAXLEN, padding=True)
            for row in torch.softmax(model(**enc).logits / T, dim=-1).tolist():
                p_neu, p_pos, p_neg = row[_NEU], row[_POS], row[_NEG]
                scores.append(p_pos - p_neg)
                ent = -sum(p * math.log(p) for p in (p_pos, p_neu, p_neg) if p > 0)
                weights.append(max(0.0, 1.0 - ent / LN3))
    wsum = sum(weights) or 1.0
    return sum(s * w for s, w in zip(scores, weights)) / wsum


def _sign_test_two_sided(n, k):
    """이항(n, 0.5)에서 관측 k(성공)의 양측 부호검정 p."""
    def tail_ge(a):
        return sum(comb(n, i) for i in range(a, n + 1)) / (2 ** n)
    return min(1.0, 2 * min(tail_ge(k), tail_ge(n - k)))


def main():
    con = sqlite3.connect(DB)

    def stmt_tone(d):
        r = con.execute("SELECT index_value FROM meetings WHERE date=? AND "
                        "method='conf_weighted' AND granularity='meeting'", (d,)).fetchone()
        return r[0] if r else None

    files = sorted(PRESSER_DIR.glob("FOMC_presconf_*.txt"))
    print(f"presser {len(files)}건 배치 점수화 (FinBERT T=3.1)...")
    tok, model, torch, T = _load()
    rows = []
    for f in files:
        date = f.stem.replace("FOMC_presconf_", "")
        sents = [s for s in f.read_text(encoding="utf-8").splitlines() if s.strip()]
        if not sents:
            continue
        ptone = _conf_weighted(sents, tok, model, torch, T)
        stone = stmt_tone(date)
        rows.append({"date": date, "statement": stone, "presser": ptone,
                     "gap": (ptone - stone) if stone is not None else None,
                     "n_sentences": len(sents)})
    con.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=["date", "statement", "presser", "gap", "n_sentences"])
        w.writeheader()
        w.writerows(rows)

    gaps = [r["gap"] for r in rows if r["gap"] is not None]
    n = len(gaps)
    n_lower = sum(1 for g in gaps if g < 0)
    mean_gap = sum(gaps) / n if n else float("nan")
    p_sign = _sign_test_two_sided(n, n_lower)

    print(f"\n── 결과: {n}개 회의 (성명문·presser 짝) ──")
    print(f"  presser < 성명문 (더 신중): {n_lower}/{n} = {n_lower/n:.0%}")
    print(f"  평균 괴리 (presser − 성명문): {mean_gap:+.4f}")
    print(f"  부호검정 p = {p_sign:.4g}  → {'유의(우연 아님)' if p_sign < 0.05 else '유의하지 않음'}")
    try:
        from scipy.stats import wilcoxon
        print(f"  Wilcoxon 부호순위 p = {wilcoxon(gaps).pvalue:.4g}")
    except Exception:
        pass
    print(f"\n산출: {OUT}")


if __name__ == "__main__":
    main()
