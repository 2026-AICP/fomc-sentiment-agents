"""Fed 축 내부 가중치 근거 그림 — statement 단독 vs 2:2:1 vs 1:1:1 (포스터용).

세 문서를 각각 지수화한 뒤 어떤 비율로 합칠지에 대한 근거를 한 장으로 보인다.

  왼쪽  전 구간 VIX 상관 + 블록 부트스트랩 95% CI
        → 세 문서를 합치면 성명문 단독보다 설명이 강해지고, 균등(1:1:1)이 가장 강함
  오른쪽 홀드아웃 3분할 (앞 구간으로 z-파라미터 고정 → 안 본 뒤 구간에서 재측정)
        → 특정 기간에 맞춘 결과가 아님. 세 분할 모두에서 순서가 유지됨

★가중치는 데이터로 튜닝하지 않았다. 사전에 고정한 세 후보를 비교만 한다
 (튜닝하면 표본에 과적합돼 "최적" 가중이 표본 외에서 오히려 나빠진다 — 1/N 규칙).

수치는 validate_fed_weights 를 그대로 재사용해 문서·그림이 어긋나지 않게 한다.

실행: python3 analysis/fed_weights_figure.py
산출: docs/figures/comparison/fed_weights.png
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.validate_fed_weights import (CANDIDATES, CUTS, composite,  # noqa: E402
                                           daily_market, meetings, monthly_corr)
from analysis.validate_robustness import block_boot_ci  # noqa: E402

FIGDIR = ROOT / "docs" / "figures" / "comparison"
COLOR = {"기준선 stmt 단독": "#9aa2ad", "A안 2:2:1": "#4a90e2", "B안 1:1:1": "#f9812f"}


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    # 한글 라벨 — 사용 가능한 한글 폰트가 있으면 쓰고, 없으면 영문 라벨로 대체
    ko = next((f for f in ("AppleGothic", "Malgun Gothic", "NanumGothic")
               if any(f == x.name for x in font_manager.fontManager.ttflist)), None)
    if ko:
        plt.rcParams["font.family"] = ko
        plt.rcParams["axes.unicode_minus"] = False
    label = (lambda k, e: k if ko else e)

    df = meetings()
    mkt = daily_market(df.index.min(), df.index.max())
    vix = mkt.vix.resample("MS").mean()      # validate_fed_weights.main 과 동일 정의

    # ── 전 구간 상관 + 부트스트랩 CI (z-파라미터를 전 구간으로 fit) ──
    full = {}
    for name, w in CANDIDATES.items():
        r, joined = monthly_corr(composite(df, df, w), vix)
        lo, hi = block_boot_ci(joined.comp, joined.vix)
        full[name] = (r, lo, hi)

    # ── 홀드아웃: 앞 구간으로 fit → 뒤(안 본) 구간에서 재측정 ──
    hold = {name: [] for name in CANDIDATES}
    for cut in CUTS:
        fit = df[df.index < f"{cut}-01-01"]
        test = df[df.index >= f"{cut}-01-01"]
        for name, w in CANDIDATES.items():
            r_test, _ = monthly_corr(composite(test, fit, w), vix)
            hold[name].append(r_test)

    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig, (axf, axh) = plt.subplots(1, 2, figsize=(12.5, 5.0))
    names = list(CANDIDATES)

    # 왼쪽 — 전 구간 |상관| 막대 + CI
    ys = range(len(names))
    for i, n in enumerate(names):
        r, lo, hi = full[n]
        axf.barh(i, abs(r), color=COLOR[n], alpha=0.85, height=0.55)
        axf.errorbar(abs(r), i, xerr=[[abs(r) - abs(hi)], [abs(lo) - abs(r)]],
                     fmt="none", ecolor="#444", capsize=5, lw=1.3)
        axf.text(abs(lo) + 0.018, i, f"{r:+.3f}", va="center", fontsize=10.5,
                 fontweight="bold" if n.startswith("B") else "normal")   # CI 밖에 배치
    axf.set_yticks(list(ys))
    axf.set_yticklabels(names, fontsize=10.5)
    axf.set_xlabel(label("VIX 상관의 크기 |r| — 클수록 설명이 강함",
                         "|correlation with VIX| (higher = stronger)"))
    axf.set_title(label("전 구간 (317개월) · 95% 신뢰구간",
                        "Full sample (317 months) with 95% CI"), fontsize=12)
    axf.set_xlim(0, max(abs(v[1]) for v in full.values()) + 0.14)   # 값 라벨 자리
    axf.grid(axis="x", alpha=0.25)
    axf.invert_yaxis()

    # 오른쪽 — 홀드아웃 3분할
    for n in names:
        axh.plot(CUTS, [abs(r) for r in hold[n]], "o-",
                 color=COLOR[n], lw=2, ms=8, label=n)
    axh.set_xticks(CUTS)
    axh.set_xlabel(label("학습/검정 분할 연도 (뒤 구간은 학습에 쓰지 않음)",
                         "train/test split year"))
    axh.set_ylabel(label("안 본 기간에서의 |r|", "|r| on unseen period"))
    axh.set_title(label("홀드아웃 — 안 본 기간에서도 순서 유지",
                        "Holdout — order holds on unseen data"), fontsize=12)
    axh.legend(fontsize=9.5)
    axh.grid(alpha=0.25)

    fig.suptitle(label("Fed 축 내부 가중치: 세 문서를 어떻게 합칠까",
                       "Fed axis weights: how to combine three documents"),
                 fontsize=13.5, fontweight="bold")
    fig.text(0.5, 0.015,
             label("가중치는 데이터로 튜닝하지 않고 사전 고정한 후보만 비교. "
                   "회의록은 회의일 기준 정렬(실제 공개는 3주 뒤) — 해석 시 유의.",
                   "Candidates fixed in advance, not tuned. Minutes aligned to meeting date "
                   "(actual release ~3 weeks later)."),
             ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=[0, 0.04, 1, 0.94])
    out = FIGDIR / "fed_weights.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)

    print(f"저장: {out}")
    for n in names:
        r, lo, hi = full[n]
        h = " / ".join(f"{s}:{abs(v):.3f}" for s, v in zip(CUTS, hold[n]))
        print(f"  {n:<16} 전구간 {r:+.3f} [{lo:+.3f},{hi:+.3f}]  홀드아웃 {h}")


if __name__ == "__main__":
    main()
