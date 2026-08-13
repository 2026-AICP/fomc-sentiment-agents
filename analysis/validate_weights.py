"""통합 가중치(50:50) 검증 — 거시지표 패널로 각 축 대비 우위를 확인.

설계: `docs/superpowers/specs/2026-08-09-vix-replacement-indicators-design.md`

VIX 보류로 headline.py 50:50 결합의 유일한 근거가 비었다. VIX 하나 대신
성격이 다른 거시지표 8개(연준의 목표·도구 기준 선정)에 같은 검정을 반복해,
결론이 지표 전반에서 유지되는지를 본다.

핵심 판정 — 부호가 아니라 **통합이 각 축 단독을 이기는가**:

    |corr(통합, 지표)| > max(|corr(Fed, 지표)|, |corr(News, 지표)|)

★순환논리가 아닌 이유: 50:50 은 지도교수가 사전에 고정한 값이지 데이터로
  적합한 파라미터가 아니다. "상관이 최대가 되게 가중치를 골랐다"가 아니라
  "고정된 50:50 이 각 축보다 나은가"를 검정한다.

★다중비교 주의: 14개 조합(8지표 × 최대 2변환)을 보면 하나쯤은 우연히 좋다.
  개별 유의성이 아니라 **전 지표에 걸친 일관성**으로 판정하고, 모든 결과를
  싣는다(체리피킹 금지). 유의성은 단순 p값이 아니라 블록 부트스트랩 CI 로 본다
  — 월별 계열은 자기상관이 강해 단순 p값이 과대평가된다.

선행:
  python3 pipeline.py                  # Fed 축 (data/fomc.db)
  python3 analysis/news_index.py       # News 축 (outputs/news_index.csv)
  python3 analysis/collect_macro.py    # 지표 (outputs/macro_monthly.csv)

실행:
  python3 analysis/validate_weights.py           # 검증 + CSV 저장
  python3 analysis/validate_weights.py --repro   # 기존 VIX 수치 재현까지 확인
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.build_headline_norm import fed_monthly, news_monthly   # noqa: E402
from analysis.collect_macro import SERIES                            # noqa: E402
from analysis.validate_robustness import block_boot_ci               # noqa: E402

MACRO_CSV = ROOT / "outputs" / "macro_monthly.csv"
OUT = ROOT / "outputs" / "weight_validation.csv"

# 기존 VIX 검증과 같은 구간으로 고정 — 수치를 나란히 비교할 수 있어야 한다.
# (analysis/headline_norm.json: 2000-02-01~2021-05-01, 256개월)
WIN_START, WIN_END = "2000-02-01", "2021-05-01"
MIN_N = 24            # 이보다 표본이 적으면 상관을 내지 않는다(의미 없음)


def sentiment_axes():
    """Fed·News 월별 축 + 50:50 통합(z) → DataFrame[fed, news, combined].

    축 구성은 build_headline_norm 과 **동일 함수를 호출**해 재현한다.
    결합 공식을 여기서 다시 구현하면 두 곳이 어긋난다.
    """
    fed, news = fed_monthly(), news_monthly()
    df = pd.concat([fed, news], axis=1).loc[WIN_START:WIN_END].dropna()
    if df.empty:
        raise SystemExit("Fed·News 축이 겹치는 구간이 없습니다 — 선행 단계를 확인하세요.")
    fz = (df.fed - df.fed.mean()) / df.fed.std()
    nz = (df.news - df.news.mean()) / df.news.std()
    return pd.DataFrame({"fed": fz, "news": nz, "combined": 0.5 * fz + 0.5 * nz})


def macro_panel():
    if not MACRO_CSV.exists():
        raise SystemExit(f"{MACRO_CSV} 없음 — 먼저 analysis/collect_macro.py 를 실행하세요.")
    return pd.read_csv(MACRO_CSV, index_col=0, parse_dates=True)


def boot_delta_ci(df, block=12, n=3000, seed=0):
    """통합 우위폭 Δ = |r(통합)| - max(|r(Fed)|, |r(News)|) 의 95% CI.

    ★왜 필요한가: 통합 상관의 CI 는 "0과 다른가"만 말한다. 이 항목의 주장은
      "통합이 각 축보다 낫다"이므로 **차이 자체**를 검정해야 한다. Δ 의 CI 하한이
      0 을 넘어야 우위를 주장할 수 있고, 0 을 걸치면 점추정상 이겨도 "우연과
      구분 안 됨"이다. block_boot_ci 와 같은 블록 재표집(자기상관 보존)을 쓴다.
    """
    rng = np.random.default_rng(seed)
    a = df[["fed", "news", "combined", "y"]].values
    N = len(a)
    nb = int(np.ceil(N / block))
    out = []
    for _ in range(n):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, N - block + 1)
            idx.extend(range(s, s + block))
        b = a[np.array(idx[:N])]
        r = [abs(np.corrcoef(b[:, i], b[:, 3])[0, 1]) for i in range(3)]
        out.append(r[2] - max(r[0], r[1]))
    return np.percentile(out, [2.5, 97.5])


def evaluate(axes, target, boot=True):
    """축 3개 vs 지표 1개 → 상관·판정·CI. 표본 부족이면 None.

    변화(diff) 모드에서는 지표뿐 아니라 **감성 축도 같이 차분**한다
    (수준 대 변화를 섞어 비교하면 안 된다).
    """
    df = pd.concat([axes, target.rename("y")], axis=1).dropna()
    if len(df) < MIN_N:
        return None
    r = {k: float(df[k].corr(df.y)) for k in ("fed", "news", "combined")}
    delta = abs(r["combined"]) - max(abs(r["fed"]), abs(r["news"]))
    lo, hi = block_boot_ci(df.combined, df.y) if boot else (np.nan, np.nan)
    dlo, dhi = boot_delta_ci(df) if boot else (np.nan, np.nan)
    return {"n": len(df), **{f"r_{k}": round(v, 3) for k, v in r.items()},
            "combined_wins": delta > 0, "delta": round(delta, 3),
            "delta_lo": round(float(dlo), 3), "delta_hi": round(float(dhi), 3),
            "delta_sig": bool(dlo > 0),          # 우위가 우연과 구분되는가
            "ci_lo": round(float(lo), 3), "ci_hi": round(float(hi), 3)}


def run(boot=True):
    axes, macro = sentiment_axes(), macro_panel()
    d_axes = axes.diff()                       # 변화 모드용 (감성 축도 함께 차분)
    rows = []
    for m in SERIES:
        if m.id not in macro.columns:
            print(f"  [건너뜀] {m.id} — 지표 CSV 에 없음")
            continue
        modes = [("change", d_axes, macro[f"{m.id}_chg"])]
        if m.use_level:                        # 추세 계열은 수준 상관을 싣지 않는다
            modes.insert(0, ("level", axes, macro[m.id]))
        for mode, a, y in modes:
            res = evaluate(a, y.loc[WIN_START:WIN_END], boot=boot)
            if res is None:
                print(f"  [건너뜀] {m.id} ({mode}) — 표본 {MIN_N}개월 미만")
                continue
            rows.append({"indicator": m.id, "label": m.label, "group": m.group,
                         "transform": mode, **res})
    return pd.DataFrame(rows)


def repro_check():
    """기존 VIX 수치(-0.436 / -0.386 / -0.534) 재현 — 파이프라인 건전성 확인.

    새 지표에서 이상한 값이 나왔을 때 지표 탓인지 코드 탓인지 가르는 유일한 장치다.
    """
    from analysis.build_headline_norm import vix_monthly
    axes = sentiment_axes()
    vix = vix_monthly(axes.index.min(), axes.index.max() + pd.offsets.MonthEnd(1))
    df = pd.concat([axes, vix.rename("y")], axis=1).dropna()
    got = {k: round(float(df[k].corr(df.y)), 3) for k in ("fed", "news", "combined")}
    want = {"fed": -0.436, "news": -0.386, "combined": -0.534}
    print(f"\n[재현 확인] VIX 상관 ({len(df)}개월)")
    for k in want:
        mark = "OK" if abs(got[k] - want[k]) <= 0.02 else "불일치"
        print(f"  {k:<9} 기대 {want[k]:+.3f} / 실측 {got[k]:+.3f}   {mark}")


def main():
    boot = "--fast" not in sys.argv
    df = run(boot=boot)
    if df.empty:
        raise SystemExit("결과가 없습니다 — 선행 단계 산출물을 확인하세요.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    print(f"\n검증 구간 {WIN_START} ~ {WIN_END}\n")
    print(f"{'지표':<9}{'변환':<8}{'n':>5}{'Fed':>8}{'News':>8}{'통합':>8}"
          f"{'우위폭Δ':>9}   Δ 95% CI            판정")
    print("-" * 92)
    # 주의: r.transform 은 pandas Series 의 .transform() 메서드와 충돌한다 → 대괄호 접근
    for _, r in df.iterrows():
        dci = f"[{r['delta_lo']:+.3f}, {r['delta_hi']:+.3f}]" if pd.notna(r["delta_lo"]) else ""
        if r["delta_sig"]:
            verdict = "우위(유의)"
        elif r["combined_wins"]:
            verdict = "우위(불확실)"
        else:
            verdict = "-"
        print(f"{r['indicator']:<9}{r['transform']:<8}{r['n']:>5}"
              f"{r['r_fed']:>+8.3f}{r['r_news']:>+8.3f}{r['r_combined']:>+8.3f}"
              f"{r['delta']:>+9.3f}   {dci:<22}{verdict}")

    t = len(df)
    w = int(df["combined_wins"].sum())
    sig = int(df["delta_sig"].sum())
    print(f"\n판정: {t}개 조합 중 통합 우위 {w}개 ({w / t:.0%}) · "
          f"그중 우연과 구분되는 것 {sig}개")
    print(f"→ {OUT}")

    if "--repro" in sys.argv:
        repro_check()


if __name__ == "__main__":
    main()
