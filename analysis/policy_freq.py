"""조건부 빈도표 — 금리결정이 예측자 구간별로 어떻게 갈리는가.

조교 피드백(2026-08): "조건부 빈도표는 좋은 접근이니 살릴 것."
다항 로지스틱(policy_logit.py)에 들어가기 전에 **모형 없이 먼저 보는** 단계다.
회귀 계수는 해석이 어렵지만 빈도표는 그대로 읽힌다 — 그리고 여기서 안 보이는
구조는 회귀에서도 대개 안 나온다.

읽는 법: 각 행은 예측자 구간, 각 칸은 그 구간에서 해당 결정이 나온 비율이다.
맨 위 '전체' 행(주변분포)과 비교해서 **얼마나 벗어나는가**가 정보량이다.
전체와 비슷하면 그 예측자는 결정에 대해 말해주는 게 없다.

예측자는 전부 회의 전 시점 정보다(policy_dataset.py 의 시점 규칙 참조).

실행:  python3 analysis/policy_freq.py
산출:  outputs/policy_freq.csv  (모든 표를 long 형식으로 이어붙임)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "outputs" / "policy_dataset.csv"
OUT = ROOT / "outputs" / "policy_freq.csv"
ORDER = ("Cut", "Hold", "Hike")
N_BINS = 3          # 3분위 — 221건에서 구간당 ~74건. 4분위는 칸이 얇아진다.
MIN_CELL = 5        # 카이제곱 기대빈도 경고 기준


# 예측자 설명 — 표 제목에 그대로 쓴다
PREDICTORS = [
    ("stmt_prev",   "직전 회의 성명문 톤"),
    ("minutes_prev", "직전 회의 회의록 톤"),
    ("presser_prev", "직전 회의 기자회견 톤"),
    ("news_pre",    "직전 완결월 뉴스 지수"),
    ("d2y_pre5",    "회의 전 5거래일 2년물 변화"),
    ("d2y_pre20",   "회의 전 20거래일 2년물 변화"),
]


def load() -> pd.DataFrame:
    if not DATA.exists():
        raise SystemExit(f"{DATA} 없음 — 먼저 analysis/policy_dataset.py 를 실행하세요.")
    return pd.read_csv(DATA, parse_dates=["date"])


def _bin_labels(s: pd.Series, k: int):
    """분위 구간 라벨 — 경계값을 함께 보여줘야 해석이 된다."""
    try:
        cats, edges = pd.qcut(s, k, retbins=True, duplicates="drop")
    except ValueError:
        return None, None
    names = [f"{i+1}분위 [{edges[i]:+.3f}, {edges[i+1]:+.3f}]" for i in range(len(edges) - 1)]
    return cats.cat.rename_categories(names), names


def crosstab(d: pd.DataFrame, col: str, label: str, rows: list) -> None:
    sub = d.dropna(subset=[col, "decision"])
    if len(sub) < N_BINS * 10:
        print(f"\n[{label}] 표본 {len(sub)}건 — 너무 적어 생략")
        return
    binned, _ = _bin_labels(sub[col], N_BINS)
    if binned is None:
        print(f"\n[{label}] 분위 경계 생성 실패(값이 뭉쳐 있음) — 생략")
        return

    ct = pd.crosstab(binned, sub.decision)
    for k in ORDER:                       # 없는 결정 클래스도 0으로 채워 열 순서 고정
        if k not in ct.columns:
            ct[k] = 0
    ct = ct[list(ORDER)]
    pct = ct.div(ct.sum(axis=1), axis=0)

    print(f"\n[{label}]   n={len(sub)}")
    print(f"  {'구간':<28}{'Cut':>8}{'Hold':>8}{'Hike':>8}{'n':>6}")
    base = sub.decision.value_counts(normalize=True)
    print(f"  {'전체(주변분포)':<28}"
          f"{base.get('Cut', 0):>8.1%}{base.get('Hold', 0):>8.1%}{base.get('Hike', 0):>8.1%}"
          f"{len(sub):>6}")
    print(f"  {'-' * 56}")
    for idx in ct.index:
        print(f"  {str(idx):<28}"
              f"{pct.loc[idx, 'Cut']:>8.1%}{pct.loc[idx, 'Hold']:>8.1%}{pct.loc[idx, 'Hike']:>8.1%}"
              f"{int(ct.loc[idx].sum()):>6}")
        for k in ORDER:
            rows.append({"table": label, "bin": str(idx), "decision": k,
                         "n": int(ct.loc[idx, k]), "share": round(float(pct.loc[idx, k]), 4)})

    chi2, p, dof, exp = stats.chi2_contingency(ct)
    v = np.sqrt(chi2 / (ct.values.sum() * (min(ct.shape) - 1)))     # Cramér's V
    thin = int((exp < MIN_CELL).sum())
    note = f"  ※ 기대빈도 {MIN_CELL} 미만 칸 {thin}개 — p값 신뢰 낮음" if thin else ""
    print(f"  카이제곱 p={p:.3f} · Cramér's V={v:.3f}{note}")


def persistence_table(d: pd.DataFrame, rows: list) -> None:
    """P(이번 결정 | 직전 결정) — 지속성 구조 자체를 먼저 보여준다.

    이게 80.5% 기준선의 정체다. 다른 예측자는 이 구조 '위에서' 추가 정보를 줘야 한다.
    """
    sub = d.dropna(subset=["prev_dec", "decision"])
    ct = pd.crosstab(sub.prev_dec, sub.decision)
    for k in ORDER:
        if k not in ct.columns:
            ct[k] = 0
    ct = ct.reindex(index=[k for k in ORDER if k in ct.index])[list(ORDER)]
    pct = ct.div(ct.sum(axis=1), axis=0)

    print(f"\n[직전 결정 → 이번 결정]   n={len(sub)}")
    print(f"  {'직전':<28}{'Cut':>8}{'Hold':>8}{'Hike':>8}{'n':>6}")
    print(f"  {'-' * 56}")
    for idx in ct.index:
        print(f"  {idx:<28}"
              f"{pct.loc[idx, 'Cut']:>8.1%}{pct.loc[idx, 'Hold']:>8.1%}{pct.loc[idx, 'Hike']:>8.1%}"
              f"{int(ct.loc[idx].sum()):>6}")
        for k in ORDER:
            rows.append({"table": "직전 결정", "bin": idx, "decision": k,
                         "n": int(ct.loc[idx, k]), "share": round(float(pct.loc[idx, k]), 4)})
    print(f"  대각선(반복) 비율 = {np.trace(ct.values) / ct.values.sum():.1%}")


def main():
    d = load()
    rows: list = []
    print("=" * 62)
    print("조건부 빈도표 — 금리결정 (Cut / Hold / Hike)")
    print("=" * 62)
    persistence_table(d, rows)
    for col, label in PREDICTORS:
        if col in d.columns:
            crosstab(d, col, label, rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\n※ 예측자 {len(PREDICTORS)}개를 각각 검정했다 — 다중비교이므로 "
          f"개별 p값이 아니라 전체 패턴으로 읽을 것.")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
