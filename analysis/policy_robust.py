"""견고성 검사 5종 — 조교 피드백 질문 4-4 에서 지정한 목록 그대로.

조교님 지적: "2008·2020 제외만으로는 충분하지 않다. 아래 정도 추가."

  ① 2008·2020 제외        위기 한두 개가 결과를 만드는지
  ② 2011년 이후 공통기간   기자회견 도입 전후 차이
  ③ 2000~2008 vs 2009+   회의록 수작업/자동수집 방식 차이
  ④ Tone level vs ΔTone   절대 톤인지 변화가 중요한지
  ⑤ Expanding-window OOS  진짜 과거 정보만으로 유지되는지

⑤ 는 policy_logit.py 가 이미 수행하므로 여기서는 ①~④ 를 돌리고 ⑤ 는 참조로 적는다.

검사 대상은 **결론을 떠받치는 두 주장**이다. 부수 수치가 아니라 이것들이 흔들리는지를 본다:
  primary   금리결정 — Fed 톤이 '지속성 + 시장기대' 위에 기여하는가 (M1→M2 우도비)
  secondary 2년물 2일 반응 — 톤 계수가 '결정 + 사전기대' 위에 유의한가 (HAC p)

실행:  python3 analysis/policy_robust.py
산출:  outputs/policy_robust.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "outputs" / "policy_dataset.csv"
OUT = ROOT / "outputs" / "policy_robust.csv"

BASE = ["prev_Cut", "prev_Hike"]
M1 = ["d2y_pre20"]
M2 = ["d2y_pre20", "stmt_prev", "minutes_prev"]
SEC_W = 2                      # 2년물 반응 창 — 본 분석에서 가장 강했던 창
MIN_N = 45                     # 이보다 작으면 검정을 시도하지 않는다


def load() -> pd.DataFrame:
    if not DATA.exists():
        raise SystemExit(f"{DATA} 없음 — 먼저 analysis/policy_dataset.py 를 실행하세요.")
    d = pd.read_csv(DATA, parse_dates=["date"])
    d["prev_Cut"] = (d.prev_dec == "Cut").astype(float)
    d["prev_Hike"] = (d.prev_dec == "Hike").astype(float)
    d["dec_Hike"] = (d.decision == "Hike").astype(float)
    d["dec_Cut"] = (d.decision == "Cut").astype(float)
    d["year"] = d.date.dt.year
    # ④ 용 — 톤의 '변화'. primary 는 직전 회의 톤을 쓰므로 그 한 칸 더 앞과의 차이다.
    d["dstmt_prev"] = d.stmt_prev - d.stmt_prev.shift(1)
    d["dstmt"] = d.stmt - d.stmt_prev
    return d


def primary_gain(sub: pd.DataFrame, tone_cols=("stmt_prev", "minutes_prev")):
    """M1 → M2 우도비 검정. (LR, p, n) 또는 None."""
    import statsmodels.api as sm
    from scipy import stats as st

    cols2 = M1 + list(tone_cols)
    s = sub.dropna(subset=cols2 + BASE + ["decision"])
    if len(s) < MIN_N or s.decision.nunique() < 3:
        return None
    out = []
    for cols in (M1, cols2):
        X = sm.add_constant(s[BASE + cols].astype(float).values, has_constant="add")
        res = None
        for method in ("newton", "bfgs"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    r = sm.MNLogit(s.decision.values, X).fit(disp=0, method=method, maxiter=2000)
                except Exception:
                    continue
            if np.isfinite(r.llf):
                res = r
                break
        if res is None:
            return None
        out.append((res.llf, X.shape[1]))
    lr = 2 * (out[1][0] - out[0][0])
    df = (out[1][1] - out[0][1]) * 2
    return lr, float(st.chi2.sf(max(lr, 0), df)), len(s)


def secondary_gain(sub: pd.DataFrame, tone_col="stmt"):
    """B1 → B2 에서 톤 계수의 HAC p값. (계수, p, n) 또는 None."""
    import statsmodels.api as sm

    y_col = f"d2y_post{SEC_W}"
    cols = ["dec_Hike", "dec_Cut", "d2y_pre20", tone_col]
    s = sub.dropna(subset=cols + [y_col])
    if len(s) < MIN_N:
        return None
    X = sm.add_constant(s[cols].astype(float), has_constant="add")
    res = sm.OLS(s[y_col].astype(float), X).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    return float(res.params[tone_col]), float(res.pvalues[tone_col]), len(s)


def _fmt_primary(r):
    if r is None:
        return f"{'—':>18}"
    lr, p, n = r
    return f"LR={lr:5.1f} p={p:.3f} n={n:>3}"


def _fmt_secondary(r):
    if r is None:
        return f"{'—':>22}"
    b, p, n = r
    return f"계수={b:+.4f} p={p:.3f} n={n:>3}"


def main():
    d = load()
    rows = []
    print("=" * 78)
    print("견고성 검사 — 조교 피드백 질문 4-4 지정 목록")
    print("=" * 78)
    print("primary  : 금리결정 — Fed 톤의 증분 (M1→M2 우도비)")
    print("secondary: 2년물 2일 반응 — 톤 계수 (HAC)")
    print()
    print(f"  {'검사':<34}{'primary':<26}{'secondary'}")
    print("  " + "-" * 74)

    checks = [
        ("전체 (기준)", d, "stmt_prev", "stmt"),
        ("① 2008·2020 제외", d[~d.year.isin([2008, 2009, 2020])], "stmt_prev", "stmt"),
        ("② 2011년 이후 (기자회견 도입 후)", d[d.year >= 2011], "stmt_prev", "stmt"),
        ("③-a 2000~2008 (회의록 수작업)", d[d.year <= 2008], "stmt_prev", "stmt"),
        ("③-b 2009년 이후 (자동수집)", d[d.year >= 2009], "stmt_prev", "stmt"),
        ("④ 톤 수준 → 톤 변화(ΔTone)", d, "dstmt_prev", "dstmt"),
    ]

    for label, sub, ptone, stone in checks:
        pr = primary_gain(sub, tone_cols=(ptone, "minutes_prev"))
        sc = secondary_gain(sub, tone_col=stone)
        print(f"  {label:<34}{_fmt_primary(pr):<26}{_fmt_secondary(sc)}")
        rows.append({
            "check": label,
            "primary_lr": None if pr is None else round(pr[0], 2),
            "primary_p": None if pr is None else round(pr[1], 4),
            "primary_n": None if pr is None else pr[2],
            "secondary_coef": None if sc is None else round(sc[0], 5),
            "secondary_p": None if sc is None else round(sc[1], 4),
            "secondary_n": None if sc is None else sc[2],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print("\n  ⑤ Expanding-window OOS 는 policy_logit.py 가 수행한다"
          " — 표본 외에서는 지속성 기준선을 넘지 못했다.")
    print("  ※ 부분표본은 표본이 줄어 검정력이 떨어진다. p값이 커지는 것이 곧"
          " '효과가 사라졌다'는 뜻은 아니다 —\n     계수의 부호·크기가 유지되는지를 함께 본다.")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
