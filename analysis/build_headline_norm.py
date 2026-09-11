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
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomc.db"
NEWS_CSV = ROOT / "outputs" / "news_index.csv"          # WSJ 월별 — 검증용
BACKFILL_CSV = ROOT / "outputs" / "news_index_backfill_weekly.csv"   # C안 — 파라미터용
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


def news_params():
    """뉴스축 z-파라미터 — **백필 주별**에서 구한다 (C안, 조교 승인 2026-09-08).

    검증(VIX 상관)은 WSJ 백본(2000~2021 월별)으로 하지만, 실제로 표준화할
    대상은 라이브 Marketaux 일별이다. 두 모집단은 선정 규칙이 달라
    WSJ 월별 분포로 라이브 일별을 재면 척도가 2.6배 어긋난다
    (69일 중 11일이 |z|>3). 경위: docs/headline_norm_issue.md

    상관계수는 아핀변환에 불변이므로 여기서 mean/std 를 바꿔도
    validation 의 r_fed·r_news 는 달라지지 않는다.
    """
    if not BACKFILL_CSV.exists():
        raise SystemExit(
            f"{BACKFILL_CSV} 없음 — 먼저 다음을 실행하세요:\n"
            "  python analysis/news_index_backfill.py --weekly")
    w = pd.read_csv(BACKFILL_CSV)["conf_weighted"]
    return {"mean": round(float(w.mean()), 4), "std": round(float(w.std()), 4),
            "source": f"{BACKFILL_CSV.name} ({len(w)}주, 백필 주별)",
            "note": "라이브 일별 std 대비 -17% (2026-07-10~ 기준) — "
                    "docs/headline_norm_issue.md §7·§8"}


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

    nw = news_params()
    print(f"뉴스 파라미터: {nw['source']}  mean {nw['mean']:+.4f} std {nw['std']:.4f}")
    print(f"  (WSJ 월별이었다면 mean {news.mean():+.4f} std {news.std():.4f})")

    # ★기존 값을 읽어 **덮어쓰지 않고 갱신**한다.
    #   presser·minutes·fed_axis_* 는 analysis/build_fed_axis_norm.py 가 넣는데,
    #   예전엔 여기서 dict 를 통째로 써버려 그 블록들이 조용히 사라졌다.
    params = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    params.update({
        "fed": {"mean": round(float(fed.mean()), 4), "std": round(float(fed.std()), 4)},
        "news": nw,
        "w_fed": 0.5, "w_news": 0.5,
        "validation": {"period": f"{df.index.min().date()}~{df.index.max().date()}",
                       "n_months": len(df), "r_fed": round(r_fed, 3),
                       "r_news": round(r_news, 3), "r_combined": round(r_comb, 3),
                       "note": "WSJ 백본 월별로 계산한 방법 검증이다. news 의 "
                               "mean/std 출처(백필 주별)와는 모집단이 다르다 — "
                               "상관계수는 아핀변환에 불변이라 r 값은 영향받지 않는다."},
    })
    OUT.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    # Windows 기본 콘솔은 cp949 라 '✔' 에서 죽는다(쓰기 직전에 죽어 파일은 안 남는다)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
