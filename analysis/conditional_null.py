"""조건부 귀무가설 — 알림이 나가는 날의 기저 (docs/notification_design.md §7-7).

hit_thresholds.py 가 고정한 적중 임계값은 그대로 두고, **무엇과 비교하는가**만 다시
잰다. §7-6 의 14.4% 는 '아무 날이나 골랐을 때'의 값인데, 알림은 아무 날에나 나가지
않기 때문이다.

  signal_divergence   → |시장 반응| ≥ theta_m   (0.80%)   ← 🔴 경고의 유일한 트리거
  signal_tone_vs_vix  → |VIX 변화|  ≥ theta_vix (1.00pt)
  signal_tone_shift   → 시장 조건 없음

즉 🔴 은 이미 시장이 크게 움직인 날에만 나간다. 변동성은 군집하므로 그런 날의 다음
날은 원래 더 출렁이고, 14.4% 와 비교하면 그 군집 효과를 신호의 성능으로 오독한다.

임계값을 재계산하지 않으므로 사전 등록을 훼손하지 않는다 — outputs/hit_thresholds.json
을 읽기만 하고, 표본 구간도 그 파일에 박힌 값을 그대로 쓴다(재실행해도 값이 안 변한다).

실행:  python3 analysis/conditional_null.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis import collect_market as cm   # 인증서 우회 + yfinance 설정 재사용
from analysis.signals import COMBINED_THRESHOLDS as TH   # agents/graph.py 가 쓰는 θ
import pandas as pd
from scipy import stats

THRESHOLDS_JSON = ROOT / "outputs" / "hit_thresholds.json"
CRISIS_YEARS = (2008, 2020)   # 조교님 질문 4-4: 위기 한두 개가 결과를 만드는지
OBSERVED = 0.25               # §8-1 이 예시로 쓰는 관측 적중률
POWER_N = (20, 40, 60, 200, 800)


def load_fixed() -> tuple[str, str, float, float, float]:
    """고정된 표본 구간과 주 기준(h=1) 임계값. 계산하지 않고 읽기만 한다."""
    j = json.loads(THRESHOLDS_JSON.read_text(encoding="utf-8"))
    h = str(j["definition"]["primary_horizon_days"])
    t = j["thresholds"][h]
    return (j["sample"]["start"], j["sample"]["end"],
            t["thr_spx_abs_ret_pct"], t["thr_vix_abs_chg_pt"], t["rate_union"])


def download(start: str, end: str) -> pd.DataFrame:
    """^GSPC·^VIX 일별 종가. hit_thresholds.py 와 같은 경로."""
    raw = cm.yf.download(["^GSPC", "^VIX"], start=start, end=end,
                         progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        raise RuntimeError("yfinance 가 빈 데이터를 반환했다.")
    df = pd.DataFrame({"spx": raw["Close"]["^GSPC"],
                       "vix": raw["Close"]["^VIX"]}).dropna()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def rate(hit: pd.Series, mask: pd.Series) -> tuple[int, float]:
    return int(mask.sum()), float(hit[mask].mean())


def main() -> None:
    start, end, thr_spx, thr_vix, registered = load_fixed()
    print(f"표본 {start} ~ {end} (outputs/hit_thresholds.json 에 고정된 구간)")
    print(f"적중 판정(h=1): |S&P| > {thr_spx}%  또는  |ΔVIX| > {thr_vix}pt\n")

    df = download(start, pd.Timestamp(end).strftime("%Y-%m-%d"))
    ret = df.spx.pct_change() * 100     # 당일 종가 수익률 % — graph.py 의 spx_ret_cc
    chg = df.vix.diff()                 # 당일 VIX 변화 pt — collect_market 의 vix_chg
    hit = ((ret.shift(-1).abs() > thr_spx) | (chg.shift(-1).abs() > thr_vix))
    ok = ret.notna() & chg.notna() & ret.shift(-1).notna() & chg.shift(-1).notna()

    n_all, base = rate(hit, ok)
    print(f"검증: 무조건부 재현 {base:.4f} (등록값 {registered}) — 일치해야 한다\n")

    big_spx = ret.abs() >= TH.theta_m      # divergence 조건
    big_vix = chg.abs() >= TH.theta_vix    # tone_vs_vix 조건
    conds = [
        ("조건 없음 (tone_shift)",             ok),
        (f"|S&P| >= {TH.theta_m}%  divergence", ok & big_spx),
        (f"|ΔVIX| >= {TH.theta_vix}pt tone_vs_vix", ok & big_vix),
        ("둘 중 하나라도",                      ok & (big_spx | big_vix)),
        ("둘 다 (실제 🔴 형태)",                ok & big_spx & big_vix),
    ]
    print(f"{'조건 (t일)':<34}{'t→t+1 적중률':>12}{'n':>8}{'무조건부 대비':>14}")
    for label, mask in conds:
        n, p = rate(hit, mask)
        print(f"{label:<34}{p*100:>11.1f}%{n:>8}{p/base:>13.2f}배")

    keep = ~df.index.year.isin(CRISIS_YEARS)
    print(f"\n[강건성] {'·'.join(map(str, CRISIS_YEARS))} 제외")
    for label, mask in conds[:2]:
        n, p = rate(hit, mask & keep)
        print(f"  {label:<34}{p*100:>11.1f}%{n:>8}")

    print(f"\n[검정력] 관측 {OBSERVED:.0%} 를 귀무가설과 구분할 수 있는가")
    for label, mask in (conds[0], conds[1]):
        _, p0 = rate(hit, mask)
        print(f"  귀무 {p0:.1%} — {label}")
        for n in POWER_N:
            k = round(OBSERVED * n)
            pv = stats.binomtest(k, n, p0, alternative="greater").pvalue
            need = next(x for x in range(n + 1)
                        if stats.binomtest(x, n, p0, alternative="greater").pvalue < 0.05)
            print(f"    n={n:<5}{OBSERVED:.0%}={k:>4}건 → p={pv:.3f}"
                  f"   유의 하한 {need}건({need/n:.0%})")


if __name__ == "__main__":
    main()
