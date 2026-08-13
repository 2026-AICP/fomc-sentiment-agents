"""FRED 거시지표 수집 → outputs/macro_monthly.csv (통합 가중치 검증용).

설계: `docs/superpowers/specs/2026-08-09-vix-replacement-indicators-design.md`

지도교수 피드백으로 VIX 사용이 보류되면서, headline.py 의 50:50 결합을 뒷받침하던
유일한 근거(VIX 상관 -0.534)가 비었다. 그 자리를 대신할 경제지표 패널을 모은다.

지표 선정 기준은 **연준의 목표와 도구**다:
  목표 — 물가안정(T5YIE·MICH) · 고용(UNRATE) · 경제성장(INDPRO)
  도구 — 금리(DGS2·DFF, 강) · QE/QT(WALCL, 강)
  대조군 — 금융상황(NFCI). VIX 가 있던 '시장 상태' 자리.
약한 도구(공개시장조작·지급준비율·신용조정)는 제외했다 — 사유는 설계문서 §3-2 참조.
요약하면 역레포는 대부분 값이 0, 지급준비율은 2020-03 폐지(0%), 신용조정은
위기 때만 활성화돼 연속 시계열이 아니다. 상관 분석이 성립하지 않는다.

이 모듈은 **수집·정렬만** 한다. 상관·판정은 analysis/validate_weights.py 담당.
지표가 늘어도 분석 쪽은 바뀌지 않도록 경계를 나눴다.

★FRED 공개 CSV 는 API 키가 필요 없다. 크롤링이 아니라 공개 데이터 파일 다운로드다.
※ collect_market.py 에도 비슷한 _fetch_fred 가 있으나 그 모듈은 임포트 시점에
   yfinance 를 끌어온다. FRED 만 쓰는 여기서 그걸 딸려오게 할 이유가 없고, 매일 도는
   자동화 파일을 건드리는 위험도 피한다. (공용 fred 모듈로 합치는 건 후속 과제)

실행:
  python3 analysis/collect_macro.py                    # 1999-12 ~ 오늘
  python3 analysis/collect_macro.py 1999-12-01 2021-05-31
"""
import io
import os
import sys
from collections import namedtuple
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "macro_monthly.csv"
# 원본 CSV 캐시 (outputs/ 는 gitignore 대상 — 생성물이라 커밋하지 않는다)
CACHE_DIR = Path(os.getenv("FRED_CACHE_DIR", ROOT / "outputs" / "fred_cache"))

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}&coed={end}"
HEADERS = {"User-Agent": "Mozilla/5.0 (AICP FOMC research)"}

# 기본 시작이 1999-12 인 이유: 검증 구간이 2000-02~ 인데 변화(diff)를 쓰려면
# 한 달 앞 값이 있어야 첫 달 변화가 결측이 되지 않는다.
DEFAULT_START = "1999-12-01"

# transform: 변화 컬럼(_chg)을 만드는 방식
#   "diff"    — 단순 차분 (%p 단위 계열: 금리·실업률·기대인플레)
#   "logdiff" — 로그 차분 (지수·잔액처럼 추세가 강하고 양수인 계열)
# use_level: 수준(level) 상관을 결과표에 실을지. 추세 계열은 허위상관이라 False.
Macro = namedtuple("Macro", "id label group transform use_level")

SERIES = (
    Macro("T5YIE",  "5년 기대인플레이션",     "목표·물가", "diff",    True),
    Macro("MICH",   "미시간 1년 기대인플레",  "목표·물가", "diff",    True),
    Macro("UNRATE", "실업률",                 "목표·고용", "diff",    True),
    Macro("INDPRO", "산업생산지수",           "목표·성장", "logdiff", False),
    Macro("DGS2",   "2년물 국채금리",         "도구·금리", "diff",    True),
    Macro("DFF",    "실효 연방기금금리",      "도구·금리", "diff",    True),
    Macro("WALCL",  "연준 총자산",            "도구·QE",   "logdiff", False),
    Macro("NFCI",   "시카고연은 금융상황",    "대조군",    "diff",    True),
    # VIX 는 지도교수 피드백으로 '보류'지만 패널에 남긴다 — 삭제가 아니라 참조용이다.
    # 기존 검증(-0.534)이 이 지표 위에 서 있어서, 나란히 놓아야 새 지표 결과를
    # 기존 결과와 연결해 읽을 수 있다.
    # ★단 독립 증거가 아니다: NFCI↔VIX 상관 +0.738 이고, VIX 로 설명되지 않는
    #   NFCI 잔차와 통합지수의 상관은 -0.015(사실상 0)다. 즉 감성지수가 NFCI 와
    #   갖는 관계는 전부 VIX 와 공유하는 성분을 통해 흐른다. "두 지표에서 일관되게
    #   나왔으니 근거가 두 배"로 읽으면 같은 증거를 두 번 세는 것이다.
    Macro("VIXCLS", "VIX 변동성(보류·참조)",  "참조",      "diff",    True),
)


# ── HTTP 전송 방식 ────────────────────────────────────────────────────────────
# FRED 는 CDN 뒤에 있고, 환경에 따라 **Python 표준 TLS 스택(requests·urllib)만
# 막히고 curl 은 통과**하는 경우가 있다(실측: curl 200/1.6초 vs requests 30초
# ReadTimeout). TLS 지문 기반 차단으로 보인다. 그래서 requests 를 먼저 쓰되,
# 실패하면 그 뒤로는 계열마다 재시도하지 않고 curl 로 고정 전환한다
# (8계열 × 타임아웃 = 수 분 낭비 방지).
_TRANSPORT = None          # None=미결정, "requests", "curl"
_PROBE_TIMEOUT = 12        # 전송 방식 판별용 짧은 타임아웃


def _get_requests(url, timeout):
    import requests
    r = requests.get(url, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.text


def _get_curl(url, timeout):
    """curl 서브프로세스 폴백. Windows 10+ · macOS · 대부분 리눅스에 기본 탑재."""
    import subprocess
    p = subprocess.run(
        ["curl", "-sS", "--fail", "--max-time", str(timeout),
         "-H", f"User-Agent: {HEADERS['User-Agent']}", url],
        capture_output=True, text=True, timeout=timeout + 10,
    )
    if p.returncode != 0:
        raise RuntimeError(f"curl 실패(exit {p.returncode}): {p.stderr.strip()[:80]}")
    return p.stdout


def http_get(url, timeout=45):
    """FRED CSV 본문을 문자열로. 첫 호출에서 쓸 수 있는 전송 방식을 정한다."""
    global _TRANSPORT
    if _TRANSPORT is None:
        try:
            text = _get_requests(url, _PROBE_TIMEOUT)
            _TRANSPORT = "requests"
            return text
        except Exception as e:
            print(f"  [알림] requests 차단됨({type(e).__name__}) → curl 로 전환",
                  file=sys.stderr)
            _TRANSPORT = "curl"
    return _get_requests(url, timeout) if _TRANSPORT == "requests" else _get_curl(url, timeout)


def _cached(series_id):
    """캐시 파일 경로. 있으면 네트워크를 타지 않는다.

    두 가지를 동시에 해결한다:
      (1) 재현성 — 같은 원본으로 몇 번을 돌려도 같은 결과가 나온다.
      (2) 네트워크가 막힌 환경 — 파일만 채워두면 코드 수정 없이 돌아간다.
    캐시를 새로 받으려면 파일을 지우거나 FRED_CACHE_DIR 를 비운다.
    """
    return CACHE_DIR / f"{series_id}.csv"


def fetch_series(series_id, start, end):
    """FRED 한 계열 → date-indexed Series. 실패하면 None (전체를 죽이지 않는다).

    캐시(outputs/fred_cache/{ID}.csv) 가 있으면 그것을 쓰고, 없으면 내려받는다.
    FRED CSV 는 휴일·미발표를 "." 으로 채우므로 to_numeric 으로 NaN 처리한다.
    """
    cache = _cached(series_id)
    if cache.exists():
        text = cache.read_text(encoding="utf-8")
    else:
        url = FRED_CSV.format(id=series_id, start=start, end=end)
        try:
            text = http_get(url)
        except Exception as e:
            print(f"  [경고] {series_id} 수집 실패 → 건너뜀: {type(e).__name__}", file=sys.stderr)
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")

    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        print(f"  [경고] {series_id} 응답 형식 이상 → 건너뜀", file=sys.stderr)
        return None
    # 첫 열=날짜, 둘째 열=값. 열 이름은 FRED 버전에 따라 DATE/observation_date 로 달라진다.
    s = pd.Series(
        pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
        index=pd.to_datetime(df.iloc[:, 0], errors="coerce"),
        name=series_id,
    )
    return s[s.index.notna()].dropna()


def to_monthly(s):
    """일·주 단위 계열 → 월평균 (월초 인덱스).

    build_headline_norm.py 의 VIX 처리(resample("MS").mean())와 동일한 규칙.
    이미 월간인 계열(UNRATE·INDPRO·MICH)은 항등 변환이 된다.
    """
    return s.resample("MS").mean()


def add_change(monthly, transform):
    """월별 수준 → 변화 계열.

    추세가 있는 계열끼리 수준 상관을 내면 허위상관(spurious)이 나온다.
    지수·잔액은 로그차분(=증가율), %p 계열은 단순차분을 쓴다.
    """
    if transform == "logdiff":
        import numpy as np
        if (monthly <= 0).any():
            raise ValueError("logdiff 는 양수 계열에만 쓸 수 있다")
        return np.log(monthly).diff()
    return monthly.diff()


def collect(start=DEFAULT_START, end=None):
    """전 계열 수집 → 월별 wide DataFrame (컬럼: {id}, {id}_chg)."""
    end = end or date.today().isoformat()
    cols, meta = {}, []
    for m in SERIES:
        raw = fetch_series(m.id, start, end)
        if raw is None or raw.empty:
            print(f"  [건너뜀] {m.id} ({m.label}) — 데이터 없음")
            continue
        monthly = to_monthly(raw)
        cols[m.id] = monthly
        cols[f"{m.id}_chg"] = add_change(monthly, m.transform)
        meta.append((m, monthly))
        print(f"  [OK] {m.id:<8} {m.label:<22} "
              f"{monthly.index.min().date()} ~ {monthly.index.max().date()}  "
              f"({monthly.notna().sum()}개월)")
    if not cols:
        raise SystemExit("수집된 계열이 없습니다 — 네트워크를 확인하세요.")
    df = pd.concat(cols, axis=1)
    df.index.name = "month"
    return df


def series_meta():
    """검증 모듈이 쓸 지표 메타 (분석 쪽이 SERIES 상수에 직접 의존하지 않도록)."""
    return [m._asdict() for m in SERIES]


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_START
    end = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"FRED 거시지표 수집 ({start} ~ {end or '오늘'}) — 키 불필요\n")
    df = collect(start, end)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT)
    print(f"\n{len(df)}개월 × {len(df.columns)}컬럼 → {OUT}")

    # 검증 구간(2000-02~2021-05) 커버리지 — 여기가 비면 상관 표본이 줄어든다
    win = df.loc["2000-02-01":"2021-05-01"]
    print(f"\n검증 구간 커버리지 ({len(win)}개월 중):")
    for m in SERIES:
        if m.id in win.columns:
            n = int(win[m.id].notna().sum())
            flag = "" if n == len(win) else f"  ← {len(win) - n}개월 결측"
            print(f"  {m.id:<8} {n:>4}개월{flag}")


if __name__ == "__main__":
    main()
