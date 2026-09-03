"""선정 범위 불일치가 News 지수에 얼마나 영향을 주는가 (C안 영향 측정).

배경: 백본(WSJ)과 라이브(Marketaux)는 같은 F∧M 키워드를 쓰지만 적용 범위가 다르다.
  · WSJ 백본   ProQuest 본문에서 F∧M 매칭 → 재필터 없이 전량 사용
  · 라이브·백필 Marketaux 본문에서 F 매칭 → **제목+설명**으로 F∧M 다시 거름
C안(현행 유지)을 택하면 이 차이가 남는다. "얼마나 영향을 주는지"를 재는 것이 이 스크립트다.

방법: 같은 WSJ 기사를 **한 번만** FinBERT 로 채점하고, 월별 집계만 두 가지로 한다.
  현행   전량 집계                       (지금 outputs/news_index.csv)
  라이브 is_relevant(title, abstract) 통과분만 집계
채점을 한 번만 하므로 두 계열의 차이는 오직 '어떤 기사를 세느냐'에서만 온다 —
모델·파라미터는 건드리지 않는다(지도교수 검증 완료 사항).

abstract 를 description 자리에 놓는 이유: Marketaux 의 description 은 기사 요약문이고
WSJ CSV 의 abstract 도 같은 성격의 요약문이라, 라이브 규칙이 보는 텍스트에 대응한다.

실행:  python3 analysis/scope_impact.py
  → outputs/scope_impact.csv        (월별 두 계열 나란히)
  → 콘솔에 요약 통계
"""
import glob
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WSJ_DIR = Path(os.getenv("WSJ_DIR", ROOT / "data" / "wsj"))
OUT = Path(os.getenv("SCOPE_OUT", ROOT / "outputs" / "scope_impact.csv"))
# 기사별 채점 캐시 — 집계만 다시 볼 때 FinBERT 재실행(CPU 10여 분)을 피한다.
CACHE = Path(os.getenv("SCOPE_CACHE", ROOT / "outputs" / "scope_scored.csv"))

_NEU, _POS, _NEG = 0, 1, 2
LN3 = math.log(3)
BATCH = 64
MAXLEN = 128          # analysis/news_index.py 와 동일하게 맞춘다


def load_articles(wsj_dir: Path):
    """WSJ 연도별 CSV → 기사 표. news_index.load_articles 와 같은 규칙에
    title·abstract 두 칸을 추가로 보존한다(라이브 규칙 적용에 필요)."""
    import pandas as pd
    files = sorted(glob.glob(str(wsj_dir / "P_WSJ_*.csv")))
    if not files:
        raise FileNotFoundError(f"WSJ 데이터를 찾을 수 없습니다: {wsj_dir}")
    frames = [pd.read_csv(f, encoding="latin-1",
                          usecols=["date", "title", "abstract", "full_text"])
              for f in files]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["date"].notna()].copy()
    s = (df["date"].astype(str)
         .str.replace(".", " ", regex=False)
         .str.replace("-", " ", regex=False).str.strip())
    df["dt"] = pd.to_datetime(s, dayfirst=True, errors="coerce", format="mixed")
    df = df[df["dt"].notna()]
    df["text"] = df["abstract"].where(
        df["abstract"].astype(str).str.len() > 20, df["title"])
    df = df[df["text"].notna() & (df["text"].astype(str).str.len() > 20)]
    return df[["dt", "title", "abstract", "text"]].reset_index(drop=True)


def score_articles(df):
    """기사별 감성 확률·score·entropy (배치 추론). news_index.py 와 동일."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from engine.sentiment import MODEL_DIR, TEMPERATURE

    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    model.eval()

    texts = df["text"].astype(str).tolist()
    p_pos, p_neu, p_neg = [], [], []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH):
            enc = tok(texts[i:i + BATCH], return_tensors="pt",
                      truncation=True, max_length=MAXLEN, padding=True)
            probs = torch.softmax(model(**enc).logits / TEMPERATURE, dim=-1)
            p_pos += probs[:, _POS].tolist()
            p_neu += probs[:, _NEU].tolist()
            p_neg += probs[:, _NEG].tolist()
            if (i // BATCH) % 50 == 0:
                print(f"  채점 {min(i + BATCH, len(texts)):,}/{len(texts):,}", flush=True)

    out = df.copy()
    out["p_pos"], out["p_neu"], out["p_neg"] = p_pos, p_neu, p_neg
    out["score"] = out["p_pos"] - out["p_neg"]
    out["entropy"] = out.apply(
        lambda r: -sum(x * math.log(x) for x in (r.p_pos, r.p_neu, r.p_neg) if x > 0),
        axis=1)
    out["w"] = (1 - out["entropy"] / LN3).clip(lower=0)
    return out


def monthly(art):
    """월별 conf_weighted 지수 + 기사 수. news_index.aggregate_monthly 와 같은 값.

    확신도 가중평균 = Σ(score·w) / Σw 를 groupby 두 번의 합으로 계산한다.
    news_index.py 는 groupby.apply 로 같은 식을 쓰는데, pandas 버전에 따라
    apply 의 인자 처리(include_groups)가 달라 깨진다. 합으로 쓰면 그 의존이 없다.
    """
    import pandas as pd
    a = art.copy()
    a["month"] = pd.to_datetime(a["dt"]).dt.to_period("M").dt.to_timestamp()
    a["sw"] = a["score"] * a["w"]
    g = a.groupby("month")
    cw = g["sw"].sum() / g["w"].sum().clip(lower=1e-9)
    return pd.DataFrame({"month": cw.index, "conf_weighted": cw.values,
                         "n_articles": g.size().values}).set_index("month")


def main():
    import numpy as np
    import pandas as pd
    from engine.news_scrape import is_relevant

    df = load_articles(WSJ_DIR)
    print(f"WSJ 기사 {len(df):,}건 로드 ({df.dt.min().date()} ~ {df.dt.max().date()})")

    # 라이브 규칙 = 제목+설명(abstract)에 F그룹 AND M그룹
    df["live_pass"] = [is_relevant(t, a) for t, a in
                       zip(df["title"].fillna(""), df["abstract"].fillna(""))]
    n_pass = int(df["live_pass"].sum())
    print(f"라이브 규칙 통과 {n_pass:,}건 ({n_pass / len(df):.1%})\n")

    # 채점은 CPU 로 10여 분 걸린다. 집계만 고쳐 다시 볼 일이 많으므로 캐시해 둔다.
    # (라벨·온도가 바뀌면 캐시를 지우고 다시 돌려야 한다.)
    if CACHE.exists():
        art = pd.read_csv(CACHE, parse_dates=["dt"])
        print(f"채점 캐시 사용: {CACHE.name} ({len(art):,}건)")
    else:
        art = score_articles(df)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        art[["dt", "live_pass", "score", "entropy", "w"]].to_csv(CACHE, index=False)
        print(f"채점 캐시 저장 → {CACHE.name}")

    cur = monthly(art)
    liv = monthly(art[art["live_pass"]])
    j = cur.join(liv, how="left", lsuffix="_cur", rsuffix="_live")
    j["diff"] = j["conf_weighted_live"] - j["conf_weighted_cur"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    j.reset_index().to_csv(OUT, index=False)

    both = j.dropna(subset=["conf_weighted_live"])
    r = both["conf_weighted_cur"].corr(both["conf_weighted_live"])
    # 방향 불일치: 두 계열의 전월 대비 변화 부호가 다른 달
    d_cur = both["conf_weighted_cur"].diff()
    d_liv = both["conf_weighted_live"].diff()
    m = d_cur.notna() & d_liv.notna()
    disagree = float((np.sign(d_cur[m]) != np.sign(d_liv[m])).mean())
    # 수준 부호 불일치: 한쪽은 긍정인데 다른 쪽은 부정인 달
    lvl = float((np.sign(both["conf_weighted_cur"]) !=
                 np.sign(both["conf_weighted_live"])).mean())

    print(f"\n{'─' * 58}\n선정 범위가 지수에 주는 영향 (WSJ 백본 {len(cur)}개월)\n{'─' * 58}")
    print(f"라이브 규칙으로 지수를 낼 수 없는 달(기사 0건): "
          f"{int(j['conf_weighted_live'].isna().sum())}개월")
    print(f"두 계열 상관계수                r = {r:+.3f}")
    print(f"수준 평균   현행 {both['conf_weighted_cur'].mean():+.4f}"
          f"   라이브규칙 {both['conf_weighted_live'].mean():+.4f}"
          f"   차이 {both['diff'].mean():+.4f}")
    print(f"수준 표준편차 현행 {both['conf_weighted_cur'].std():.4f}"
          f"   라이브규칙 {both['conf_weighted_live'].std():.4f}")
    print(f"월별 차이  평균절대 {both['diff'].abs().mean():.4f}"
          f"   최대 {both['diff'].abs().max():.4f}"
          f"   표준편차 {both['diff'].std():.4f}")
    print(f"전월대비 변화 방향이 어긋난 달   {disagree:.1%}")
    print(f"수준 부호(긍/부)가 어긋난 달     {lvl:.1%}")
    print(f"\n기사 수  월평균  현행 {cur['n_articles'].mean():.0f}건"
          f"  →  라이브규칙 {liv['n_articles'].mean():.0f}건")
    print(f"        월최소  현행 {cur['n_articles'].min()}건"
          f"  →  라이브규칙 {liv['n_articles'].min()}건")
    floor = 15   # news_signals.Thresholds 신뢰도 하한
    print(f"  월 {floor}건 미만 비율  현행 "
          f"{(cur['n_articles'] < floor).mean():.1%}"
          f"  →  라이브규칙 {(liv['n_articles'] < floor).mean():.1%}"
          f"  (전체 {len(cur)}개월 기준)")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
