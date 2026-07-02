"""
Phase 6 — 백테스트 하네스 (합격선: 신호 적중률 vs 단순보유)

우리 신호는 방향을 '예측'하지 않는다(signal_design.md §1-A). 따라서 '적중'을
방향 맞춤이 아니라 **위험사건**으로 조작적 정의한다:

  위험사건 = 발표 후 N거래일 내 최대낙폭(max drawdown)이
             전체 회의 중 상위 tertile(상위 1/3)에 드는 것.   (주지표)
             |누적수익률|(방식 A)도 보조로 함께 산출.

  적중률   = P(위험사건 | 신호 발동).  Wilson 신뢰구간 + 표본 수 병기.
  단순보유 = 아무 신호 없이 그냥 보유했을 때의 위험사건 기저율(tertile상 ≈1/3).
             신호가 정보를 가지려면 적중률이 기저율보다 유의하게 높아야 한다.

벤치마크(§4): ① 단순보유(기저율) ② 무작위 신호(몬테카를로) ③ 금리결정만(FRED 필요, 훅만).
정직성: CI가 무작위 분포와 겹치면 "신호 없음"이 정직한 결론. 국면(긴축/완화)별 분리.

순수 함수(테스트 쉬움) + DB 러너로 분리. 실행: python3 analysis/backtest.py
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Sequence

N_DAYS = 2               # 신호기간: 발표 후 N거래일 관찰
TOP_TERTILE = 2.0 / 3.0  # 위험사건 컷: 상위 1/3


# ---------------------------------------------------------------------------
# 결과 측정 — 발표 후 창(window)의 낙폭·수익률
# ---------------------------------------------------------------------------
def max_drawdown(closes: Sequence[float]) -> float:
    """일별 종가 시계열의 최대낙폭 크기(양수 %)를 반환.

    closes[0] = 발표일 종가를 기준점으로, 이후 running-peak 대비 최대 하락폭.
    반환값은 양수 %(예: 2.5 = 고점 대비 -2.5%). 데이터 부족 시 0.
    """
    if not closes or len(closes) < 2:
        return 0.0
    peak = closes[0]
    mdd = 0.0
    for c in closes[1:]:
        peak = max(peak, c)
        dd = c / peak - 1.0        # <= 0
        mdd = min(mdd, dd)
    return abs(mdd) * 100.0


def abs_cum_return(closes: Sequence[float]) -> float:
    """창 시작→끝 누적수익률의 절대값(%). 방향 무관 '큰 움직임' 보조지표."""
    if not closes or len(closes) < 2 or closes[0] == 0:
        return 0.0
    return abs(closes[-1] / closes[0] - 1.0) * 100.0


def tertile_cutoff(values: Sequence[float], q: float = TOP_TERTILE) -> float:
    """전체 회의 지표값에서 상위 tertile 컷오프(q 분위수). 상대순위라 시대보정."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return float("inf")
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def risk_flags(outcomes: Sequence[float], q: float = TOP_TERTILE) -> List[bool]:
    """각 회의가 위험사건인지(지표값 >= 상위 tertile 컷) 불리언 리스트."""
    cut = tertile_cutoff(outcomes, q)
    return [(o is not None and o >= cut) for o in outcomes]


# ---------------------------------------------------------------------------
# 적중률 + 신뢰구간
# ---------------------------------------------------------------------------
def wilson_interval(k: int, n: int, z: float = 1.96):
    """이항비율 k/n 의 Wilson 95% 신뢰구간 (표본 작을 때도 안정)."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


@dataclass
class HitResult:
    n_fired: int          # 신호 발동 회의 수
    n_hit: int            # 그 중 위험사건 수
    hit_rate: float       # 적중률
    ci_low: float
    ci_high: float
    base_rate: float      # 단순보유 기저율(전체 위험사건 비율)
    lift: float           # 적중률 - 기저율 (양수면 정보 있음 방향)
    rand_mean: float      # 무작위 신호 평균 적중률
    rand_p: float         # 무작위가 관측만큼 잘 맞출 확률(경험적 p값)


def evaluate(fired: Sequence[bool], risk: Sequence[bool],
             trials: int = 5000, seed: int = 0) -> HitResult:
    """신호 발동(fired) vs 위험사건(risk) 을 대조해 적중률·기저율·무작위 벤치마크 산출.

    무작위 신호: 같은 개수(n_fired)의 회의를 무작위로 골라 적중률 분포를 만들고,
    관측 적중 수 이상을 무작위가 낼 확률(rand_p)을 경험적으로 잰다.
    rand_p 가 크면(예: >0.05) "무작위와 구별 안 됨 = 신호 없음".
    """
    n = len(fired)
    idx_hit = [i for i in range(n) if risk[i]]
    base_rate = len(idx_hit) / n if n else 0.0

    n_fired = sum(fired)
    n_hit = sum(1 for i in range(n) if fired[i] and risk[i])
    hit_rate, lo, hi = wilson_interval(n_hit, n_fired)

    # 무작위 벤치마크
    rng = random.Random(seed)
    total_risk = len(idx_hit)
    ge = 0
    acc = 0.0
    if n_fired == 0 or n == 0:
        rand_mean, rand_p = 0.0, 1.0
    else:
        for _ in range(trials):
            picks = rng.sample(range(n), n_fired)
            h = sum(1 for i in picks if risk[i])
            acc += h
            if h >= n_hit:
                ge += 1
        rand_mean = (acc / trials) / n_fired
        rand_p = ge / trials
    return HitResult(n_fired, n_hit, hit_rate, lo, hi,
                     base_rate, hit_rate - base_rate, rand_mean, rand_p)


# ---------------------------------------------------------------------------
# 간단 룰전략 vs 단순보유 (이벤트 단위)
#   market 이 회의 ±7일 창만 있어 연속 시계열이 아니므로, 이벤트 단위로 비교한다.
#   - 단순보유: 매 회의의 N일 수익을 그대로 얻음.
#   - 신호전략: 🔴경고(alert) 회의는 그 창을 쉼(현금=0), 나머지는 보유.
# ---------------------------------------------------------------------------
@dataclass
class StrategyResult:
    n: int
    hold_mean_ret: float      # 단순보유 평균 N일 수익률(%)
    signal_mean_ret: float    # 신호전략 평균 N일 수익률(%)
    hold_mean_dd: float       # 단순보유 평균 낙폭(%)
    avoided_dd: float         # 신호전략이 피한 평균 낙폭(%) (양수면 낙폭 회피)


def strategy_vs_hold(event_rets: Sequence[float], event_dds: Sequence[float],
                     alert: Sequence[bool]) -> StrategyResult:
    n = len(event_rets)
    if n == 0:
        return StrategyResult(0, 0, 0, 0, 0)
    hold_ret = sum(event_rets) / n
    sig_ret = sum(r for r, a in zip(event_rets, alert) if not a) / n  # 경고창은 0
    hold_dd = sum(event_dds) / n
    # 신호전략이 실제로 겪은 낙폭(경고창은 0) → 회피분 = 단순보유 - 신호전략
    sig_dd = sum(d for d, a in zip(event_dds, alert) if not a) / n
    return StrategyResult(n, hold_ret, sig_ret, hold_dd, hold_dd - sig_dd)


# ---------------------------------------------------------------------------
# 국면(regime) 태그 — 톤↔시장 관계가 국면마다 뒤집힘(§1-A) → 분리 집계용.
#   거친 휴리스틱(연도 기반 연준 긴축/완화기). 표본 작아 '경향'으로만.
# ---------------------------------------------------------------------------
_TIGHTENING_YEARS = set(range(1999, 2001)) | {2004, 2005, 2006} | {2015, 2016, 2017, 2018} | {2022, 2023}
_EASING_YEARS = {2001, 2002, 2003, 2007, 2008, 2009, 2019, 2020}


def regime_of(date: str) -> str:
    """YYYY-MM-DD → '긴축' | '완화' | '중립' (거친 연도 기반)."""
    try:
        y = int(date[:4])
    except (ValueError, IndexError):
        return "중립"
    if y in _TIGHTENING_YEARS:
        return "긴축"
    if y in _EASING_YEARS:
        return "완화"
    return "중립"


# ---------------------------------------------------------------------------
# DB 러너 — 실제 데이터로 위 함수들을 엮어 백테스트 실행
# ---------------------------------------------------------------------------
def load_outcomes(con, dates: Sequence[str], n_days: int = N_DAYS):
    """각 회의일 이후 n_days 거래일의 종가 창으로 (낙폭, |수익률|)을 계산.

    market 은 거래일만 있으므로 date >= 회의일 을 정렬해 앞 n_days+1개를 창으로 쓴다.
    반환: (drawdowns, abs_returns) — 창 부족 회의는 None.
    """
    dds, rets = [], []
    for d in dates:
        rows = con.execute(
            "SELECT spx_close FROM market WHERE date >= ? AND spx_close IS NOT NULL "
            "ORDER BY date LIMIT ?",
            (d, n_days + 1),
        ).fetchall()
        closes = [r[0] for r in rows]
        if len(closes) < 2:
            dds.append(None)
            rets.append(None)
        else:
            dds.append(max_drawdown(closes))
            rets.append(abs_cum_return(closes))
    return dds, rets


def run_backtest(con, agg_method: str = "conf_weighted",
                 reaction_offset: int = 1, n_days: int = N_DAYS,
                 report_dir=None):
    """백테스트 실행. 콘솔 출력 + (report_dir 주면) 마크다운 리포트 저장.

    반환: 리포트 경로(또는 None).
    """
    from analysis.signals import load_series, build_alerts, Thresholds

    L: List[str] = []   # 리포트/콘솔 공용 줄 버퍼
    def emit(line=""):
        print(line)
        L.append(line)

    series = load_series(con, agg_method, reaction_offset)
    if not series:
        print("meetings 톤이 없습니다. pipeline → collect_market 을 먼저 실행하세요.")
        return None

    dates = [s["date"] for s in series]
    alerts = build_alerts(series, Thresholds(), small_sample=len(series) < 30)

    # 결과 측정 + 위험사건 판정 (창이 있는 회의만 유효)
    dds, rets = load_outcomes(con, dates, n_days)
    valid = [i for i in range(len(dates)) if dds[i] is not None]
    if len(valid) < 3:
        print(f"유효 창을 가진 회의가 {len(valid)}건뿐 — market 수집을 확인하세요.")
        return None

    v_dd = [dds[i] for i in valid]
    risk_dd = risk_flags(v_dd)                          # 주지표: 낙폭 tertile
    risk_map = {valid[j]: risk_dd[j] for j in range(len(valid))}

    emit(f"# Phase 6 백테스트 — 신호 적중률 vs 단순보유")
    emit()
    emit(f"- 회의 {len(dates)}건 (유효 창 {len(valid)}건), 톤 집계={agg_method}, 신호기간 N={n_days}거래일")
    emit(f"- 위험사건 정의: 발표후 {n_days}일 최대낙폭 상위 tertile (기저율 ≈ 33%)")
    emit()

    # 신호별 적중률
    emit("## 1. 신호별 적중률 (vs 기저율·무작위)")
    emit()
    emit("| 신호 | 발동 | 적중 | 적중률 (95% CI) | 기저율 | lift | 무작위 p | 판정 |")
    emit("|---|--:|--:|---|--:|--:|--:|---|")
    for name in ("divergence", "tone_vs_vix", "tone_shift"):
        fired = [any(s.name == name and s.fired for s in alerts[i].signals) for i in valid]
        risk = [risk_map[i] for i in valid]
        res = evaluate(fired, risk)
        emit(f"| {name} | {res.n_fired} | {res.n_hit} | "
             f"{res.hit_rate:.0%} ({res.ci_low:.0%}~{res.ci_high:.0%}) | "
             f"{res.base_rate:.0%} | {res.lift:+.0%} | {res.rand_p:.3f} | {_verdict(res)} |")
    emit()

    # 룰전략 vs 단순보유 (🔴 경고창 회피)
    ev_ret = []  # 부호있는 N일 수익률
    for i in valid:
        rows = con.execute(
            "SELECT spx_close FROM market WHERE date >= ? AND spx_close IS NOT NULL "
            "ORDER BY date LIMIT ?", (dates[i], n_days + 1)).fetchall()
        closes = [r[0] for r in rows]
        ev_ret.append((closes[-1] / closes[0] - 1.0) * 100.0 if len(closes) >= 2 else 0.0)
    ev_dd = [dds[i] for i in valid]
    alert_flags = [alerts[i].grade == "🔴 경고" for i in valid]
    st = strategy_vs_hold(ev_ret, ev_dd, alert_flags)
    n_alert = sum(alert_flags)
    emit("## 2. 룰전략 vs 단순보유 (🔴 경고창 회피)")
    emit()
    emit(f"- 🔴 경고 {n_alert}건 창을 현금으로 회피")
    emit(f"- 평균 N일 수익률: 단순보유 {st.hold_mean_ret:+.2f}% | 신호전략 {st.signal_mean_ret:+.2f}%")
    emit(f"- 평균 낙폭: 단순보유 {st.hold_mean_dd:.2f}% | 신호전략이 피한 낙폭 {st.avoided_dd:+.2f}%")
    emit()

    # 국면별 분리 (괴리 신호)
    emit("## 3. 국면별 괴리 적중률 (긴축/완화 — 표본 작아 '경향')")
    emit()
    emit("| 국면 | 회의 | 괴리발동 | 적중률 | 기저율 |")
    emit("|---|--:|--:|--:|--:|")
    for reg in ("긴축", "완화", "중립"):
        sub = [i for i in valid if regime_of(dates[i]) == reg]
        if not sub:
            continue
        fired = [any(s.name == "divergence" and s.fired for s in alerts[i].signals) for i in sub]
        risk = [risk_map[i] for i in sub]
        res = evaluate(fired, risk, trials=2000)
        emit(f"| {reg} | {len(sub)} | {res.n_fired} | {res.hit_rate:.0%} | {res.base_rate:.0%} |")
    emit()
    emit("> ※ 표본이 작으면 CI가 넓고 p값이 커진다. 무작위와 구별 안 되면 **'신호 없음'이 정직한 결론**이다.")

    if report_dir is not None:
        from pathlib import Path
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        out = report_dir / "phase6_backtest.md"
        out.write_text("\n".join(L), encoding="utf-8")
        print(f"\n리포트 저장: {out}")
        return out
    return None


def _verdict(res: HitResult) -> str:
    if res.n_fired < 3:
        return "표본 부족(판정 보류)"
    if res.rand_p <= 0.05 and res.lift > 0:
        return "무작위 대비 유의(신호 후보)"
    return "무작위와 구별 어려움(신호 근거 약함)"


def main():
    import sqlite3
    import sys
    from pathlib import Path
    try:  # Windows cp949 콘솔에서도 이모지 출력되게
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 직접 실행 대비
    from analysis.analyze_alignment import DB_PATH
    con = sqlite3.connect(DB_PATH)
    run_backtest(con, report_dir="reports/out")
    con.close()


if __name__ == "__main__":
    main()
