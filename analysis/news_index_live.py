"""News 지수 (실시간·일별) — 스크랩한 fed_news.csv 로부터 산출.

analysis/news_index.py(과거 WSJ·월별, 검증용)와 **방법론을 공유**하되:
  · 입력: 실시간 스크랩본(engine/news_scrape.py → data/news/fed_news.csv)
  · 집계: '일별'(운영용 — 매일 갱신)
  · 텍스트: description 우선(짧으면 title). ← 3방식 비교에서 확신도 최고(가장 깨끗).
    title 혼합/단독은 확신도를 떨어뜨려 폐기(헤드라인이 극단·오해 유발).
스코어러(FinBERT 배치·온도보정 T=3.1)는 검증된 news_index.score_articles 재사용.

★신뢰 표시(부트스트랩 신뢰구간):
  '오늘 값을 얼마나 믿나'는 per-article 확신도가 아니라, 그날 기사 수(N)로 만든
  신뢰구간으로 표시한다. 그날 기사들을 복원추출(2000회)해 지수를 다시 계산 →
  2.5/97.5 퍼센타일 = 95% CI. 기사가 많을수록 좁아짐(=신뢰↑). n<2 는 계산 불가.
  결정적(seed 고정) → 재현 가능.

산출: outputs/news_index_live.csv
      (date, n_articles, mean_score, share_pos_minus_neg, conf_weighted,
       ci_lo, ci_hi, confidence)

실행:  python3 analysis/news_index_live.py                 # 기본 CSV
       python3 analysis/news_index_live.py <fed_news.csv>  # 경로 지정
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.news_index import score_articles   # 검증된 FinBERT 배치 스코어러 재사용

IN = ROOT / "data" / "news" / "fed_news.csv"
OUT = ROOT / "outputs" / "news_index_live.csv"
LN3 = math.log(3)               # 3클래스 최대 엔트로피(확신도 정규화용)
NAN = float("nan")


def _weighted(scores, weights):
    """확신도 가중 평균 (분모 0 방지 → 단순평균 대체)."""
    import numpy as np
    s, w = np.asarray(scores, float), np.asarray(weights, float)
    denom = w.sum()
    return float((s * w).sum() / denom) if denom > 1e-9 else float(s.mean())


def _boot_ci(scores, weights, B=2000, level=95, seed=0):
    """확신도가중 지수의 부트스트랩 신뢰구간 (n<2 → NaN). 결정적(seed 고정)."""
    import numpy as np
    n = len(scores)
    if n < 2:
        return (NAN, NAN)
    s, w = np.asarray(scores, float), np.asarray(weights, float)
    idx = np.random.default_rng(seed).integers(0, n, size=(B, n))
    ss, ws = s[idx], w[idx]
    denom = ws.sum(1)
    cw = np.where(denom > 1e-9, (ss * ws).sum(1) / np.where(denom > 1e-9, denom, 1.0), ss.mean(1))
    a = (100 - level) / 2
    lo, hi = np.percentile(cw, [a, 100 - a])
    return (float(lo), float(hi))


def load_live_news(csv_path):
    """스크랩 CSV → DataFrame[dt, text].

    dt: published_at(전체 타임스탬프, 시각 포함) 우선 → 없으면 date(일자)로 폴백(구 CSV 호환).
        UTC 기준 tz-naive 로 통일(일별 집계·회의 윈도우 비교와 호환). ← 2d 시간대 정밀화
    text: description(20자 이하면 title).
    """
    import pandas as pd
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df = df[df["date"].notna()].copy()
    if "published_at" in df.columns:                        # 시각 있으면 우선, 없으면 date
        pub = df["published_at"].fillna("").astype(str)
        raw = pub.where(pub.str.len() >= 10, df["date"].astype(str))
    else:
        raw = df["date"].astype(str)
    # format="ISO8601": date-only('2026-06-17')와 시각포함('...T14:05:00Z')이 섞여도
    # 각각 파싱(미지정 시 pandas 2.x가 첫 행 포맷을 강제해 date-only 를 NaT로 버림).
    df["dt"] = pd.to_datetime(raw, errors="coerce", utc=True,
                              format="ISO8601").dt.tz_localize(None)
    df = df[df["dt"].notna()]
    desc = df["description"].fillna("").astype(str)
    title = df["title"].fillna("").astype(str)
    df["text"] = desc.where(desc.str.len() > 20, title)     # 검증 방식(B)
    df = df[df["text"].str.len() > 0]
    return df[["dt", "text"]].reset_index(drop=True)


def aggregate_daily(art):
    """기사별 점수 → 일별 지수(3방식 + 확신도 + 부트스트랩 95% CI)."""
    import pandas as pd
    art = art.copy()
    art["day"] = pd.to_datetime(art["dt"]).dt.date
    art["w"] = (1 - art["entropy"] / LN3).clip(lower=0)     # 확신도 = 1 - 정규화 엔트로피
    rows = []
    for day, d in art.groupby("day"):
        s, w = d["score"].to_numpy(), d["w"].to_numpy()
        lo, hi = _boot_ci(s, w)
        rows.append({
            "date": str(day),
            "n_articles": len(d),
            "mean_score": float(s.mean()),
            "share_pos_minus_neg": float((d.p_pos > d.p_neg).mean() - (d.p_neg > d.p_pos).mean()),
            "conf_weighted": _weighted(s, w),
            "ci_lo": lo, "ci_hi": hi,
            "confidence": float(w.mean()),
        })
    return pd.DataFrame(rows)


def build_live_index(csv_path=IN, out=OUT, return_articles=False):
    """스크랩 CSV → 일별 News 지수 DataFrame(및 CSV 저장). 에이전트/보고서에서 import 가능."""
    df = load_live_news(csv_path)
    art = score_articles(df)
    daily = aggregate_daily(art)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out, index=False)
    return (daily, art) if return_articles else daily


def index_for_window(csv_path=IN, center=None, before=3, after=1):
    """center 날짜 전후 [center-before, center+after] 뉴스로 News 지수 산출.

    발표일에 그 회의 주변 뉴스만 모아 지수를 내기 위함. center=None 이면 전체.
    기사가 없으면 None(예: 과거 회의 — 실시간 뉴스 없음) → 통합 시 Fed-only 로 폴백.
    반환: {conf_weighted, ci_lo, ci_hi, n_articles} 또는 None.
    """
    import pandas as pd
    df = load_live_news(csv_path)
    if center is not None:
        c = pd.to_datetime(center)
        lo, hi = c - pd.Timedelta(days=before), c + pd.Timedelta(days=after)
        df = df[(df["dt"] >= lo) & (df["dt"] <= hi)]
    if len(df) == 0:
        return None
    art = score_articles(df).copy()
    art["w"] = (1 - art["entropy"] / LN3).clip(lower=0)
    s, w = art["score"].to_numpy(), art["w"].to_numpy()
    lo_ci, hi_ci = _boot_ci(s, w)
    return {"conf_weighted": _weighted(s, w), "ci_lo": lo_ci,
            "ci_hi": hi_ci, "n_articles": int(len(art))}


def main():
    import numpy as np
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else IN
    if not Path(csv_path).exists():
        raise SystemExit(f"뉴스 CSV가 없습니다: {csv_path}\n"
                         "먼저 engine/news_scrape.py 로 수집하세요.")
    daily, art = build_live_index(csv_path, return_articles=True)

    print(f"일별 News 지수 {len(daily)}일 → {OUT}\n── 날짜별 (지수 ± 95% CI) ──")
    for _, r in daily.iterrows():
        n = int(r["n_articles"])
        band = (f"(95% CI {r['ci_lo']:+.3f} ~ {r['ci_hi']:+.3f})"
                if n >= 2 and not math.isnan(r["ci_lo"]) else "(CI 계산불가: n=1)")
        print(f"  {r['date']}  지수 {r['conf_weighted']:+.3f}  {band}  | 기사 {n}건")

    # 양이 늘면 CI가 좁아짐 — 최근 전체를 한 창으로 pooling 해 시연 + 필요 표본 추정
    art = art.copy()
    art["w"] = (1 - art["entropy"] / LN3).clip(lower=0)
    s, w = art["score"].to_numpy(), art["w"].to_numpy()
    cw = _weighted(s, w)
    lo, hi = _boot_ci(s, w)
    print(f"\n── 참고: 최근 {len(art)}건 전체를 한 창으로 (양↑ → CI↓) ──")
    print(f"  지수 {cw:+.3f}  (95% CI {lo:+.3f} ~ {hi:+.3f})  | 기사 {len(art)}건")
    if len(s) >= 2:
        sd = float(np.std(s, ddof=1))
        need = int(math.ceil((1.96 * sd / 0.05) ** 2)) if sd > 0 else 0
        print(f"  → ±0.05 수준(포스터용)까지 좁히려면 하루 약 {need}건 필요 "
              f"(현재 표본표준편차 {sd:.3f} 기준).")
    print("\n※ per-article '확신도'는 내부 가중치일 뿐 — 신뢰 표시는 위 CI로. 신뢰는 '양'에서.")


if __name__ == "__main__":
    main()
