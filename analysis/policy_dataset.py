"""금리결정 설명력 분석용 회의별 데이터셋 — 목표변수 + 누출 없는 예측자.

조교 피드백(2026-08): 금리 결정은 인상·동결·인하 **3분류**라 OLS 가 부적절하고
다항 로지스틱이 맞다. 그 분석의 재료를 만드는 모듈이다.
분석 자체는 policy_freq.py(조건부 빈도표) · policy_logit.py(회귀)가 맡는다.

★이 모듈의 존재 이유는 **시점 규칙**이다. 감성지수로 금리결정을 "설명"할 때
가장 쉬운 실수가 두 가지다:

  (1) 동시점 누출 — 성명문은 회의 당일 발표되고 본문에 결정이 **그대로 서술**된다
      ("the Committee decided to raise the target range ..."). 이 톤으로 결정을
      맞히는 건 설명이 아니라 동어반복이다.
  (2) 기준선 착각 — 최빈 클래스(Hold 66.5%)를 기준으로 삼으면 성공을 과장한다.
      연준 결정은 사이클로 움직여 **직전 결정을 그대로 반복**하기만 해도 80.5% 다.
      모델은 이 지속성 기준선을 이겨야 의미가 있다.

그래서 예측자는 **회의 t 가 열리기 전에 알 수 있는 것만** 쓴다:

  회의 t-1 의 성명문·기자회견 톤   회의 t-1 당일 공개
  회의 t-1 의 회의록 톤            t-1 의 3주 후 공개 → t 전에 도착(간격 검증함)
  뉴스 지수                        t 직전에 완결된 달
  2년물 변화                       t 직전 N거래일 (시장의 사전 기대)

동시점 값(stmt_now·minutes_now)도 함께 싣되 **비교 대조용**으로만 쓴다.
컬럼 이름에 _now 가 붙은 것은 누출이 있다는 뜻이다.

목표변수는 FRED 연방기금 목표금리 변화로 객관 측정한다(사람 라벨 불필요) —
tone_vs_policy.py 가 쓰던 것과 같은 정의(DFEDTAR ~2008 + DFEDTARU 2008~, ±0.05).

실행:  python3 analysis/policy_dataset.py          # 산출 + 요약 출력
산출:  outputs/policy_dataset.csv
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# collect_market 이 아니라 collect_macro 를 쓴다 — 전자는 임포트 시 yfinance 를
# 끌어와서 FRED 만 필요한 여기서는 불필요하게 의존성을 늘린다(미설치 환경에서 즉시 실패).
from analysis.collect_macro import fetch_series           # noqa: E402

DB = ROOT / "data" / "fomc.db"
OUT = ROOT / "outputs" / "policy_dataset.csv"
PRESSER_CSV = ROOT / "outputs" / "presser_tones.csv"
MINUTES_CSV = ROOT / "outputs" / "minutes_tones.csv"
NEWS_CSV = ROOT / "outputs" / "news_index.csv"

HOLD_BAND = 0.05        # |목표금리 변화| 이 이하면 동결 (tone_vs_policy 와 동일)
MINUTES_LAG_DAYS = 21   # 회의록 공개까지 걸리는 기간(약 3주)

# 2년물은 **두 가지 역할**을 한다 — 섞으면 안 된다.
#   사전(pre)  : 회의 전 변화 = 시장이 이미 반영한 기대 → 통제변수(예측자)
#   사후(post) : 발표 후 변화 = 조교 피드백의 "secondary outcome" → 종속변수
# 조교 피드백: 사후 창은 "다음 회의까지"처럼 길게 잡지 말고 **짧은 것부터** 본다.
D2Y_PRE_WINDOWS = (5, 20)
D2Y_POST_WINDOWS = (1, 2, 5)


def classify(chg: float) -> str:
    """목표금리 변화 → 3분류. tone_vs_policy.classify 와 같은 기준."""
    return "Cut" if chg < -HOLD_BAND else "Hike" if chg > HOLD_BAND else "Hold"


def target_rate(start: str, end: str) -> pd.Series:
    """연속 목표금리 (DFEDTAR ~2008-12 + DFEDTARU 2008-12~)."""
    parts = [s for s in (fetch_series("DFEDTAR", start, end),
                         fetch_series("DFEDTARU", start, end)) if s is not None]
    if not parts:
        raise SystemExit("목표금리 수집 실패 — FRED 접근을 확인하세요.")
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated(keep="first")]


def fed_tones() -> pd.DataFrame:
    """회의별 성명문 톤 (conf_weighted)."""
    con = sqlite3.connect(DB)
    df = pd.read_sql(
        "SELECT date, index_value AS stmt FROM meetings "
        "WHERE method='conf_weighted' AND granularity='meeting' ORDER BY date",
        con, parse_dates=["date"])
    con.close()
    if df.empty:
        raise SystemExit("meetings 가 비어있음 — 먼저 pipeline.py 를 실행하세요.")
    return df


def _axis_csv(path: Path, col: str) -> pd.Series:
    if not path.exists():
        print(f"  [경고] {path.name} 없음 — {col} 축 생략", file=sys.stderr)
        return pd.Series(dtype=float)
    d = pd.read_csv(path, parse_dates=["date"])
    return d.set_index("date")[col]


def _news_monthly() -> pd.Series:
    if not NEWS_CSV.exists():
        print("  [경고] news_index.csv 없음 — 뉴스 축 생략", file=sys.stderr)
        return pd.Series(dtype=float)
    d = pd.read_csv(NEWS_CSV, parse_dates=["month"])
    return d.set_index("month")["conf_weighted"]


def build() -> pd.DataFrame:
    t = fed_tones()
    lo = t.date.min() - pd.Timedelta(days=400)
    hi = t.date.max() + pd.Timedelta(days=10)
    s_lo, s_hi = lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")

    # ── 목표변수 ────────────────────────────────────────────────────────
    rate = target_rate(s_lo, s_hi)

    def chg(d):
        after, before = rate.asof(d + pd.Timedelta(days=2)), rate.asof(d - pd.Timedelta(days=2))
        return (after - before) if pd.notna(after) and pd.notna(before) else np.nan

    t["chg"] = t.date.apply(chg)
    t = t.dropna(subset=["chg"]).reset_index(drop=True)
    t["decision"] = t.chg.apply(classify)

    # ── 회의 간격 · 회의록 가용성 검증 ──────────────────────────────────
    # 회의록은 t-1 의 3주 후 공개 → 회의 간격이 21일보다 짧으면 t 시점에 아직 없다.
    t["gap_days"] = t.date.diff().dt.days
    t["minutes_prev_available"] = t.gap_days >= MINUTES_LAG_DAYS

    # ── 예측자 (전부 회의 t 이전 정보) ──────────────────────────────────
    presser = _axis_csv(PRESSER_CSV, "presser")
    minutes = _axis_csv(MINUTES_CSV, "minutes")
    t["presser_now"] = t.date.map(presser) if len(presser) else np.nan
    t["minutes_now"] = t.date.map(minutes) if len(minutes) else np.nan

    for src, dst in (("stmt", "stmt_prev"), ("presser_now", "presser_prev"),
                     ("minutes_now", "minutes_prev")):
        t[dst] = t[src].shift(1)
    t["prev_dec"] = t.decision.shift(1)
    # 간격이 짧아 회의록이 아직 없었을 회의는 결측 처리 (사후 정보 사용 방지)
    t.loc[~t.minutes_prev_available, "minutes_prev"] = np.nan

    # 뉴스 — 회의 직전에 '완결된' 달의 지수 (당월은 아직 안 끝났으므로 쓰지 않음)
    news = _news_monthly()
    if len(news):
        t["news_pre"] = t.date.map(
            lambda d: news.get((d.to_period("M") - 1).to_timestamp(), np.nan))
    else:
        t["news_pre"] = np.nan

    # 2년물 — 사전(통제변수) · 사후(secondary outcome)
    d2y = fetch_series("DGS2", s_lo, s_hi)
    if d2y is not None and len(d2y):
        d2y = d2y.sort_index()
        for w in D2Y_PRE_WINDOWS:
            t[f"d2y_pre{w}"] = t.date.apply(lambda d, w=w: _pre_change(d2y, d, w))
        for w in D2Y_POST_WINDOWS:
            t[f"d2y_post{w}"] = t.date.apply(lambda d, w=w: _post_change(d2y, d, w))
    return t


def _pre_change(series: pd.Series, meeting_date, win_days: int):
    """회의 '전날까지' win_days 거래일 동안의 변화. 회의 당일은 포함하지 않는다."""
    past = series[series.index < meeting_date]
    if len(past) < win_days + 1:
        return np.nan
    return float(past.iloc[-1] - past.iloc[-(win_days + 1)])


def _post_change(series: pd.Series, meeting_date, win_days: int):
    """회의 당일 종가 → win_days 거래일 뒤 종가 변화 (발표 반응).

    성명문은 미 동부 오후 2시 발표라 **당일 종가에 이미 반영**된다. 그래서 기준점을
    회의 전날 종가로 잡으면 발표 반응과 당일 장중 다른 요인이 섞인다. 여기서는
    보수적으로 '회의 당일 직전 거래일 종가 → +win_days 거래일 종가'로 잡아
    발표 당일 반응을 포함시킨다(창 1이 곧 발표 당일 반응).
    """
    base_idx = series.index.searchsorted(meeting_date, side="left")   # 회의일 직전 위치
    if base_idx == 0 or base_idx - 1 + win_days >= len(series):
        return np.nan
    return float(series.iloc[base_idx - 1 + win_days] - series.iloc[base_idx - 1])


def summarize(t: pd.DataFrame) -> None:
    print(f"\n회의 {len(t)}건  ({t.date.min().date()} ~ {t.date.max().date()})")
    vc = t.decision.value_counts()
    print("\n목표변수 분포")
    for k in ("Hike", "Hold", "Cut"):
        print(f"  {k:<5}{vc.get(k, 0):>5}건  {vc.get(k, 0) / len(t):>6.1%}")

    p = t.dropna(subset=["prev_dec"])
    print("\n기준선 — 모델은 아래를 이겨야 한다")
    print(f"  최빈 클래스(Hold)      {vc.max() / len(t):>6.1%}")
    print(f"  직전 결정 반복(지속성) {(p.decision == p.prev_dec).mean():>6.1%}   ← 진짜 기준선")

    print("\n예측자 가용성 (결측 아닌 비율)")
    for c in ("stmt_prev", "presser_prev", "minutes_prev", "news_pre",
              *[f"d2y_pre{w}" for w in D2Y_PRE_WINDOWS],
              *[f"d2y_post{w}" for w in D2Y_POST_WINDOWS]):
        if c in t.columns:
            print(f"  {c:<16}{t[c].notna().mean():>6.1%}  ({int(t[c].notna().sum())}건)")

    n_short = int((~t.minutes_prev_available.fillna(True)).sum())
    if n_short:
        print(f"\n  ※ 회의 간격 {MINUTES_LAG_DAYS}일 미만이라 직전 회의록이 아직 "
              f"없었을 회의 {n_short}건 — minutes_prev 결측 처리함")


def main():
    t = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT, index=False)
    summarize(t)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
