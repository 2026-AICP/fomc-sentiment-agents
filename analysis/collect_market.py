"""
Phase 5 — 시장 데이터 수집 (market 테이블 채우기) · 개선판

meetings 테이블의 회의 날짜들을 기준으로, 전체 기간의
S&P500 · VIX 데이터를 yfinance로 "한 번에" 받아 market 테이블에 적재한다.

스키마(market): date, spx_close, spx_ret_cc, vix, vix_chg, ust2y, ust10y
- 이번 단계에서는 spx_close, spx_ret_cc, vix, vix_chg 까지 채운다.
- ust2y, ust10y (국채금리)는 FRED API 키가 필요하므로 이번엔 NULL로 둔다.

[리뷰 피드백 반영]
 (1) 회의마다 따로 호출(N번) -> 전체 기간 1회 다운로드 (느림·차단 방지)
 (2) 수익률을 "전역 연속 시계열"에서 계산 -> 창마다 NULL 반복 생기는 것 방지
 (3) 다운로드 실패 대비 try/except (한 번 실패로 전체가 죽지 않게)
 (4) 단위 통일: spx_ret_cc 는 % 단위(예: 0.61 = 0.61%). RETURN_AS_PCT=True
 (5) yf.download 에 auto_adjust=True 명시 (버전 무관 일관된 결과)

실행:  python3 analysis/collect_market.py
"""

import sqlite3
import sys
import yfinance as yf
import pandas as pd

DB_PATH = "data/fomc.db"
WINDOW_DAYS = 7        # 회의일 기준 앞뒤 며칠까지 시장 데이터를 담을지 (+-7일)
PAD_DAYS = 5          # 전체 다운로드 구간 양끝 여유 (주말·휴장 대비)

# (4) 단위 정책: % 단위로 저장(예: 0.61 = 0.61%).
#    소수 비율(0.0061)로 되돌리려면 아래를 False 로만 바꾸면 된다.
RETURN_AS_PCT = True


def get_meeting_dates(con):
    """meetings 테이블에서 서로 다른 회의 날짜만 뽑아온다.

    meetings에는 같은 회의가 집계방식(label_avg, conf_weighted)별로
    여러 줄 들어있으므로, DISTINCT 로 날짜만 유일하게 추린다.
    """
    rows = con.execute("SELECT DISTINCT date FROM meetings ORDER BY date").fetchall()
    return [r[0] for r in rows]


def download_full_range(dates):
    """(1) 전체 기간을 '한 번에' 받는다.

    가장 이른 회의 ~ 가장 늦은 회의까지의 구간을 양끝에 여유를 두고
    딱 1회 다운로드한다. 회의가 N개여도 호출은 1번뿐 -> 빠르고 차단 위험 없음.

    (3) 실패하면 예외를 잡아 명확한 메시지와 함께 중단한다.
    (5) auto_adjust=True 명시.
    """
    start = (pd.to_datetime(min(dates)) - pd.Timedelta(days=WINDOW_DAYS + PAD_DAYS)).strftime("%Y-%m-%d")
    end = (pd.to_datetime(max(dates)) + pd.Timedelta(days=WINDOW_DAYS + PAD_DAYS)).strftime("%Y-%m-%d")
    print(f"전체 다운로드 구간: {start} ~ {end} (yfinance 1회 호출)")

    try:
        raw = yf.download(
            ["^GSPC", "^VIX"],
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,   # (5) 버전 무관 일관성
        )
    except Exception as e:
        print(f"[오류] yfinance 다운로드 실패: {e}", file=sys.stderr)
        raise

    if raw is None or raw.empty:
        raise RuntimeError("yfinance가 빈 데이터를 반환했습니다. 네트워크/티커/기간을 확인하세요.")

    # 여러 티커를 받으면 컬럼이 (지표, 티커) 2단 구조. 필요한 종가(Close)만 정리.
    df = pd.DataFrame({
        "spx_close": raw["Close"]["^GSPC"],
        "vix": raw["Close"]["^VIX"],
    }).dropna()
    return df


def compute_derived_global(df):
    """(2) 파생값을 '전역 연속 시계열'에서 계산한다.

    전체 기간을 이어붙인 상태로 pct_change / diff 를 하므로,
    NULL 은 진짜 맨 첫 거래일 딱 하나에만 생긴다(회의마다 반복되지 않음).

    - spx_ret_cc : 종가-대-종가 수익률 (close-to-close). 스키마 지정 방식.
    - vix_chg    : VIX 전일 대비 변화량.
    """
    df = df.sort_index().copy()
    ret = df["spx_close"].pct_change()          # 소수 비율 (예: 0.006)
    if RETURN_AS_PCT:                            # (4) % 단위면 x100
        ret = ret * 100.0
    df["spx_ret_cc"] = ret
    df["vix_chg"] = df["vix"].diff()
    df["ust2y"] = None                           # 국채금리는 이번 단계 미수집
    df["ust10y"] = None
    return df


def slice_windows(df, dates):
    """각 회의일 전후 +-WINDOW_DAYS 를 잘라 하나로 합친다.

    파생값은 이미 전역에서 계산됐으므로 여기선 '자르기'만 한다.
    여러 회의 창이 겹치면 같은 날짜가 중복될 수 있어 마지막에 중복 제거.
    """
    idx = pd.to_datetime(df.index)
    keep = pd.Series(False, index=df.index)
    for d in dates:
        c = pd.to_datetime(d)
        lo, hi = c - pd.Timedelta(days=WINDOW_DAYS), c + pd.Timedelta(days=WINDOW_DAYS)
        keep = keep | ((idx >= lo) & (idx <= hi))
    out = df[keep.values].copy()
    out = out[~out.index.duplicated(keep="first")]  # 창 겹침 대비 중복 제거
    return out


def upsert_market(con, df):
    """market 테이블에 적재. 같은 date면 덮어쓰기(멱등성 보장).

    date를 키로 INSERT OR REPLACE -> 몇 번을 돌려도 중복 행이 안 쌓인다.
    """
    cols = ["date", "spx_close", "spx_ret_cc", "vix", "vix_chg", "ust2y", "ust10y"]
    for ts, row in df.iterrows():
        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
        values = (
            date_str,
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
    if not dates:
        print("meetings 테이블에 회의 날짜가 없습니다. 먼저 Phase 4 결과를 확인하세요.")
        con.close()
        return
    print(f"수집 대상 회의({len(dates)}건): {dates}")

    full = download_full_range(dates)      # (1) 1회 다운로드
    full = compute_derived_global(full)    # (2) 전역에서 파생값 계산
    windowed = slice_windows(full, dates)  # 회의별 +-N일만 잘라내기

    upsert_market(con, windowed)

    unit = "%" if RETURN_AS_PCT else "소수비율"
    n = con.execute("SELECT COUNT(*) FROM market").fetchone()[0]
    print(f"\n완료. market 테이블 총 {n}건 (이번 실행 {len(windowed)}건 적재, 수익률 단위={unit})")
    con.close()


if __name__ == "__main__":
    main()