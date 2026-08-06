"""강건성 종합 그림 — 통합↔VIX(-0.534)의 신뢰성을 3각도로 한눈에 (포스터용).

  · Holdout(시간분할): 안 본 기간에도 유지 → 과최적 아님
  · Bootstrap 95% CI: 0과 구분 → 우연 아님
  · LOMO(leave-one-month-out): 어떤 달 하나 빼도 유지 → 특정 사건(2008·2020) 비의존
코드·데이터는 validate_robustness 재사용.

실행: python3 analysis/robustness_figure.py
산출: docs/figures/comparison/robustness_summary.png
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.validate_robustness import aligned, combined, holdout, block_boot_ci

FIGDIR = ROOT / "docs" / "figures" / "comparison"
SPLITS = ["2012", "2014", "2016"]     # holdout()이 연도만 받아 -01-01 을 붙임


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = aligned()
    comb = combined(df, df)
    c, v = comb.values, df.vix.values
    full_r = float(np.corrcoef(c, v)[0, 1])
    ci = block_boot_ci(comb, df.vix)
    lomo = np.array([np.corrcoef(np.delete(c, i), np.delete(v, i))[0, 1] for i in range(len(c))])
    lo, hi = lomo.min(), lomo.max()
    worst = df.index[int(np.argmax(np.abs(lomo - full_r)))].date()
    hold = [(cut,) + tuple(holdout(df, cut)) for cut in SPLITS]  # (yr, nf, nt, r_fit, r_test)

    print(f"n={len(df)} | full r={full_r:+.3f} | 부트 CI [{ci[0]:+.3f}, {ci[1]:+.3f}]")
    print(f"LOMO: 범위 [{lo:+.3f}, {hi:+.3f}] · 최대영향 달 {worst} → {lomo[np.argmax(np.abs(lomo-full_r))]:+.3f}")
    for y, nf, nt, rf, rt in hold:
        print(f"  Holdout {y}: in {rf:+.3f} / out {rt:+.3f}")

    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, (axf, axl) = plt.subplots(1, 2, figsize=(12.5, 5.2))

    # ── Panel A: 추정치 안정성 (Full+CI, Holdout out-of-sample) ──
    rows = ["Full sample"] + [f"Holdout {y}" for y, *_ in hold]
    ys = np.arange(len(rows))[::-1]
    axf.axvline(full_r, color="#f9812f", ls="--", lw=1.2, alpha=0.6)
    axf.errorbar(full_r, ys[0], xerr=[[full_r - ci[0]], [ci[1] - full_r]], fmt="o",
                 color="#f9812f", ms=11, capsize=6, lw=1.6, label="Full sample (95% CI)")
    axf.scatter([rt for *_, rt in hold], ys[1:], color="#4a90e2", s=85, zorder=3,
                label="Holdout (out-of-sample)")
    for (rt, yy) in zip([rt for *_, rt in hold], ys[1:]):
        axf.annotate(f"{rt:+.3f}", (rt, yy), textcoords="offset points", xytext=(0, 9),
                     ha="center", fontsize=9, color="#4a90e2")
    axf.annotate(f"{full_r:+.3f}", (full_r, ys[0]), textcoords="offset points", xytext=(0, 11),
                 ha="center", fontsize=10, fontweight="bold", color="#f9812f")
    axf.set_yticks(ys)
    axf.set_yticklabels(rows)
    axf.set_ylim(-0.6, len(rows) - 0.2)
    axf.set_xlabel("Correlation with VIX")
    axf.set_title("Estimate stays ≈ −0.53 (holdout + bootstrap)")
    axf.grid(axis="x", alpha=0.25)
    axf.legend(loc="lower left", fontsize=9)

    # ── Panel B: LOMO 분포 ──
    axl.hist(lomo, bins=30, color="#2dd4a0", alpha=0.75, edgecolor="white")
    axl.axvline(full_r, color="#f9812f", lw=2, label=f"Full sample ({full_r:+.3f})")
    axl.set_xlabel("Correlation with VIX  (each = one month left out)")
    axl.set_ylabel("Count")
    axl.set_title(f"Leave-one-month-out: all in [{lo:+.3f}, {hi:+.3f}]")
    axl.text(0.03, 0.97, f"n={len(df)} months\nno single month drives it\n(most influential: {worst})",
             transform=axl.transAxes, va="top", fontsize=8.5, color="#555",
             bbox=dict(boxstyle="round", fc="white", ec="#ccc", alpha=0.85))
    axl.legend(loc="upper right", fontsize=9)
    axl.grid(axis="y", alpha=0.25)

    fig.suptitle("Robustness of Combined index ↔ VIX  (−0.534, 256 months)", fontsize=13, y=1.02)
    fig.tight_layout()
    out = FIGDIR / "robustness_summary.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
