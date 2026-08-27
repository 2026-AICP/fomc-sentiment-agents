"""신뢰도 게이트(min_articles · ci_max) 민감도 분석.

두 값은 2026-07-03 파일 생성 시 데이터 없이 찍은 잠정값이다(`news_signals.Thresholds`
docstring). 정상 수집이 3~4주 쌓이기 전에는 분위수 보정을 할 수 없으므로
(`docs/feedback_status.md` — 깨진 수집 기간을 임계값에 박아 넣게 된다),
그 사이 대안으로 **값에 결론이 얼마나 흔들리는지**를 본다.

`docs/signal_calibration.md` 의 θ 민감도 분석과 같은 논법이다 —
"완벽한 값 하나"가 아니라 "값에 안 흔들림"을 근거로 쓴다.

    python analysis/gate_sensitivity.py

읽기 전용이다. 임계값을 고치지 않고 표만 찍는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.news_signals import (          # noqa: E402
    DEFAULT, Thresholds, build_alerts, load_market_daily, load_series,
)

# θ 민감도 분석과 같은 배율 구간 (docs/signal_calibration.md)
MULTS = (0.5, 0.75, 1.0, 1.5, 2.0)
BASE_N, BASE_CI = DEFAULT.min_articles, DEFAULT.ci_max
LEVELS = ("🔴 경고", "⚠️ 주의", "🔵 관심", "🟢 안정", "⚪ 관망")

# 8월 수집 장애로 표본이 갈린다 — 같은 표에 섞으면 오염된 쪽이 결과를 만든다.
SPLIT = "2026-08-01"


def grade(series, market, n_min, ci_max):
    """(min_articles, ci_max) 한 조합의 날짜→등급."""
    th = Thresholds(min_articles=n_min, ci_max=ci_max)
    return {a.date: a.level for a in build_alerts(series, market, th)}


def _pct(part, whole):
    return f"{part / whole:.0%}" if whole else "-"


def table_dist(series, market, dates):
    """배율 격자 × 등급 분포."""
    print(f"\n{'min_art':>8} {'ci_max':>7} │ " + " ".join(f"{l:>7}" for l in LEVELS) + "  │ 기준선 대비 등급변동")
    print("─" * 78)
    base = grade(series, market, BASE_N, BASE_CI)
    for mn in MULTS:
        n_min = max(1, round(BASE_N * mn))
        for mc in MULTS:
            ci = round(BASE_CI * mc, 3)
            g = grade(series, market, n_min, ci)
            counts = [sum(1 for d in dates if g[d] == l) for l in LEVELS]
            moved = sum(1 for d in dates if g[d] != base[d])
            mark = "  ← 현재" if (n_min == BASE_N and ci == BASE_CI) else ""
            print(f"{n_min:>8} {ci:>7.2f} │ " + " ".join(f"{c:>7}" for c in counts)
                  + f"  │ {moved:>2}일 ({_pct(moved, len(dates))}){mark}")


def table_alarm_stability(series, market, dates):
    """경보(🔴·⚠️)가 배율 전 구간에서 유지되는지 — 결론이 값에 흔들리는가.

    등급을 매기지 못하는 조합(거의 전부 관망)은 제외한다. 게이트가 판별을 하는 게
    아니라 그냥 꺼져 있는 상태라, 포함하면 어떤 날도 '전 구간 유지'가 될 수 없다.
    """
    combos, grids, dead = [], [], []
    for mn in MULTS:
        for mc in MULTS:
            n, c = max(1, round(BASE_N * mn)), round(BASE_CI * mc, 3)
            g = grade(series, market, n, c)
            if sum(1 for d in dates if g[d] == "⚪ 관망") / len(dates) > 0.95:
                dead.append((n, c))
                continue
            combos.append((n, c))
            grids.append(g)
    if dead:
        cis = sorted({c for _, c in dead})
        print(f"\n제외한 축퇴 조합 {len(dead)}개 — ci_max {cis} 에서는 전 날짜가 관망이 된다.")
        print("  관측된 CI 폭 중앙값이 0.46 이라, 임계값을 그 아래로 내리면 게이트가 아니라 차단기가 된다.")

    print(f"\n경보일 안정성 — {len(combos)}개 조합 전체에서")
    print("─" * 78)
    rows = []
    for d in dates:
        levels = [g[d] for g in grids]
        alarm = sum(1 for l in levels if l in ("🔴 경고", "⚠️ 주의"))
        if alarm:
            rows.append((d, alarm, len(combos), grade(series, market, BASE_N, BASE_CI)[d]))
    if not rows:
        print("  경보가 뜬 날 없음")
        return
    print(f"{'날짜':<12} {'현재등급':<9} 경보로 판정한 조합")
    for d, a, tot, cur in rows:
        bar = "█" * round(a / tot * 20)
        print(f"{d:<12} {cur:<9} {a:>2}/{tot} {_pct(a, tot):>5} {bar}")
    always = sum(1 for _, a, tot, _ in rows if a == tot)
    print(f"\n  전 구간 유지: {always}/{len(rows)}일 — 나머지는 임계값에 따라 뒤집힌다")


def table_binding(series, dates):
    """어느 조건이 실제로 게이트를 거는가 — 기사수인가 CI인가."""
    print("\n어느 조건이 거는가 (현재값 15건·0.60 기준)")
    print("─" * 78)
    by_n = [r for r in series if r["date"] in dates and r["n_articles"] < BASE_N]
    ci_only = [r for r in series if r["date"] in dates
               and r["n_articles"] >= BASE_N
               and r["ci_hi"] == r["ci_hi"]
               and (r["ci_hi"] - r["ci_lo"]) > BASE_CI]
    n = len(dates)
    print(f"  기사수로 탈락      {len(by_n):>3}일 / {n}일 ({_pct(len(by_n), n)})")
    print(f"  CI 로만 추가 탈락  {len(ci_only):>3}일 / {n}일 ({_pct(len(ci_only), n)})")
    print(f"  통과               {n - len(by_n) - len(ci_only):>3}일 / {n}일")
    if by_n and not ci_only:
        print("  → 기사수 하한이 사실상 전부. ci_max 는 이 표본에서 거의 무의미하다.")


def table_sign_determinacy(series, dates):
    """게이트는 CI '폭'을 보는데, divergence·sign_flip 은 CI '부호'를 필요로 한다.

    폭이 좁아도 구간이 0 을 걸치면 지수가 양수인지 음수인지 알 수 없다. 그런 날에
    "뉴스는 긍정인데 시장은 하락" 을 주장하면 근거가 없는 것이다. 게이트는 이걸
    검사하지 않는다 — 설계상의 빈틈이라 여기 남긴다.
    """
    rows = [r for r in series if r["date"] in dates and r["ci_lo"] == r["ci_lo"]]
    spans = [r for r in rows if r["ci_lo"] < 0 < r["ci_hi"]]
    firm = [r for r in rows if r not in spans]
    firm_ok = [r for r in firm if r["n_articles"] >= BASE_N]

    print("\n부호 판정 가능성 — 게이트가 검사하지 않는 것")
    print("─" * 78)
    print(f"  CI 가 0 을 걸침 (부호 불명)   {len(spans):>3}일 / {len(rows)}일 ({_pct(len(spans), len(rows))})")
    print(f"  부호 확정                    {len(firm):>3}일")
    print(f"   └ 그중 기사 {BASE_N}건 이상      {len(firm_ok):>3}일  ← 부호 기반 신호를 믿을 수 있는 날")
    for r in firm_ok:
        print(f"      {r['date']}  지수 {r['value']:+.3f}  CI {r['ci_lo']:+.3f}~{r['ci_hi']:+.3f}  기사 {r['n_articles']}")
    print("\n  ※ divergence·sign_flip 은 지수의 부호로 판정한다. 위 날짜 밖에서 나온")
    print("     경보는 부호가 뒤집힐 수 있다 — ci_max 를 아무리 조여도 잡히지 않는다.")


def main():
    series = load_series()
    market = load_market_daily([r["date"] for r in series])
    dates = [r["date"] for r in series]
    jul = [d for d in dates if d < SPLIT]
    aug = [d for d in dates if d >= SPLIT]

    print(f"표본 {dates[0]} ~ {dates[-1]} · {len(dates)}일 "
          f"(7월 {len(jul)}일 · 8월 {len(aug)}일)")
    print(f"현재 잠정값: min_articles={BASE_N} · ci_max={BASE_CI}")
    print(f"배율 구간 {MULTS[0]}~{MULTS[-1]} (docs/signal_calibration.md 와 동일)")

    for label, sub in (("전체", dates), ("7월 (수집 정상)", jul), ("8월 (수집 장애)", aug)):
        if len(sub) < 5:
            continue
        print(f"\n\n{'=' * 78}\n■ {label} — {len(sub)}일\n{'=' * 78}")
        table_dist(series, market, sub)
        table_binding(series, sub)

    print(f"\n\n{'=' * 78}\n■ 결론 판정 — 경보가 값에 흔들리는가\n{'=' * 78}")
    table_alarm_stability(series, market, dates)
    table_sign_determinacy(series, dates)


if __name__ == "__main__":
    main()
