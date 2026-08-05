"""회의록 전 구간 배치 점수화 → outputs/minutes_tones.csv (+ 섹션별 톤).

presser_backfill 과 동일 구조·동일 공식(확신도가중). 회의록은 성명문보다 20배 이상
길어(회의당 수백 문장) 배치 추론이 필수라 별도 스크립트로 둔다.

산출 컬럼: date, statement, minutes, gap, n_sentences, {6개 섹션 톤}
  · statement = DB 의 성명문 톤(같은 회의) — 축 간 비교용
  · gap       = minutes − statement (기자회견 분석과 같은 관점)
  · 섹션 톤   = 어느 섹션이 전체 톤을 만드는지 (PVCCEO 위원견해 vs CPA 정책문구 등)

실행: python3 analysis/minutes_backfill.py
"""
import csv
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.minutes_index import SECTIONS, load_sections, minutes_dir  # noqa: E402

DB = ROOT / "data" / "fomc.db"
MINUTES_DIR = ROOT / "data" / "minutes"
OUT = ROOT / "outputs" / "minutes_tones.csv"
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
    """문장 리스트 → 확신도가중 톤 (성명문·기자회견과 동일 공식, 배치 추론)."""
    from engine.sentiment import _NEG, _NEU, _POS
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
    if not weights:
        return None, 0
    wsum = sum(weights) or 1.0
    return sum(s * w for s, w in zip(scores, weights)) / wsum, wsum / len(weights)


def meeting_dates():
    """회의록이 있는 회의일 (data/minutes 기준)."""
    out = []
    for tsv in sorted(MINUTES_DIR.glob("*/*/_titles.tsv")):
        d = tsv.parent.name
        out.append(f"{d[:4]}-{d[4:6]}-{d[6:]}")
    return out


def main():
    from engine.preprocess import split_sentences
    con = sqlite3.connect(DB)

    def stmt_tone(d):
        r = con.execute("SELECT index_value FROM meetings WHERE date=? AND "
                        "method='conf_weighted' AND granularity='meeting'", (d,)).fetchone()
        return r[0] if r else None

    dates = meeting_dates()
    print(f"회의록 {len(dates)}건 배치 점수화 (FinBERT)...")
    tok, model, torch, T = _load()
    rows = []
    for n, date in enumerate(dates, 1):
        secs = load_sections(date)
        if not secs:
            continue
        row = {"date": date}
        all_sents = []
        for code in SECTIONS:
            if code not in secs:
                row[code] = None
                continue
            sents = [s for s in split_sentences(secs[code]) if s.strip()]
            if not sents:
                row[code] = None
                continue
            all_sents.extend(sents)
            tone, _ = _conf_weighted(sents, tok, model, torch, T)
            row[code] = round(tone, 4) if tone is not None else None
        if not all_sents:
            continue
        mtone, conf = _conf_weighted(all_sents, tok, model, torch, T)
        stone = stmt_tone(date)
        row.update({"statement": round(stone, 4) if stone is not None else None,
                    "minutes": round(mtone, 4), "confidence": round(conf, 4),
                    "gap": round(mtone - stone, 4) if stone is not None else None,
                    "n_sentences": len(all_sents)})
        rows.append(row)
        if n % 20 == 0 or n == len(dates):
            print(f"  {n}/{len(dates)} … {date} 톤 {mtone:+.3f} ({len(all_sents)}문장)")
    con.close()

    fields = ["date", "statement", "minutes", "gap", "confidence", "n_sentences"] + list(SECTIONS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 요약 — 축 간 비교(성명문 대비)와 섹션별 평균
    paired = [r for r in rows if r["gap"] is not None]
    print(f"\n산출: {OUT}  ({len(rows)}회의)")
    if paired:
        gaps = [r["gap"] for r in paired]
        lower = sum(1 for g in gaps if g < 0)
        print(f"  회의록 vs 성명문: 평균 괴리 {sum(gaps)/len(gaps):+.4f} · "
              f"회의록이 더 낮은 비율 {lower}/{len(paired)} ({lower/len(paired):.0%})")
    print("  섹션별 평균 톤:")
    for code in SECTIONS:
        vals = [r[code] for r in rows if r.get(code) is not None]
        if vals:
            print(f"    {code:8} {sum(vals)/len(vals):+.4f}  ({len(vals)}회의)")


if __name__ == "__main__":
    main()
