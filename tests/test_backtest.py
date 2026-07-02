"""백테스트 순수 함수 단위테스트 (합성 데이터, 결정적, 네트워크·DB 없음)."""
import math

from analysis.backtest import (
    max_drawdown,
    abs_cum_return,
    tertile_cutoff,
    risk_flags,
    wilson_interval,
    evaluate,
    strategy_vs_hold,
    regime_of,
)


# --- 결과 측정 --------------------------------------------------------------
def test_max_drawdown_basic():
    # 100 → 110 → 99: 고점 110 대비 저점 99 = -10%
    assert math.isclose(max_drawdown([100, 110, 99]), 10.0, rel_tol=1e-9)

def test_max_drawdown_monotonic_up_is_zero():
    assert max_drawdown([100, 101, 102]) == 0.0

def test_max_drawdown_too_short():
    assert max_drawdown([100]) == 0.0

def test_abs_cum_return_direction_agnostic():
    assert math.isclose(abs_cum_return([100, 98]), 2.0, rel_tol=1e-9)
    assert math.isclose(abs_cum_return([100, 102]), 2.0, rel_tol=1e-9)


# --- tertile / 위험사건 -----------------------------------------------------
def test_tertile_cutoff_and_flags():
    vals = [1, 2, 3, 4, 5, 6]      # 상위 1/3 컷 ≈ 4.33
    flags = risk_flags(vals)
    # 5, 6 만 위험사건(상위 1/3), 4 이하는 아님
    assert flags == [False, False, False, False, True, True]


# --- Wilson CI --------------------------------------------------------------
def test_wilson_interval_bounds():
    p, lo, hi = wilson_interval(3, 10)
    assert math.isclose(p, 0.3, rel_tol=1e-9)
    assert 0.0 <= lo < p < hi <= 1.0

def test_wilson_zero_n():
    assert wilson_interval(0, 0) == (0.0, 0.0, 0.0)


# --- evaluate: 신호가 위험사건과 완벽히 겹치면 유의 -------------------------
def test_evaluate_perfect_signal_beats_random():
    # 6건 중 뒤 2건이 위험사건이고, 신호도 정확히 그 2건만 발동
    risk = [False, False, False, False, True, True]
    fired = [False, False, False, False, True, True]
    res = evaluate(fired, risk, trials=2000, seed=1)
    assert res.n_fired == 2 and res.n_hit == 2
    assert math.isclose(res.hit_rate, 1.0, rel_tol=1e-9)
    assert res.base_rate < res.hit_rate      # 기저율보다 높음
    assert res.rand_p < 0.1                   # 무작위론 드묾

def test_evaluate_random_signal_not_significant():
    # 신호가 위험사건과 무관(엇갈림) → 무작위와 구별 안 됨
    risk = [True, False, True, False, True, False]
    fired = [False, True, False, True, False, True]  # 전부 빗나감
    res = evaluate(fired, risk, trials=2000, seed=1)
    assert res.n_hit == 0
    assert res.rand_p > 0.05                  # 유의하지 않음

def test_evaluate_no_fires():
    res = evaluate([False, False, False], [True, False, True], trials=100)
    assert res.n_fired == 0 and res.rand_p == 1.0


# --- 룰전략 vs 단순보유 -----------------------------------------------------
def test_strategy_avoids_flagged_drawdowns():
    # 경고 회의(마지막)만 큰 낙폭 → 회피하면 평균 낙폭 감소
    rets = [0.5, -0.3, -5.0]
    dds = [0.6, 0.4, 6.0]
    alert = [False, False, True]
    st = strategy_vs_hold(rets, dds, alert)
    assert st.n == 3
    assert st.avoided_dd > 0                  # 낙폭을 피함
    assert st.signal_mean_ret > st.hold_mean_ret  # 큰 손실 회피로 평균 개선


# --- 국면 태그 --------------------------------------------------------------
def test_regime_of():
    assert regime_of("2005-06-30") == "긴축"
    assert regime_of("2008-10-29") == "완화"
    assert regime_of("2013-03-20") == "중립"
    assert regime_of("bad-date") == "중립"
