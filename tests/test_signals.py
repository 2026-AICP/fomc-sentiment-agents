"""신호 규칙 엔진 단위테스트 (네트워크·모델·DB 의존 없음, 결정적).

Phase 6 신호 A/B/C 와 grade·build_alerts 의 경계·부호 로직을 고정한다.
"""
from analysis.signals import (
    Thresholds,
    signal_tone_shift,
    signal_divergence,
    signal_tone_vs_vix,
    grade,
    build_alerts,
    GRADE_ALERT,
    GRADE_CAUTION,
    GRADE_ALIGNED,
    GRADE_NEUTRAL,
)

TH = Thresholds()  # 기본 잠정값


# --- 신호 A: 톤 급변 --------------------------------------------------------
def test_tone_shift_fires_on_big_change():
    s = signal_tone_shift(prev_tone=-0.10, tone=0.15, theta=0.20)
    assert s.fired and s.value > 0  # 개선 방향

def test_tone_shift_silent_on_small_change():
    assert not signal_tone_shift(0.10, 0.15, theta=0.20).fired

def test_tone_shift_first_meeting_has_no_prev():
    assert not signal_tone_shift(None, 0.5, theta=0.20).fired


# --- 신호 B: 괴리 (핵심) ----------------------------------------------------
def test_divergence_fires_on_opposite_signs_big_enough():
    # 톤 부정(-0.10) 인데 시장 급등(+1.2%) → 괴리
    s = signal_divergence(tone=-0.10, reaction_ret=1.2, theta_t=0.05, theta_m=0.30)
    assert s.fired and s.value > 0

def test_divergence_silent_when_same_direction():
    # 톤 부정 + 시장 하락 → 방향 일치, 괴리 아님
    assert not signal_divergence(-0.10, -1.2, 0.05, 0.30).fired

def test_divergence_silent_when_reaction_too_small():
    # 부호는 반대지만 시장 반응이 θ_m 미달
    assert not signal_divergence(-0.10, 0.05, 0.05, 0.30).fired

def test_divergence_silent_on_zero_tone():
    assert not signal_divergence(0.0, 1.2, 0.05, 0.30).fired


# --- 신호 C: 톤-VIX 동행 이탈 ----------------------------------------------
def test_tone_vs_vix_fires_when_comovement_breaks():
    # 평소 톤 긍정이면 VIX 하락이 정상. 톤 긍정인데 VIX 급등 → 이탈
    s = signal_tone_vs_vix(tone=0.10, vix_chg=3.0, theta_t=0.05, theta_vix=1.0)
    assert s.fired

def test_tone_vs_vix_silent_when_comovement_holds():
    # 톤 긍정 + VIX 하락 → 정상 동행
    assert not signal_tone_vs_vix(0.10, -3.0, 0.05, 1.0).fired

def test_tone_vs_vix_silent_when_vix_change_small():
    assert not signal_tone_vs_vix(0.10, 0.2, 0.05, 1.0).fired


# --- 종합 등급 --------------------------------------------------------------
def test_grade_alert_when_divergence_fired():
    sigs = [signal_divergence(-0.10, 1.2, 0.05, 0.30)]
    assert grade(sigs, tone=-0.10, reaction_ret=1.2) == GRADE_ALERT

def test_grade_caution_when_only_tone_shift():
    sigs = [signal_tone_shift(-0.10, 0.15, 0.20)]
    assert grade(sigs, tone=0.15, reaction_ret=0.15) == GRADE_CAUTION

def test_grade_aligned_when_no_warning_and_same_direction():
    # 아무 신호도 발동 안 하고 톤·반응 방향이 같음
    sigs = [signal_divergence(0.02, 0.1, 0.05, 0.30)]  # 크기 미달 → 무발동
    assert grade(sigs, tone=0.02, reaction_ret=0.1) == GRADE_ALIGNED

def test_grade_neutral_when_reaction_missing():
    sigs = [signal_divergence(0.02, None, 0.05, 0.30)]
    assert grade(sigs, tone=0.02, reaction_ret=None) == GRADE_NEUTRAL


# --- 조립부: build_alerts ---------------------------------------------------
def test_build_alerts_uses_previous_tone_for_shift():
    series = [
        {"date": "2000-01-01", "tone": -0.10, "confidence": 0.4,
         "reaction_ret": -0.5, "vix_chg": 0.2},
        {"date": "2000-02-01", "tone": 0.20, "confidence": 0.4,   # +0.30 급변
         "reaction_ret": 0.5, "vix_chg": -0.2},
    ]
    alerts = build_alerts(series, TH)
    assert len(alerts) == 2
    # 첫 회의는 직전 톤이 없어 tone_shift 무발동
    assert not any(s.name == "tone_shift" and s.fired for s in alerts[0].signals)
    # 둘째 회의는 +0.30 급변 → tone_shift 발동
    assert any(s.name == "tone_shift" and s.fired for s in alerts[1].signals)

def test_build_alerts_small_sample_note():
    series = [{"date": "2000-01-01", "tone": 0.1, "confidence": 0.4,
               "reaction_ret": 0.1, "vix_chg": 0.0}]
    a = build_alerts(series, TH, small_sample=True)[0]
    assert "표본 적음" in a.note
