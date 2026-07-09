"""괴리 신호 유의성 검정 — "괴리가 위기 구간에 우연보다 많이 몰리는가?"

TA 피드백 1순위. Fisher exact test + Permutation test.
위기 구간은 신호 입력(VIX·S&P)과 **독립**인 기준으로 **사전 정의**해 순환논리를 회피한다:
  · PRIMARY = NBER 공식 경기침체 (시장이 아니라 경제활동 기반, 표준·객관)
  · ROBUST  = NBER + 잘 알려진 금융스트레스 (강건성 확인용, 사전 목록화)

주장은 "예측"이 아니라 "괴리가 위기 구간에 우연보다 몰린다(연관)"까지만. attention signal.
실행: python3 analysis/validate_divergence.py
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.signals import build_alerts, load_series

DB = ROOT / "data" / "fomc.db"

# ── 사전 정의(pre-registered) 위기 구간 — 신호 입력과 독립 ──
NBER = [("2001-03-01", "2001-11-30"),   # 닷컴
        ("2007-12-01", "2009-06-30"),   # 글로벌 금융위기
        ("2020-02-01", "2020-04-30")]   # COVID
STRESS = NBER + [("2011-07-01", "2011-10-31"),   # 미국 신용강등·유로위기
                 ("2015-08-01", "2016-02-29"),   # 중국 위안화·유가급락
                 ("2018-10-01", "2018-12-31"),   # 2018 Q4 급락
                 ("2022-01-01", "2022-12-31"),   # 인플레·급속긴축
                 ("2023-03-01", "2023-05-31")]   # SVB 은행권


def _in(date, periods):
    return any(lo <= date <= hi for lo, hi in periods)


def divergence_flags(con):
    """각 회의: (날짜, 괴리 발동 여부). signals.build_alerts 의 divergence 신호 사용."""
    alerts = build_alerts(load_series(con))
    return [(a.date, any(s.name == "divergence" and s.fired for s in a.signals)) for a in alerts]


def test(flags, periods, label, n_perm=10000, seed=0):
    dates = np.array([d for d, _ in flags])
    div = np.array([x for _, x in flags], dtype=bool)
    crisis = np.array([_in(d, periods) for d in dates], dtype=bool)

    a = int((div & crisis).sum())    # 괴리 & 위기
    b = int((div & ~crisis).sum())   # 괴리 & 비위기
    c = int((~div & crisis).sum())   # 비괴리 & 위기
    d = int((~div & ~crisis).sum())  # 비괴리 & 비위기

    # Fisher exact (한쪽: 괴리가 위기에 과대표집?)
    try:
        from scipy.stats import fisher_exact
        odds, p_fisher = fisher_exact([[a, b], [c, d]], alternative="greater")
    except Exception:
        odds, p_fisher = float("nan"), float("nan")

    # Permutation: 괴리 라벨을 무작위 재배정(개수 고정) → 위기 구간에 몇 개 드나
    rng = np.random.default_rng(seed)
    n, k = len(div), int(div.sum())
    crisis_idx = set(np.where(crisis)[0].tolist())
    null = np.fromiter((sum(1 for i in rng.permutation(n)[:k] if i in crisis_idx)
                        for _ in range(n_perm)), dtype=float, count=n_perm)
    p_perm = (int((null >= a).sum()) + 1) / (n_perm + 1)

    rate_c = a / max(a + c, 1)      # 위기 구간 괴리율
    rate_n = b / max(b + d, 1)      # 비위기 구간 괴리율

    print(f"\n══ {label} ══")
    print(f"  2x2:  괴리&위기 {a} | 괴리&비위기 {b} | 비괴리&위기 {c} | 비괴리&비위기 {d}")
    print(f"  괴리율:  위기 구간 {rate_c:.0%}  vs  비위기 {rate_n:.0%}   (배율 {rate_c/max(rate_n,1e-9):.1f}x)")
    print(f"  Fisher exact (greater):  odds {odds:.2f},  p = {p_fisher:.4f}")
    print(f"  Permutation ({n_perm}회):  관측 {a} vs 우연평균 {null.mean():.1f},  p = {p_perm:.4f}")
    print(f"  → {'유의 (우연 아님)' if p_perm < 0.05 else '유의하지 않음'}")


def main():
    con = sqlite3.connect(DB)
    flags = divergence_flags(con)
    con.close()
    n, nd = len(flags), sum(x for _, x in flags)
    print(f"회의 {n}건 · 괴리 신호 {nd}건 ({nd/n:.0%})")
    test(flags, NBER, "PRIMARY — NBER 경기침체 (보수적·독립)")
    test(flags, STRESS, "ROBUST — NBER + 알려진 금융스트레스")
    print("\n※ 해석: '괴리가 위기 구간에 우연보다 몰린다(연관)'까지. '위기 예측'이 아님 — attention signal.")


if __name__ == "__main__":
    main()
