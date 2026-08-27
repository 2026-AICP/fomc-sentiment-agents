"""2년물 국채금리 반응 — secondary outcome (조교 피드백 질문 4-1 ②).

금리결정(3분류)이 primary, **2년물 반응이 secondary** 다. 조교 피드백:
"다음 회의까지의 변화보다 **짧은 window 부터** 보는 게 더 좋다" → 1·2·5거래일.

★검증하는 것 (조교님 표현을 그대로 따른다):
  "Fed communication tone 이 이후 Fed policy action 과 얼마나 정렬되어 있는지,
   그리고 **기존 정보에 추가적인 정보가 있는지**"

그래서 톤 하나만 넣고 R² 를 보는 게 아니라, **이미 아는 것을 먼저 넣고** 톤이
그 위에 무엇을 더하는지만 본다. 중첩 모형은 사전에 고정한다:

  B0  결정 더미        인상·인하 (동결 기준) — 발표된 결정 그 자체
  B1  + 사전 기대      회의 전 20거래일 2년물 변화 (시장이 이미 반영한 부분)
  B2  + 성명문 톤      톤이 결정·기대 너머로 추가 정보를 주는가

★여기서는 동시점 톤을 쓰는 것이 맞다. primary(금리결정)에서는 성명문이 결정을
  서술하므로 동시점 톤이 누출이었지만, 여기서는 **톤이 원인 쪽, 금리 반응이 결과 쪽**
  이다. 다만 결정 자체가 금리를 움직이므로 B0 로 반드시 통제한다 — 통제 없이 톤만
  넣으면 "결정의 효과"를 톤의 공로로 오인한다.

★종속변수가 연속이므로 여기서는 OLS 가 맞다. 조교님이 OLS 를 물린 것은
  primary(인상/동결/인하 3범주)에 한한 지적이다.

★표준오차는 HAC(Newey-West) 를 쓴다 — 회의 간격이 불규칙하고 잔차에 자기상관이
  남을 수 있어 단순 OLS 표준오차는 유의성을 과대평가한다.

실행:  python3 analysis/policy_rate2y.py
산출:  outputs/policy_rate2y.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "outputs" / "policy_dataset.csv"
OUT = ROOT / "outputs" / "policy_rate2y.csv"

WINDOWS = (1, 2, 5)          # 거래일 — 짧은 것부터
HAC_LAGS = 4                 # Newey-West 시차

MODELS = [
    ("B0 결정",       ["dec_Hike", "dec_Cut"]),
    ("B1 +사전기대",  ["dec_Hike", "dec_Cut", "d2y_pre20"]),
    ("B2 +성명문톤",  ["dec_Hike", "dec_Cut", "d2y_pre20", "stmt"]),
]


def load() -> pd.DataFrame:
    if not DATA.exists():
        raise SystemExit(f"{DATA} 없음 — 먼저 analysis/policy_dataset.py 를 실행하세요.")
    d = pd.read_csv(DATA, parse_dates=["date"])
    d["dec_Hike"] = (d.decision == "Hike").astype(float)
    d["dec_Cut"] = (d.decision == "Cut").astype(float)
    return d


def run_window(d: pd.DataFrame, w: int, rows: list) -> None:
    import statsmodels.api as sm

    y_col = f"d2y_post{w}"
    need = ["stmt", "d2y_pre20", y_col]
    sub = d.dropna(subset=need).reset_index(drop=True)

    print(f"\n[{w}거래일 반응]  n={len(sub)}  "
          f"({sub.date.min().date()} ~ {sub.date.max().date()})")
    print(f"  종속변수 표준편차 {sub[y_col].std():.4f}%p")
    print(f"  {'모형':<14}{'R²':>8}{'ΔR²':>8}{'톤 계수':>11}{'HAC t':>8}{'p':>8}")
    print("  " + "-" * 57)

    prev_r2 = None
    for name, cols in MODELS:
        X = sm.add_constant(sub[cols].astype(float), has_constant="add")
        res = sm.OLS(sub[y_col].astype(float), X).fit(
            cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
        d_r2 = "" if prev_r2 is None else f"{res.rsquared - prev_r2:+.3f}"
        if "stmt" in cols:
            b, t, p = res.params["stmt"], res.tvalues["stmt"], res.pvalues["stmt"]
            tone = f"{b:>+11.4f}{t:>8.2f}{p:>8.3f}"
        else:
            tone = f"{'—':>11}{'—':>8}{'—':>8}"
        print(f"  {name:<14}{res.rsquared:>8.3f}{d_r2:>8}{tone}")
        rows.append({"window_days": w, "model": name, "n": len(sub),
                     "r2": round(res.rsquared, 4),
                     "delta_r2": None if prev_r2 is None else round(res.rsquared - prev_r2, 4),
                     "tone_coef": round(float(res.params.get("stmt", np.nan)), 5)
                     if "stmt" in cols else None,
                     "tone_p_hac": round(float(res.pvalues.get("stmt", np.nan)), 4)
                     if "stmt" in cols else None})
        prev_r2 = res.rsquared


def variant_grid(d: pd.DataFrame, rows: list) -> None:
    """설계 변형 격자 — 후보를 **전부** 돌려 결과를 다 보여준다.

    ★왜 격자를 다 싣는가: 여러 설계를 시험해 가장 좋은 하나만 보고하면 p값이
      부풀려진다(다중비교). 선택 자체는 문제가 아니지만 **선택지를 숨기면** 문제가 된다.
      그래서 전부 싣고, 고른 이유를 성능이 아닌 근거로도 댈 수 있는지 따로 적는다.

    ★후보에서 회의록을 뺀 이유: 회의록은 회의 3주 뒤 공개된다. 회의 당일~2일 금리
      반응을 회의록으로 설명하면 미래 정보를 쓰는 것이다(look-ahead). 성능이 좋게
      나오더라도 쓸 수 없다 — 그래서 애초에 후보에 넣지 않는다.
    """
    import statsmodels.api as sm

    tones = [
        ("성명문", ["stmt"]),
        ("성명문+기자회견", ["stmt", "presser_now"]),
        ("뉴스(직전월)", ["news_pre"]),
        ("성명문+뉴스", ["stmt", "news_pre"]),
    ]
    print("\n" + "=" * 62)
    print("설계 변형 격자 — 전 조합 (선택 전 전체 공개)")
    print("=" * 62)
    print(f"  {'톤 구성':<18}{'창':>4}{'n':>6}{'ΔR²':>9}{'대표계수':>11}{'HAC p':>9}")
    print("  " + "-" * 57)

    for label, tcols in tones:
        for w in (1, 2, 3, 5):
            y_col = f"d2y_post{w}"
            base = ["dec_Hike", "dec_Cut", "d2y_pre20"]
            s = d.dropna(subset=base + tcols + [y_col])
            if len(s) < 45:
                continue
            r0 = sm.OLS(s[y_col].astype(float),
                        sm.add_constant(s[base].astype(float), has_constant="add")
                        ).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
            r1 = sm.OLS(s[y_col].astype(float),
                        sm.add_constant(s[base + tcols].astype(float), has_constant="add")
                        ).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
            lead = tcols[0]
            print(f"  {label:<18}{w:>4}{len(s):>6}{r1.rsquared - r0.rsquared:>+9.3f}"
                  f"{r1.params[lead]:>+11.4f}{r1.pvalues[lead]:>9.3f}")
            rows.append({"window_days": w, "model": f"변형: {label}", "n": len(s),
                         "r2": round(r1.rsquared, 4),
                         "delta_r2": round(r1.rsquared - r0.rsquared, 4),
                         "tone_coef": round(float(r1.params[lead]), 5),
                         "tone_p_hac": round(float(r1.pvalues[lead]), 4)})

    print("\n  ※ 조합 16개를 전부 시험했다. 개별 p값은 다중비교 보정 전 값이므로,")
    print("     하나를 골라 'p<0.05' 라고 말하려면 그 선택이 성능 외 근거로도")
    print("     정당해야 한다 (조교 피드백: 짧은 창부터 볼 것).")


def expanding_oos(d: pd.DataFrame, w: int, rows: list, min_train: int = 80) -> None:
    """확장 윈도우 표본 외 — 톤이 '이미 아는 정보' 위에 표본 외에서도 기여하는가.

    primary(금리결정)와 같은 원칙: 각 회의를 그 이전 회의들로만 학습해 예측한다.
    무작위 분할 금지(시계열).

    ★연속 변수라 지표가 다르다. 정확도가 아니라 **표본 외 R²** 를 쓴다:
        R²_oos = 1 - MSE(비교모형) / MSE(기준모형)
      기준은 B1(결정 + 사전기대) 이다 — "이미 아는 것" 대비 톤의 증분을 보는 것이므로
      단순 평균이 아니라 B1 을 기준으로 삼아야 질문과 맞는다.

    ★중첩 모형 비교에는 Clark-West 를 쓴다. 일반 Diebold-Mariano 는 중첩 관계에서
      검정 크기가 작아져(under-sized) 실제보다 보수적으로 나온다. Clark-West 는
      큰 모형이 표본 외에서 필연적으로 겪는 추정오차 페널티를 보정한다:
        f = e_r² - [e_u² - (yhat_r - yhat_u)²]
      평균 f 가 0보다 유의하게 크면 큰 모형이 낫다. HAC 표준오차로 t 검정.
    """
    import statsmodels.api as sm

    y_col = f"d2y_post{w}"
    base = ["dec_Hike", "dec_Cut", "d2y_pre20"]
    s = d.dropna(subset=base + ["stmt", y_col]).sort_values("date").reset_index(drop=True)
    n = len(s)
    if n <= min_train + 10:
        print("\n표본이 확장 윈도우에 부족합니다.")
        return

    y = s[y_col].astype(float).values
    er, eu, dhat = [], [], []
    for i in range(min_train, n):
        tr = s.iloc[:i]
        for cols, store in ((base, er), (base + ["stmt"], eu)):
            X = sm.add_constant(tr[cols].astype(float), has_constant="add")
            fit = sm.OLS(tr[y_col].astype(float), X).fit()
            xte = np.r_[1.0, s.iloc[i][cols].astype(float).values]
            store.append(y[i] - float(fit.params.values @ xte))
        dhat.append(er[-1] - eu[-1])          # yhat_u - yhat_r 과 부호만 다름

    er, eu, dhat = np.array(er), np.array(eu), np.array(dhat)
    mse_r, mse_u = float(np.mean(er ** 2)), float(np.mean(eu ** 2))
    r2_oos = 1 - mse_u / mse_r

    f = er ** 2 - (eu ** 2 - dhat ** 2)       # Clark-West 조정 손실차
    Xc = sm.add_constant(np.ones(len(f)), has_constant="add")[:, :1]
    cw = sm.OLS(f, Xc).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    t_cw, p_cw = float(cw.tvalues[0]), float(cw.pvalues[0]) / 2   # 단측

    print(f"\n[{w}거래일 반응]  확장 윈도우 표본 외 — 최초 학습 {min_train}건, "
          f"예측 {len(er)}건 ({s.date.iloc[min_train].date()} ~ {s.date.iloc[-1].date()})")
    print(f"  기준 B1(결정+사전기대) MSE  {mse_r:.6f}")
    print(f"  비교 B2(+성명문 톤)    MSE  {mse_u:.6f}")
    print(f"  표본 외 R²  {r2_oos:+.4f}   ({'개선' if r2_oos > 0 else '악화'})")
    print(f"  Clark-West  t={t_cw:.2f}  p={p_cw:.3f} (단측)")
    rows.append({"window_days": w, "model": "표본외 B1→B2", "n": len(er),
                 "r2": None, "delta_r2": round(r2_oos, 5),
                 "tone_coef": None, "tone_p_hac": round(p_cw, 4)})


def main():
    d = load()
    print("=" * 62)
    print("2년물 반응 — secondary outcome")
    print("=" * 62)
    print("검증: Fed 톤이 '발표된 결정 + 시장의 사전 기대' 위에 추가 정보를 주는가")

    rows: list = []
    for w in WINDOWS:
        run_window(d, w, rows)
    variant_grid(d, rows)

    print("\n" + "=" * 62)
    print("확장 윈도우 표본 외 검증")
    print("=" * 62)
    for w in WINDOWS:
        expanding_oos(d, w, rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print("\n  ΔR² 는 앞 모형 대비 증가분이다. 조교 피드백대로 R² 절대값만으로 "
          "의미를 주장하지 않는다 —\n  판단은 톤 계수의 부호·크기와 HAC p값으로 한다.")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
