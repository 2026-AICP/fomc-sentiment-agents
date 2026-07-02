"""News(WSJ) 감성 인덱스 생성 (Phase 5 — News 축).

WSJ Fed·통화정책 관련 기사(연도별 CSV)를 FinBERT로 감성분석하여
월별 News Sentiment Index를 산출한다. Fed 인덱스와 동일한 방법론
(확신도 가중 + 온도 보정)을 쓴다.

데이터: WSJ 연도별 CSV (P_WSJ_YYYY.csv). 용량 때문에 git 에 없음 →
  드롭박스에서 받아 아래 경로에 둔다 (기본 data/wsj/, 또는 WSJ_DIR 로 지정).
  CSV 컬럼: date, title, abstract, full_text, ... (인코딩 latin-1, 날짜 형식 혼재)

집계 방식(월별): 세 가지를 함께 산출해 비교 (index/aggregate.py 정신).
  - mean_score          : 기사 score 단순 평균
  - share_pos_minus_neg : 긍정기사비율 - 부정기사비율 (극단값에 덜 민감)
  - conf_weighted       : 확신도(1 - 정규화 엔트로피) 가중 (★권장, 시장정합 최선)

실행:  python3 analysis/news_index.py
  → outputs/news_index.csv (또는 NEWS_OUT)

주의: 이 스크립트는 검증용 "과거 데이터" 처리다. 실시간 자동수집(뉴스 API)은
  Phase 7(Data Collector 에이전트)에서 별도 소스로 구현한다.
"""
import glob
import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WSJ_DIR = Path(os.getenv("WSJ_DIR", ROOT / "data" / "wsj"))
OUT = Path(os.getenv("NEWS_OUT", ROOT / "outputs" / "news_index.csv"))

# 감성 엔진 라벨 순서 (engine/sentiment.py 와 동일): 0=중립,1=긍정,2=부정
_NEU, _POS, _NEG = 0, 1, 2
LN3 = math.log(3)          # 3클래스 최대 엔트로피 (정규화용)
BATCH = 64
MAXLEN = 128               # 기사는 abstract 위주라 128 토큰이면 충분


def load_articles(wsj_dir: Path):
    """연도별 WSJ CSV → (날짜, 텍스트) 리스트. 인코딩·날짜형식 혼재 처리."""
    import pandas as pd
    files = sorted(glob.glob(str(wsj_dir / "P_WSJ_*.csv")))
    if not files:
        raise FileNotFoundError(
            f"WSJ 데이터를 찾을 수 없습니다: {wsj_dir}\n"
            "드롭박스에서 P_WSJ_YYYY.csv 들을 받아 이 경로에 두거나 WSJ_DIR 로 지정하세요."
        )
    frames = [pd.read_csv(f, encoding="latin-1", usecols=["date", "title", "abstract", "full_text"])
              for f in files]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["date"].notna()].copy()
    # 날짜 구분자 통일(점·하이픈 → 공백) 후 유연 파싱 (형식이 파일마다 다름)
    s = df["date"].astype(str).str.replace(".", " ", regex=False).str.replace("-", " ", regex=False).str.strip()
    df["dt"] = pd.to_datetime(s, dayfirst=True, errors="coerce", format="mixed")
    df = df[df["dt"].notna()]
    # 텍스트: abstract 우선, 없으면 title
    df["text"] = df["abstract"].where(df["abstract"].astype(str).str.len() > 20, df["title"])
    df = df[df["text"].notna() & (df["text"].astype(str).str.len() > 20)]
    return df[["dt", "text"]].reset_index(drop=True)


def score_articles(df):
    """기사별 감성 확률·score·entropy 계산 (배치 추론, 온도 보정)."""
    import pandas as pd
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

    out = df.copy()
    out["p_pos"], out["p_neu"], out["p_neg"] = p_pos, p_neu, p_neg
    out["score"] = out["p_pos"] - out["p_neg"]
    out["entropy"] = out.apply(
        lambda r: -sum(x * math.log(x) for x in (r.p_pos, r.p_neu, r.p_neg) if x > 0), axis=1)
    return out


def aggregate_monthly(art):
    """기사별 점수 → 월별 인덱스 (세 방식)."""
    import pandas as pd
    art = art.copy()
    art["month"] = pd.to_datetime(art["dt"]).dt.to_period("M").dt.to_timestamp()
    g = art.groupby("month")
    mean_score = g["score"].mean()
    pos_share = g.apply(lambda d: (d.p_pos > d.p_neg).mean())
    neg_share = g.apply(lambda d: (d.p_neg > d.p_pos).mean())
    art["w"] = (1 - art["entropy"] / LN3).clip(lower=0)
    conf_w = art.groupby("month").apply(lambda d: (d.score * d.w).sum() / max(d.w.sum(), 1e-9))
    res = pd.DataFrame({
        "month": mean_score.index,
        "mean_score": mean_score.values,
        "share_pos_minus_neg": (pos_share - neg_share).values,
        "conf_weighted": conf_w.values,
        "n_articles": g.size().values,
    })
    return res


def main():
    import sys
    sys.path.insert(0, str(ROOT))
    df = load_articles(WSJ_DIR)
    print(f"WSJ 기사 {len(df)}건 로드 ({df.dt.min().date()} ~ {df.dt.max().date()})")
    art = score_articles(df)
    monthly = aggregate_monthly(art)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(OUT, index=False)
    print(f"월별 News 인덱스 {len(monthly)}개월 → {OUT}")
    print("권장 컬럼: conf_weighted (시장정합 최선). 표준편차 "
          f"{monthly['conf_weighted'].std():.3f}")


if __name__ == "__main__":
    main()
