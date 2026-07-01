"""
Phase 5 — 시장 데이터 수집 (market 테이블 채우기)

meetings 테이블의 회의 날짜를 기준으로, 그 전후 기간의
S&P500 · VIX 데이터를 yfinance로 받아 market 테이블에 적재한다.

스키마(market): date, spx_close, spx_ret_cc, vix, vix_chg, ust2y, ust10y
- 이번 단계에서는 spx_close, spx_ret_cc, vix, vix_chg 까지 채운다.
- ust2y, ust10y (국채금리)는 FRED API 키가 필요하므로 이번엔 NULL로 둔다.

실행:  python3 analysis/collect_market.py
"""

import sqlite3
import yfinance as yf
import pandas as pd

DB_PATH = "data/fomc.db"
WINDOW_DAYS = 7   # 회의일 기준 앞뒤 며칠까지 시장 데이터를 받을지 (±7일)


def get_meeting_dates(con):
    """meetings 테이블에서 서로 다른 회의 날짜만 뽑아온다.

    meetings에는 같은 회의가 집계방식(label_avg, conf_weighted)별로
    여러 줄 들어있으므로, DISTINCT 로 날짜만 유일하게 추린다.
    """
    rows = con.execute("SELECT DISTINCT date FROM meetings ORDER BY date").fetchall()
    return [r[0] for r in rows]


def fetch_market_window(center_date, window_days=WINDOW_DAYS):
    """회의일(center_date) 전후 window_days 만큼의 S&P500·VIX를 받아온다.

    yfinance 로 ^GSPC(S&P500 지수), ^VIX(변동성 지수)를 함께 내려받는다.
    반환: 날짜별 종가가 담긴 DataFrame
    """
    center = pd.to_datetime(center_date)
    # 주말·휴장을 고려해 넉넉히 받는다 (start~end, end는 미포함이라 +1일 여유)
    start = (center - pd.Timedelta(days=window_days + 3)).strftime("%Y-%m-%d")
    end = (center + pd.Timedelta(days=window_days + 3)).strftime("%Y-%m-%d")

    raw = yf.download(["^GSPC", "^VIX"], start=start, end=end, progress=False)

    # yfinance는 여러 티커를 받으면 컬럼이 (지표, 티커) 2단 구조로 온다.
    # 필요한 종가(Close)만 뽑아 정리한다.
    df = pd.DataFrame({
        "spx_close": raw["Close"]["^GSPC"],
        "vix": raw["Close"]["^VIX"],
    })
    df = df.dropna()               # 휴장일 등 빈 행 제거
    df.index = df.index.strftime("%Y-%m-%d")  # 날짜를 'YYYY-MM-DD' 문자열로
    return df


def compute_derived(df):
    """원자료(종가)로부터 파생값을 계산한다.

    - spx_ret_cc : S&P500 종가-대-종가 수익률 (전일 대비 %변화). 스키마 지정 방식.
    - vix_chg    : VIX 변화량 (전일 대비 절대 차이).
    첫 행은 '전일'이 없으므로 파생값이 NaN → None(NULL) 처리한다.
    """
    df = df.copy()
    df["spx_ret_cc"] = df["spx_close"].pct_change()   # 종가 수익률
    df["vix_chg"] = df["vix"].diff()                  # VIX 변화량
    # 국채금리는 이번 단계에서 미수집 → NULL
    df["ust2y"] = None
    df["ust10y"] = None
    return df


def upsert_market(con, df):
    """market 테이블에 적재한다. 같은 date면 덮어쓰기(멱등성 보장).

    date를 기본키로 보고 INSERT OR REPLACE 를 쓴다.
    → 스크립트를 두 번 돌려도 행이 중복되지 않는다 (프로젝트 멱등성 원칙).
    """
    cols = ["date", "spx_close", "spx_ret_cc", "vix", "vix_chg", "ust2y", "ust10y"]
    for date, row in df.iterrows():
        values = (
            date,
            _num(row["spx_close"]),
            _num(row["spx_ret_cc"]),
            _num(row["vix"]),
            _num(row["vix_chg"]),
            row["ust2y"],
            row["ust10y"],
        )
        con.execute(
            f"INSERT OR REPLACE INTO market ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})",
            values,
        )
    con.commit()


def _num(x):
    """NaN을 SQLite가 이해하는 None(NULL)으로 바꾼다."""
    return None if pd.isna(x) else float(x)


def main():
    con = sqlite3.connect(DB_PATH)

    dates = get_meeting_dates(con)
    print(f"수집 대상 회의: {dates}")

    total = 0
    for d in dates:
        print(f"\n[{d}] 전후 ±{WINDOW_DAYS}일 시장 데이터 수집 중...")
        raw = fetch_market_window(d)
        df = compute_derived(raw)
        upsert_market(con, df)
        total += len(df)
        print(f"  → {len(df)}건 적재 완료")

    # 확인: 실제로 몇 건이 들어갔는지 다시 세어본다
    n = con.execute("SELECT COUNT(*) FROM market").fetchone()[0]
    print(f"\n완료. market 테이블 총 {n}건 (이번 실행 {total}건 처리)")
    con.close()


if __name__ == "__main__":
    main()
