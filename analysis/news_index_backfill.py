"""백필(2021-01~2026-06) 뉴스 → 감성 지수. 대시보드 뉴스축을 5.5년으로 확장.

라이브(analysis/news_index_live.py)와 **같은 함수를 그대로 재사용**한다 —
로더·스코어러·일별 집계·부트스트랩 CI 전부. 백필과 라이브는 선정 규칙도 같으므로
(둘 다 Marketaux 본문 F → 제목+설명 F∧M) 두 구간은 이어 붙일 수 있다.
  ※ WSJ 백본(2000~2021)은 규칙이 다르다 — docs/scope_impact.md 참조. 여기 안 섞는다.

★왜 별도 파일인가 — 매일 재채점을 피하려고.
  라이브 파이프라인은 매 실행마다 fed_news.csv 전체를 다시 채점한다. 백필을
  fed_news.csv 에 합치면 24,500건을 매일 다시 돌려 러너에서 7분씩 쓴다.
  백필 구간은 더 늘지 않으므로 **한 번 채점해 CSV 로 굳히고**, 대시보드 내보내기가
  라이브 결과와 이어 붙이면 된다. 일일 작업량은 지금과 똑같이 유지된다.

★기사별 점수를 캐시하는 이유: 집계 단위(일/주/월)를 바꿔 볼 때 FinBERT 를
  다시 돌리지 않기 위해서다. 백필 일별은 중앙값 7건이라 신뢰도 하한(15건)을
  73% 의 날이 못 넘는다 — 어떤 단위로 낼지는 별도 결정 사항이다.

실행:
  python3 analysis/news_index_backfill.py            # 일별
  python3 analysis/news_index_backfill.py --weekly   # 주별
  python3 analysis/news_index_backfill.py --monthly  # 월별
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.news_index import score_articles          # 검증된 FinBERT 배치 스코어러
from analysis.news_index_live import load_live_news, aggregate_daily, LN3, _boot_ci, _weighted

IN = ROOT / "data" / "news" / "fed_news_backfill.csv"
OUT = ROOT / "outputs" / "news_index_backfill.csv"
# 기사별 채점 캐시 — 집계 단위를 바꿔도 재채점하지 않는다(CPU 약 7분).
CACHE = ROOT / "outputs" / "news_backfill_scored.csv"


def scored(csv_path=IN, cache=CACHE):
    """기사별 점수 — 캐시가 있으면 읽고, 없으면 채점 후 저장."""
    import pandas as pd
    cache = Path(cache)
    if cache.exists():
        print(f"채점 캐시 사용: {cache.name}")
        return pd.read_csv(cache, parse_dates=["dt"])
    df = load_live_news(csv_path)
    print(f"백필 기사 {len(df):,}건 로드 ({df.dt.min().date()} ~ {df.dt.max().date()})")
    art = score_articles(df)
    cache.parent.mkdir(parents=True, exist_ok=True)
    art.to_csv(cache, index=False)
    print(f"채점 캐시 저장 → {cache.name}")
    return art


def aggregate_period(art, freq):
    """주/월 단위 집계 — aggregate_daily 와 같은 정의(확신도 가중 + 부트스트랩 CI).

    일별은 백필 구간에서 중앙값 7건이라 신뢰구간이 지나치게 넓다. 더 굵은 단위로
    묶으면 표본이 두꺼워져(주 62건·월 348건) 게이트를 넘긴다.
    """
    import pandas as pd
    a = art.copy()
    a["dt"] = pd.to_datetime(a["dt"])
    a["w"] = (1 - a["entropy"] / LN3).clip(lower=0)
    # 구간의 시작일을 대표 날짜로 삼는다(차트 x축이 단조 증가하도록)
    a["bucket"] = a["dt"].dt.to_period(freq).dt.start_time.dt.date
    rows = []
    for b, d in a.groupby("bucket"):
        s, w = d["score"].to_numpy(), d["w"].to_numpy()
        lo, hi = _boot_ci(s, w)
        rows.append({
            "date": str(b),
            "n_articles": int(len(d)),
            "mean_score": float(d["score"].mean()),
            "share_pos_minus_neg": float((d.p_pos > d.p_neg).mean() - (d.p_neg > d.p_pos).mean()),
            "conf_weighted": _weighted(s, w),
            "ci_lo": lo, "ci_hi": hi,
            "confidence": float(w.mean()),
        })
    return pd.DataFrame(rows)


def main():
    argv = sys.argv[1:]
    art = scored()
    if "--weekly" in argv:
        out, idx = ROOT / "outputs" / "news_index_backfill_weekly.csv", aggregate_period(art, "W")
        unit = "주"
    elif "--monthly" in argv:
        out, idx = ROOT / "outputs" / "news_index_backfill_monthly.csv", aggregate_period(art, "M")
        unit = "월"
    else:
        out, idx = OUT, aggregate_daily(art)
        unit = "일"
    out.parent.mkdir(parents=True, exist_ok=True)
    idx.to_csv(out, index=False)
    n = idx["n_articles"]
    print(f"\n{unit}별 지수 {len(idx):,}구간 → {out.name}")
    print(f"  기사수  중앙 {n.median():.0f}  평균 {n.mean():.1f}  최소 {n.min()}")
    print(f"  15건 미만 구간: {(n < 15).sum()}/{len(n)} ({(n < 15).mean():.0%})")
    print(f"  지수  평균 {idx['conf_weighted'].mean():+.4f}  표준편차 {idx['conf_weighted'].std():.4f}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
