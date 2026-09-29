"""검증 시리즈 생성 — 통합 감성지수(현재 설계) vs VIX 월별 256개월 → analysis/validation_series.json (커밋).

현재 설계 = 연준 축(성명문:기자회견:회의록 = 1:1:1, 각자 z 후 가용 성분 평균,
headline.combine_fed_axes 와 같은 파라미터) + 뉴스 축(WSJ 백본 월별)을 1:1 로 결합한다.
결합 식은 라이브 headline 과 같다: 0.5·연준 결합값 + 0.5·z(뉴스).

이전에는 연준 축이 성명문 하나이던 설계(validate_robustness.combined, r=-0.524)를 그렸다.
사이트가 실제로 내보내는 지수와 설계가 달라서 현재 설계로 바꿨다(2026-09).
표시하는 공식 상관계수는 최종보고서 확정값(meta.validation.r_combined)이고, 여기 r 은
이 시리즈로 다시 계산한 값이다 — 데이터 시점에 따라 소수 셋째 자리가 조금 다를 수 있다.

yfinance 네트워크가 필요하므로 export_dashboard 와 분리(한 번 생성해 커밋, export는 복사만).
실행: python3 analysis/build_validation_series.py
"""
import csv
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.build_headline_norm import DB, news_monthly, vix_monthly   # noqa: E402

OUT = ROOT / "analysis" / "validation_series.json"
NORM = ROOT / "analysis" / "headline_norm.json"
WIN_START, WIN_END = "2000-02-01", "2021-05-01"      # 기존 검증과 같은 256개월


def _tones(path, col):
    with open(path, encoding="utf-8") as f:
        rows = [(r["date"], r[col]) for r in csv.DictReader(f) if r.get(col)]
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in rows}, name=col)
    return s


def fed_composite_monthly(norm):
    """회의별 연준 3문서 결합(가용 성분 z 평균) → 월 그리드(직전값 이월)."""
    con = sqlite3.connect(DB)
    st = pd.read_sql("SELECT date, index_value FROM meetings "
                     "WHERE method='conf_weighted' AND granularity='meeting' ORDER BY date",
                     con, parse_dates=["date"]).set_index("date")["index_value"]
    con.close()
    parts = {
        "statement": (st, norm["fed"]),
        "minutes": (_tones(ROOT / "outputs" / "minutes_tones.csv", "minutes"), norm["minutes"]),
        "presser": (_tones(ROOT / "outputs" / "presser_tones.csv", "presser"), norm["presser"]),
    }
    z = pd.concat({k: (s - p["mean"]) / p["std"] for k, (s, p) in parts.items()}, axis=1)
    z = z.loc[z.index.isin(st.index)]                  # 회의일 = 성명문이 있는 날
    return z.mean(axis=1, skipna=True).resample("MS").last().ffill().rename("fed")


def main():
    norm = json.loads(NORM.read_text(encoding="utf-8"))
    fed, news = fed_composite_monthly(norm), news_monthly()
    lo, hi = pd.Timestamp(WIN_START), pd.Timestamp(WIN_END)
    vix = vix_monthly(lo, hi + pd.offsets.MonthEnd(1))
    df = pd.concat([fed, news, vix], axis=1).loc[lo:hi].dropna()
    comb = 0.5 * df.fed + 0.5 * (df.news - norm["news"]["mean"]) / norm["news"]["std"]
    r = float(comb.corr(df.vix))
    rows = [{"month": idx.strftime("%Y-%m"), "combined": round(float(c), 3),
             "vix": round(float(v), 2)}
            for idx, c, v in zip(df.index, comb, df.vix)]
    payload = {"r": round(r, 3), "n_months": len(rows), "design": "fed3_news_1to1",
               "period": f"{rows[0]['month']}~{rows[-1]['month']}", "series": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"검증 시리즈 {len(rows)}개월 (r={r:+.3f}) → {OUT}")


if __name__ == "__main__":
    main()
