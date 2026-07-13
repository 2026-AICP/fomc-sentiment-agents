"""Fed vs News vs 통합 — VIX 상관 비교 그림 (왜 두 축을 합치나).

각 지수(Fed단독·News단독·통합)의 VIX 상관을 비교 → **통합이 가장 강함**(≈-0.534).
왼쪽: 상관 크기(|r|) 막대 + 블록 부트스트랩 95% CI. 오른쪽: 통합 vs VIX 산점도.
데이터·CI는 검증된 코드 재사용(validate_robustness).

실행: python3 analysis/comparison_figure.py
산출: docs/figures/comparison/index_vs_vix_comparison.png
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.validate_robustness import aligned, combined, _z, block_boot_ci

FIGDIR = ROOT / "docs" / "figures" / "comparison"


def _abs_err(r, ci):
    """(막대높이=|r|, yerr_low, yerr_high) — 음수 상관이라 |CI| 로 변환."""
    bar = abs(r)
    lo, hi = sorted([abs(ci[0]), abs(ci[1])])
    return bar, bar - lo, hi - bar


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = aligned()
    fz = _z(df.fed, df.fed.mean(), df.fed.std())
    nz = _z(df.news, df.news.mean(), df.news.std())
    comb = combined(df, df)
    r_fed, r_news, r_comb = fz.corr(df.vix), nz.corr(df.vix), comb.corr(df.vix)
    ci_fed = block_boot_ci(fz, df.vix)
    ci_news = block_boot_ci(nz, df.vix)
    ci_comb = block_boot_ci(comb, df.vix)
    n = len(df)
    print(f"검증 {df.index.min().date()}~{df.index.max().date()} ({n}개월)")
    print(f"  Fed  {r_fed:+.3f}  CI {np.round(ci_fed,3)}")
    print(f"  News {r_news:+.3f}  CI {np.round(ci_news,3)}")
    print(f"  통합 {r_comb:+.3f}  CI {np.round(ci_comb,3)}")

    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, (axb, axs) = plt.subplots(1, 2, figsize=(12, 5.2))

    # ── 왼쪽: |상관| 막대 + 부트스트랩 CI ──
    names = ["Fed only", "News only", "Combined"]
    rs = [r_fed, r_news, r_comb]
    cis = [ci_fed, ci_news, ci_comb]
    colors = ["#9aa2ad", "#9aa2ad", "#f9812f"]
    heights, errlo, errhi = zip(*[_abs_err(r, c) for r, c in zip(rs, cis)])
    axb.bar(names, heights, color=colors, yerr=[errlo, errhi], capsize=6,
            error_kw=dict(ecolor="#555", lw=1.3))
    for i, (h, r) in enumerate(zip(heights, rs)):
        axb.text(i, h + 0.012, f"{r:+.3f}", ha="center", fontsize=11,
                 fontweight="bold" if i == 2 else "normal")
    axb.set_ylabel("|VIX correlation|   (higher = more market-aligned)")
    axb.set_title("Combined index is most correlated with market (VIX)")
    axb.set_ylim(0, max(heights) + 0.18)
    axb.grid(axis="y", alpha=0.25)

    # ── 오른쪽: 통합 지수 vs VIX 산점도 + 추세선 ──
    x, y = comb.values, df.vix.values
    axs.scatter(x, y, s=22, alpha=0.55, color="#4a90e2", edgecolor="white", linewidth=0.3)
    m, b = np.polyfit(x, y, 1)
    xr = np.array([x.min(), x.max()])
    axs.plot(xr, m * xr + b, color="#ef4d4d", lw=2, label=f"trend (r={r_comb:+.3f})")
    axs.set_xlabel("Combined sentiment index (z)")
    axs.set_ylabel("VIX (monthly avg)")
    axs.set_title(f"Combined index vs VIX  ({n} months, 2000–2021)")
    axs.legend(loc="upper right", fontsize=10)
    axs.grid(alpha=0.25)

    fig.tight_layout()
    out = FIGDIR / "index_vs_vix_comparison.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
