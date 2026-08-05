"""회의록(minutes) 톤 산출 — data/minutes/ 를 성명문·기자회견과 **동일 방식**으로 점수화.

문장별 FinBERT → 확신도가중(conf_weighted). 세 축(성명문·회의록·기자회견)이 같은 공식이라
apples-to-apples 비교가 되고, 지도교수 요청("각각 따로 분석 후 가중평균")의 재료가 된다.

  minutes_tone(date) → {conf_weighted, confidence, n_sentences, sections: {코드: 톤}}

★회의록 특성 — 성명문(13문장)보다 **훨씬 길다**(수백 문장). 그래서
  · 저장 형식이 문단이라 split_sentences 로 문장 분해 후 점수화
  · 섹션별 톤도 함께 산출 — 어느 섹션이 톤을 만드는지 볼 수 있다
    (PVCCEO=위원 견해가 가장 감성이 강하고, CPA=정책결정은 형식적 문구가 많음)
  · 전체 톤은 **섹션 구분 없이 전 문장**을 한 번에 가중평균 (성명문 공식과 동일)

실행:  python3 analysis/minutes_index.py 2026-06-17
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MINUTES_DIR = ROOT / "data" / "minutes"
LN3 = math.log(3)               # 3클래스 최대 엔트로피(확신도 정규화)
# 분석 대상 섹션 — 표준 6섹션만(추가 섹션은 회의마다 있다 없다 해서 시계열이 안 됨)
SECTIONS = ("DFMOMO", "SRES", "SRFS", "SEO", "PVCCEO", "CPA")


def minutes_dir(date: str) -> Path:
    d = date.replace("-", "")
    return MINUTES_DIR / d[:4] / d


def has_minutes(date: str) -> bool:
    p = minutes_dir(date)
    return p.exists() and any(p.glob("*_*.txt"))


def load_sections(date: str):
    """{코드: 본문} — 표준 6섹션 중 존재하는 것만."""
    p = minutes_dir(date)
    if not p.exists():
        return {}
    out = {}
    for code in SECTIONS:
        f = p / f"{date.replace('-', '')}_{code}.txt"
        if f.exists():
            text = f.read_text(encoding="utf-8").strip()
            if text:
                out[code] = text
    return out


def _tone(sents, analyze):
    """문장 리스트 → (conf_weighted, confidence). 성명문 aggregate 공식과 동일."""
    scores, weights = [], []
    for s in sents:
        r = analyze(s)
        scores.append(r["score"])
        weights.append(max(0.0, 1.0 - r["entropy"] / LN3))
    if not weights:
        return None, None
    wsum = sum(weights) or 1.0
    return sum(sc * w for sc, w in zip(scores, weights)) / wsum, wsum / len(weights)


def minutes_tone(date: str, analyze=None):
    """회의록 → {conf_weighted, confidence, n_sentences, sections}. 없으면 None.

    analyze: 문장→{score, entropy} 스코어러. 기본은 engine.sentiment(FinBERT)로
    성명문·기자회견과 동일(비교 공정). 테스트는 가짜 스코어러 주입 가능.
    """
    secs = load_sections(date)
    if not secs:
        return None
    if analyze is None:
        from engine.sentiment import analyze
    from engine.preprocess import split_sentences

    all_sents, sec_tones = [], {}
    for code, text in secs.items():
        sents = [s for s in split_sentences(text) if s.strip()]
        if not sents:
            continue
        all_sents.extend(sents)
        cw, _ = _tone(sents, analyze)
        sec_tones[code] = {"conf_weighted": cw, "n_sentences": len(sents)}
    if not all_sents:
        return None
    cw, conf = _tone(all_sents, analyze)
    return {"conf_weighted": cw, "confidence": conf,
            "n_sentences": len(all_sents), "sections": sec_tones}


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-06-17"
    res = minutes_tone(date)
    if res is None:
        raise SystemExit(f"회의록 없음: {minutes_dir(date)}\n"
                         "먼저 engine/minutes_scrape.py 로 수집하세요.")
    print(f"{date} 회의록 톤: {res['conf_weighted']:+.4f}  "
          f"(확신도 {res['confidence']:.3f} · {res['n_sentences']}문장)")
    for code, s in res["sections"].items():
        print(f"   {code:8} {s['conf_weighted']:+.4f}  ({s['n_sentences']}문장)")
