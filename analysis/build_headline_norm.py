"""통합(headline) z-파라미터 생성 + 검증 → analysis/headline_norm.json.

두 축을 표준화(z)해 결합했을 때 VIX 상관이 각 축 단독보다 나아짐을 재현하고,
실시간 결합(analysis/headline.py)이 쓸 z-파라미터(각 축 mean/std)를 저장한다.

입력:
  - Fed 축: data/fomc.db  meetings(method='conf_weighted') — pipeline.py 로 빌드
  - News 축: outputs/news_index.csv — analysis/news_index.py 로 빌드
  - VIX: yfinance ^VIX (월별 평균)

실행:
  python3 analysis/news_index.py        # (선행) News 인덱스 생성
  python3 analysis/build_headline_norm.py

출력: analysis/headline_norm.json (git 커밋). headline.combine 이 이 값으로 z 표준화.
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomc.db"
NEWS_CSV = ROOT / "outputs" / "news_index.csv"
OUT = ROOT / "analysis" / "headline_norm.json"


def fed_monthly():
    """회의별 Fed conf_weighted → 월 그리드(회의 없는 달은 직전값 이월 step)."""
    con = sqlite3.connect(DB)
    df = pd.read_sql(
        "SELECT date, index_value FROM meetings "
        "WHERE method='conf_weighted' AND granularity='meeting' ORDER BY date",
        con, parse_dates=["date"])
    con.close()
    if df.empty:
        raise SystemExit("meetings(conf_weighted) 비어있음 — 먼저 pipeline.py 로 DB를 빌드하세요.")
    return df.set_index("date")["index_value"].resample("MS").last().ffill().rename("fed")


def news_monthly():
    if not NEWS_CSV.exists():
        raise SystemExit(f"{NEWS_CSV} 없음 — 먼저 analysis/news_index.py 를 실행하세요.")
    n = pd.read_csv(NEWS_CSV, parse_dates=["month"])
    return n.set_index("month")["conf_weighted"].rename("news")


def vix_monthly(start, end):
    import yfinance as yf
    v = yf.download("^VIX", start=str(start.date()), end=str(end.date()),
                    progress=False, auto_adjust=False)["Close"]
    if isinstance(v, pd.DataFrame):
        v = v.iloc[:, 0]
    return v.resample("MS").mean().rename("vix")


def _z(s):
    return (s - s.mean()) / s.std()


def main():
    fed, news = fed_monthly(), news_monthly()
    lo = max(fed.index.min(), news.index.min())
    hi = min(fed.index.max(), news.index.max())
    vix = vix_monthly(lo, hi + pd.offsets.MonthEnd(1))
    df = pd.concat([fed, news, vix], axis=1).loc[lo:hi].dropna()
    fz, nz = _z(df.fed), _z(df.news)
    comb = 0.5 * fz + 0.5 * nz
    r_fed, r_news, r_comb = fz.corr(df.vix), nz.corr(df.vix), comb.corr(df.vix)

    print(f"검증 구간: {df.index.min().date()} ~ {df.index.max().date()} ({len(df)}개월)")
    print(f"VIX 상관:  Fed {r_fed:+.3f} | News {r_news:+.3f} | 통합 {r_comb:+.3f}"
          f"  ({'통합 개선✔' if abs(r_comb) > max(abs(r_fed), abs(r_news)) else '통합 미개선'})")

    params = {
        "fed": {"mean": round(float(fed.mean()), 4), "std": round(float(fed.std()), 4)},
        "news": {"mean": round(float(news.mean()), 4), "std": round(float(news.std()), 4)},
        "w_fed": 0.5, "w_news": 0.5,
        "validation": {"period": f"{df.index.min().date()}~{df.index.max().date()}",
                       "n_months": len(df), "r_fed": round(r_fed, 3),
                       "r_news": round(r_news, 3), "r_combined": round(r_comb, 3)},
    }
    OUT.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
