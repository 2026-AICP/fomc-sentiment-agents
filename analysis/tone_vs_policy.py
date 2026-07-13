"""감성 톤 ↔ 실제 금리결정(인상/동결/인하) — 라벨 없는 '매파/비둘기' 검증.

Fed 톤(conf_weighted)이 실제 정책행동과 정렬되는가? 인상 회의는 톤↑, 인하 회의는 톤↓?
금리결정은 **FRED 연방기금 목표금리 변화**(공개데이터, 라벨 불필요)로 객관 측정:
  DFEDTAR(~2008) + DFEDTARU(2008~) 이어붙여 회의 전후 목표금리 차 = 그 회의의 결정.

주장은 인과가 아니라 "감성 톤이 정책 스탠스와 정렬된다"는 상관까지. (감성 ≠ 매파/비둘기지만 연동)

실행: python3 analysis/tone_vs_policy.py
산출: docs/figures/comparison/tone_vs_policy.png
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.collect_market import _fetch_fred

DB = ROOT / "data" / "fomc.db"
FIGDIR = ROOT / "docs" / "figures" / "comparison"


def fed_tones():
    con = sqlite3.connect(DB)
    df = pd.read_sql("SELECT date, index_value AS tone FROM meetings "
                     "WHERE method='conf_weighted' AND granularity='meeting' ORDER BY date",
                     con, parse_dates=["date"])
    con.close()
    return df


def target_rate(start, end):
    """연속 목표금리 시리즈 (DFEDTAR ~2008 + DFEDTARU 2008~)."""
    parts = [s.dropna() for s in (_fetch_fred("DFEDTAR", start, end),
                                  _fetch_fred("DFEDTARU", start, end)) if s is not None]
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated(keep="first")]


def classify(c):
    return "Cut" if c < -0.05 else "Hike" if c > 0.05 else "Hold"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tones = fed_tones()
    rate = target_rate(tones.date.min().strftime("%Y-%m-%d"),
                       (tones.date.max() + pd.Timedelta(days=10)).strftime("%Y-%m-%d"))

    def chg(d):
        a, b = rate.asof(d + pd.Timedelta(days=2)), rate.asof(d - pd.Timedelta(days=2))
        return (a - b) if pd.notna(a) and pd.notna(b) else np.nan

    tones["chg"] = tones.date.apply(chg)
    tones = tones.dropna(subset=["chg"])
    tones["decision"] = tones.chg.apply(classify)

    r = tones.tone.corr(tones.chg)
    g = tones.groupby("decision").tone.agg(["count", "mean"])
    print(f"회의 {len(tones)}건 | 톤 ↔ 금리변화 상관 r = {r:+.3f}")
    print(g)

    FIGDIR.mkdir(parents=True, exist_ok=True)
    order = ["Cut", "Hold", "Hike"]
    colors = {"Cut": "#4a90e2", "Hold": "#9aa2ad", "Hike": "#ef4d4d"}   # 인하=파랑, 인상=빨강
    data = [tones[tones.decision == k].tone.values for k in order]

    fig, ax = plt.subplots(figsize=(7.5, 5.3))
    bp = ax.boxplot(data, tick_labels=[f"{k}\n(n={len(d)})" for k, d in zip(order, data)],
                    patch_artist=True, widths=0.55, showmeans=True,
                    meanprops=dict(marker="D", markerfacecolor="black", markersize=6),
                    medianprops=dict(color="#333"))
    for patch, k in zip(bp["boxes"], order):
        patch.set_facecolor(colors[k])
        patch.set_alpha(0.65)
    # 그룹 평균 라벨
    for i, (k, d) in enumerate(zip(order, data), 1):
        ax.text(i, np.max(d) + 0.02, f"mean {d.mean():+.3f}", ha="center", fontsize=9, color="#333")
    ax.axhline(0, color="#bbb", ls="--", lw=1)
    ax.set_ylabel("Fed sentiment tone (conf_weighted)")
    ax.set_xlabel("Actual rate decision (FRED target-rate change)")
    ax.set_title(f"Sentiment tone vs Policy decision   (r = {r:+.2f}, {len(tones)} meetings)")
    ax.text(0.02, 0.03, "◆ = group mean · validated with actual rate decisions (no labeling)",
            transform=ax.transAxes, fontsize=8, color="#666")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIGDIR / "tone_vs_policy.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
