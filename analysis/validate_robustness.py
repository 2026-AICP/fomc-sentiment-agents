"""통합지수 견고함 검증 — 시간분할 홀드아웃 + 블록 부트스트랩 CI.

docs/news_fed_index.md §3 의 통합↔VIX 상관(-0.534)이
  (1) 과최적(in-sample)이 아니라 안 본 기간에도 일반화되고 [홀드아웃]
  (2) 우연이 아니라 0 과 구분된다 [부트스트랩 95% CI]
를 정량으로 보인다.

입력: fomc.db(Fed) + outputs/news_index.csv(News) + VIX. build_headline_norm 재사용.
실행: python3 analysis/news_index.py  (선행) 후  python3 analysis/validate_robustness.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.build_headline_norm import fed_monthly, news_monthly, vix_monthly


def aligned():
    fed, news = fed_monthly(), news_monthly()
    lo = max(fed.index.min(), news.index.min())
    hi = min(fed.index.max(), news.index.max())
    vix = vix_monthly(lo, hi + pd.offsets.MonthEnd(1))
    return pd.concat([fed, news, vix], axis=1).loc[lo:hi].dropna()


def _z(s, mu, sd):
    return (s - mu) / sd


def combined(df, base):
    """base 구간으로 z-파라미터 산출 → df 에 적용한 50:50 통합값."""
    return 0.5 * _z(df.fed, base.fed.mean(), base.fed.std()) + \
           0.5 * _z(df.news, base.news.mean(), base.news.std())


def holdout(df, cut):
    """앞(<cut) 으로 z-파라미터 fit → 뒤(>=cut, 안 본 기간)에서 상관 검정."""
    fit = df[df.index < f"{cut}-01-01"]
    test = df[df.index >= f"{cut}-01-01"]
    r_fit = combined(fit, fit).corr(fit.vix)
    r_test = combined(test, fit).corr(test.vix)
    return len(fit), len(test), r_fit, r_test


def block_boot_ci(x, y, block=12, n=3000, seed=0):
    """블록 부트스트랩 (시계열 자기상관 보존) → 상관의 95% CI."""
    rng = np.random.default_rng(seed)
    x, y = x.values, y.values
    N = len(x)
    nb = int(np.ceil(N / block))
    rs = []
    for _ in range(n):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, N - block + 1)
            idx.extend(range(s, s + block))
        idx = np.array(idx[:N])
        rs.append(np.corrcoef(x[idx], y[idx])[0, 1])
    return np.percentile(rs, [2.5, 97.5])


def main():
    df = aligned()
    full = combined(df, df)
    r_full = full.corr(df.vix)
    print(f"전체: {df.index.min().date()}~{df.index.max().date()} ({len(df)}개월) · 통합↔VIX {r_full:+.3f}\n")

    print("── 홀드아웃 (앞=학습으로 z-파라미터 fit, 뒤=안 본 기간 검정) ──")
    for cut in (2012, 2014, 2016):
        nf, nt, rf, rt = holdout(df, cut)
        print(f"  {cut} 분할: 학습 {nf}개월(in-sample {rf:+.3f}) → 검정 {nt}개월  홀드아웃 {rt:+.3f}")

    lo, hi = block_boot_ci(full, df.vix)
    sig = "0 미포함 → 유의" if hi < 0 else "0 포함"
    print(f"\n── 블록 부트스트랩 95% CI (block=12개월, 3000회) ──")
    print(f"  통합↔VIX {r_full:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]   ({sig})")


if __name__ == "__main__":
    main()
