"""다항 로지스틱 회귀 — 감성지수가 금리결정을 설명하는가.

조교 피드백(2026-08): 금리 결정은 인상·동결·인하 3분류라 OLS 가 부적절 →
다항 로지스틱. 표본 분할은 시계열이므로 무작위 금지 → **확장 윈도우**.

★설계의 핵심은 "무엇과 비교하는가"다. 감성지수만 넣고 정확도 80% 가 나왔다고
설명력이 있는 게 아니다. 연준 결정은 사이클로 움직여 **직전 결정을 반복만 해도
80.5%** 다(policy_freq.py). 그래서 중첩 모형을 순서대로 쌓아, 각 단계가 **앞 단계
위에서 무엇을 더 설명하는지**만 본다:

  M0  지속성        직전 결정만 — 이게 이길 대상
  M1  + 시장기대    회의 전 2년물 변화 (시장이 이미 반영한 부분)
  M2  + Fed 톤      직전 회의 성명문·회의록
  M3  + 뉴스        직전 완결월 뉴스 지수

M2 가 M1 을 못 이기면 "감성지수는 시장이 아는 것 이상을 말하지 않는다"가 결론이다.
그것도 정직한 결과이므로 그대로 보고한다.

★R² 해석 주의(조교 피드백): 사회과학 자료에서 낮은 McFadden pseudo-R² 는 실패가
아니다. 0.2~0.4 면 이미 매우 좋은 적합으로 본다. 절대값이 아니라 **모형 간 차이**로 읽는다.

★표준화 시점: 확장 윈도우의 각 단계에서 **그 시점까지의 과거로만** 평균·표준편차를
구한다. 전체 표본으로 표준화하면 미래 정보가 새어 들어간다(look-ahead).

실행:  python3 analysis/policy_logit.py
산출:  outputs/policy_logit_insample.csv · outputs/policy_logit_oos.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "outputs" / "policy_dataset.csv"
OUT_IN = ROOT / "outputs" / "policy_logit_insample.csv"
OUT_OOS = ROOT / "outputs" / "policy_logit_oos.csv"

ORDER = ["Cut", "Hold", "Hike"]
MIN_TRAIN = 80          # 확장 윈도우 최초 학습 표본(회의) — 3클래스가 다 들어갈 만큼
EPS = 1e-12

# 중첩 모형 — 사전에 고정한다. 변수 조합을 뒤져 좋은 걸 고르지 않는다(과적합·다중비교).
#
# ★트랙이 둘인 이유: 뉴스 축(WSJ)은 2021-05 에서 끝난다. 뉴스를 포함하면 모형 간
#   비교를 위해 표본을 169건으로 맞춰야 하고, **2022~2023 인상 사이클이 통째로 빠진다**
#   — 정책이 가장 역동적이던 구간을 검증에서 제외하는 셈이다. 그래서 Fed 축만 쓰는
#   트랙(전 구간 2026까지)과 뉴스까지 넣는 트랙(2021까지)을 나란히 돌린다.
TRACKS = {
    "Fed 축 (전 구간)": [
        ("M0 지속성",    []),
        ("M1 +시장기대", ["d2y_pre20"]),
        ("M2 +Fed톤",    ["d2y_pre20", "stmt_prev", "minutes_prev"]),
    ],
    "뉴스 포함 (2021까지)": [
        ("M0 지속성",    []),
        ("M1 +시장기대", ["d2y_pre20"]),
        ("M2 +Fed톤",    ["d2y_pre20", "stmt_prev", "minutes_prev"]),
        ("M3 +뉴스",     ["d2y_pre20", "stmt_prev", "minutes_prev", "news_pre"]),
    ],
}
BASE_DUMMIES = ["prev_Cut", "prev_Hike"]   # prev_Hold 를 기준범주로 뺀다


def load() -> pd.DataFrame:
    if not DATA.exists():
        raise SystemExit(f"{DATA} 없음 — 먼저 analysis/policy_dataset.py 를 실행하세요.")
    d = pd.read_csv(DATA, parse_dates=["date"])
    d["prev_Cut"] = (d.prev_dec == "Cut").astype(float)
    d["prev_Hike"] = (d.prev_dec == "Hike").astype(float)
    return d


def _design(d: pd.DataFrame, cols: list):
    """결측 제거 후 (X, y, 사용행). 모형마다 표본이 달라지면 비교가 깨지므로 주의."""
    need = cols + BASE_DUMMIES + ["decision"]
    sub = d.dropna(subset=need)
    X = sub[BASE_DUMMIES + cols].astype(float).values
    y = sub.decision.values
    return X, y, sub


def _fit_predict(Xtr, ytr, Xte):
    """L2 다항 로지스틱. 표준화는 학습 구간 통계로만 한다(호출자가 이미 처리)."""
    from sklearn.linear_model import LogisticRegression
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = LogisticRegression(max_iter=2000, C=1.0)
        m.fit(Xtr, ytr)
    proba = pd.DataFrame(m.predict_proba(Xte), columns=list(m.classes_))
    for k in ORDER:                      # 학습에 없던 클래스는 0 확률로 채워 열 고정
        if k not in proba.columns:
            proba[k] = 0.0
    return proba[ORDER].values


def _logloss(proba, y):
    idx = {k: i for i, k in enumerate(ORDER)}
    p = np.array([proba[i, idx[v]] for i, v in enumerate(y)])
    return float(-np.mean(np.log(np.clip(p, EPS, 1))))


def _fit_mnlogit(sm, y, X, name: str):
    """MNLogit 적합 — 기본 뉴턴법이 실패하면 BFGS 로 재시도.

    3분류 자료에서 특정 조합(예: 인상기에 prev_Hike 더미)이 거의 완전분리에 가까워지면
    뉴턴법이 발산해 llf 가 nan 이 된다. 준-분리는 자료의 성질이지 버그가 아니므로,
    더 안정적인 최적화로 한 번 더 시도하고 그래도 안 되면 **실패를 명시**한다.
    """
    for method, iters in (("newton", 200), ("bfgs", 2000)):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                res = sm.MNLogit(y, X).fit(disp=0, method=method, maxiter=iters)
            except Exception:
                continue
        if np.isfinite(res.llf) and np.isfinite(res.prsquared):
            if method != "newton":
                print(f"    ({name}: 뉴턴법 수렴 실패 → BFGS 로 재적합)")
            return res
    return None


# ── 표본 내 적합 (계수·pseudo-R²·우도비 검정) ────────────────────────────
def insample(d: pd.DataFrame, models: list, track: str) -> pd.DataFrame:
    import statsmodels.api as sm

    # 모형 간 비교가 성립하려면 **같은 표본**이어야 한다 → 최대 모형 기준으로 행을 맞춘다.
    _, _, common = _design(d, models[-1][1])
    print("\n" + "=" * 66)
    print(f"[{track}]  표본 내 적합 — 회의 {len(common)}건 "
          f"({common.date.min().date()} ~ {common.date.max().date()})")
    print("=" * 66)
    print("  ※ 모형 간 비교를 위해 그 트랙의 최대 모형 기준으로 표본을 통일했다\n")

    rows, prev = [], None
    print(f"  {'모형':<14}{'변수':>4}{'pseudo-R²':>11}{'LL':>10}{'vs 앞 모형':>22}")
    print("  " + "-" * 62)
    for name, cols in models:
        X = sm.add_constant(common[BASE_DUMMIES + cols].astype(float).values, has_constant="add")
        res = _fit_mnlogit(sm, common.decision.values, X, name)
        if res is None:                       # 수렴 실패는 nan 으로 흘리지 않고 명시한다
            print(f"  {name:<14}{len(cols):>4}{'수렴 실패':>11}")
            rows.append({"track": track, "model": name, "n_vars": len(cols),
                         "pseudo_r2": None, "loglik": None,
                         "lr_vs_prev": "수렴 실패", "n": len(common)})
            prev = None                       # 다음 모형의 LR 검정도 끊는다
            continue
        k = X.shape[1]
        lr = ""
        if prev is not None:
            from scipy import stats as st
            stat = 2 * (res.llf - prev[0])
            df = (k - prev[1]) * 2                    # 3클래스 → 방정식 2개
            lr = f"LR={stat:5.1f} df={df} p={st.chi2.sf(max(stat, 0), df):.3f}"
        print(f"  {name:<14}{len(cols):>4}{res.prsquared:>11.3f}{res.llf:>10.1f}{lr:>22}")
        rows.append({"track": track, "model": name, "n_vars": len(cols),
                     "pseudo_r2": round(res.prsquared, 4), "loglik": round(res.llf, 2),
                     "lr_vs_prev": lr, "n": len(common)})
        prev = (res.llf, k)
    print("\n  pseudo-R² 는 절대값이 아니라 모형 간 차이로 읽는다 "
          "(사회과학에서 0.2~0.4 면 좋은 적합).")
    return pd.DataFrame(rows)


# ── 확장 윈도우 표본 외 검증 ────────────────────────────────────────────
def expanding_oos(d: pd.DataFrame, models: list, track: str) -> pd.DataFrame:
    """각 회의를 그 이전 회의들로만 학습해 예측. 무작위 분할 금지(시계열)."""
    _, _, common = _design(d, models[-1][1])
    common = common.sort_values("date").reset_index(drop=True)
    n = len(common)
    if n <= MIN_TRAIN + 10:
        raise SystemExit("표본이 확장 윈도우에 부족합니다.")

    print(f"\n[{track}]  확장 윈도우 표본 외 — 최초 학습 {MIN_TRAIN}건, "
          f"예측 대상 {n - MIN_TRAIN}건 ({common.date.iloc[MIN_TRAIN].date()} ~ "
          f"{common.date.iloc[-1].date()})")

    y_true = common.decision.values[MIN_TRAIN:]
    # 지속성 기준선 — 직전 결정을 그대로 예측
    persist = common.prev_dec.values[MIN_TRAIN:]

    rows = []
    print(f"\n  {'모형':<14}{'정확도':>9}{'로그손실':>11}{'macro-F1':>11}")
    print("  " + "-" * 46)
    acc_p = float(np.mean(persist == y_true))
    from sklearn.metrics import f1_score
    f1_p = f1_score(y_true, persist, average="macro", zero_division=0)
    print(f"  {'기준선 지속성':<14}{acc_p:>9.1%}{'—':>11}{f1_p:>11.3f}")
    rows.append({"track": track, "model": "기준선 지속성", "accuracy": round(acc_p, 4),
                 "logloss": None, "macro_f1": round(f1_p, 4), "n_test": len(y_true)})

    for name, cols in models:
        feats = BASE_DUMMIES + cols
        preds, probas = [], []
        for i in range(MIN_TRAIN, n):
            tr, te = common.iloc[:i], common.iloc[i:i + 1]
            Xtr = tr[feats].astype(float).values
            Xte = te[feats].astype(float).values
            mu, sd = Xtr.mean(0), Xtr.std(0)          # 과거 구간으로만 표준화
            sd = np.where(sd < 1e-9, 1.0, sd)
            p = _fit_predict((Xtr - mu) / sd, tr.decision.values, (Xte - mu) / sd)
            probas.append(p[0])
            preds.append(ORDER[int(np.argmax(p[0]))])
        probas = np.array(probas)
        acc = float(np.mean(np.array(preds) == y_true))
        ll = _logloss(probas, y_true)
        f1 = f1_score(y_true, preds, average="macro", zero_division=0)
        print(f"  {name:<14}{acc:>9.1%}{ll:>11.3f}{f1:>11.3f}")
        rows.append({"track": track, "model": name, "accuracy": round(acc, 4),
                     "logloss": round(ll, 4), "macro_f1": round(f1, 4), "n_test": len(y_true)})

    print("\n  로그손실은 낮을수록 좋다 — 정확도와 달리 확률의 질까지 본다"
          "(불균형 자료에서 정확도만 보면 오해가 생긴다).")
    return pd.DataFrame(rows)


def main():
    d = load()
    ins_all, oos_all = [], []
    for track, models in TRACKS.items():
        ins_all.append(insample(d, models, track))
        oos_all.append(expanding_oos(d, models, track))
    ins = pd.concat(ins_all, ignore_index=True)
    oos = pd.concat(oos_all, ignore_index=True)
    OUT_IN.parent.mkdir(parents=True, exist_ok=True)
    ins.to_csv(OUT_IN, index=False)
    oos.to_csv(OUT_OOS, index=False)
    print(f"\n→ {OUT_IN}\n→ {OUT_OOS}")


if __name__ == "__main__":
    main()
