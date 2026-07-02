"""
Phase 6 — 신호 규칙 엔진 (signal_design.md §3 실체화)

3종 신호를 '순수 함수'로 구현한다. 숫자만 받고 판정 결과(Signal)를 돌려주며
DB·네트워크·모델에 의존하지 않아 단위테스트가 쉽다. DB 조립은 load_series()가 맡는다.

  신호 A (tone_shift)   : 직전 회의 대비 톤 급변  → 🔼/🔽
  신호 B (divergence) ⭐ : 톤 부호 ≠ 시장반응 부호 (핵심 위험 알림)
  신호 C (tone_vs_vix)  : 평소 음의 동행(톤↑→VIX↓)이 깨지는 이례

[철학 — signal_design.md §1-A]
  우리는 방향을 '예측'하지 않는다. "과거 이런 톤·패턴일 때 이런 경향이 있었다"를
  신뢰도·표본경고와 함께 알린다. 그래서 grade는 매수/매도가 아니라
  🟢정합 · ⚪중립 · ⚠️주의 · 🔴경고 4등급으로만 낸다.

실행(회의별 알림 미리보기): python3 analysis/signals.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# 임계값 (θ) — 전부 잠정값. signal_design.md §8 대로 데이터 분포로 보정 예정.
# 코드 곳곳에 하드코딩하지 않고 한 곳(Thresholds)에서 주입한다.
# ---------------------------------------------------------------------------
@dataclass
class Thresholds:
    theta_shift: float = 0.20   # A: |이번 톤 - 직전 톤| 이 이상이면 '급변'
    theta_t: float = 0.05       # B·C: 톤 크기 하한 (Phase5: 톤이 ±0.2 내에 몰림 → 작게 시작)
    theta_m: float = 0.30       # B: 시장 반응 크기 하한 (%단위, spx_ret_cc 규약과 동일)
    theta_vix: float = 1.00     # C: VIX 변화 크기 하한 (VIX 포인트)


DEFAULT_THRESHOLDS = Thresholds()

# 종합 등급 라벨 (사용자가 보는 것)
GRADE_ALIGNED = "🟢 정합"
GRADE_NEUTRAL = "⚪ 중립"
GRADE_CAUTION = "⚠️ 주의"
GRADE_ALERT = "🔴 경고"


def sign(x: Optional[float]) -> int:
    """부호만: 양수 +1, 음수 -1, 0/None 은 0."""
    if x is None:
        return 0
    return (x > 0) - (x < 0)


@dataclass
class Signal:
    """개별 신호 1개의 판정 결과."""
    name: str            # tone_shift | divergence | tone_vs_vix
    fired: bool          # 발동 여부
    detail: str          # 사람이 읽는 설명
    value: float = 0.0   # 발동을 만든 크기(변화량·괴리크기 등)


@dataclass
class Alert:
    """회의 1건의 종합 알림 (신호 3종 + 등급 + 신뢰도 + 면책)."""
    date: str
    grade: str
    confidence: float
    tone: Optional[float]
    reaction_ret: Optional[float]
    signals: List[Signal] = field(default_factory=list)
    note: str = ""

    def fired_names(self) -> List[str]:
        return [s.name for s in self.signals if s.fired]


# ---------------------------------------------------------------------------
# 신호 A — 톤 급변 (Tone Shift)
#   근거: FOMC 텍스트 정보는 '절대 수준'보다 '직전 대비 변화'에 있다.
# ---------------------------------------------------------------------------
def signal_tone_shift(prev_tone: Optional[float], tone: Optional[float],
                      theta: float = DEFAULT_THRESHOLDS.theta_shift) -> Signal:
    if prev_tone is None or tone is None:
        return Signal("tone_shift", False, "직전 회의 톤 없음(첫 회의)", 0.0)
    delta = tone - prev_tone
    fired = abs(delta) >= theta
    if not fired:
        return Signal("tone_shift", False, f"톤 변화 {delta:+.3f} (θ={theta} 미만)", delta)
    arrow = "🔼 톤 개선" if delta > 0 else "🔽 톤 악화"
    return Signal("tone_shift", True, f"{arrow} ({delta:+.3f})", delta)


# ---------------------------------------------------------------------------
# 신호 B — 톤↔시장 괴리 (Divergence) ⭐ 핵심
#   조건: sign(톤) ≠ sign(반응)  AND  |톤| ≥ θ_t  AND  |반응| ≥ θ_m
#   근거: 괴리는 위기·전환점에 집중 (프로토타입 확인).
# ---------------------------------------------------------------------------
def signal_divergence(tone: Optional[float], reaction_ret: Optional[float],
                      theta_t: float = DEFAULT_THRESHOLDS.theta_t,
                      theta_m: float = DEFAULT_THRESHOLDS.theta_m) -> Signal:
    if tone is None or reaction_ret is None:
        return Signal("divergence", False, "톤/반응 데이터 없음", 0.0)
    ts, rs = sign(tone), sign(reaction_ret)
    opposite = ts != 0 and rs != 0 and ts != rs
    big_enough = abs(tone) >= theta_t and abs(reaction_ret) >= theta_m
    if not (opposite and big_enough):
        why = "방향 일치" if not opposite else "크기 미달"
        return Signal("divergence", False, f"괴리 아님({why})", 0.0)
    magnitude = abs(tone) * abs(reaction_ret)
    tone_word = "긍정" if ts > 0 else "부정"
    mkt_word = "급락" if rs < 0 else "급등"
    detail = f"⚠️ 괴리 — 연준 톤 {tone_word}({tone:+.3f}) vs 시장 {mkt_word}({reaction_ret:+.2f}%)"
    return Signal("divergence", True, detail, magnitude)


# ---------------------------------------------------------------------------
# 신호 C — 톤↔공포(VIX) 동행 이탈 (Tone vs VIX)
#   평소 톤과 VIX는 음의 동행(톤↑ → VIX↓, 상관 −0.34). 이 관계가 깨지면 이례.
#   이탈 = 톤과 VIX변화가 '같은 부호' 이고 둘 다 충분히 큼
#          (톤 긍정인데 VIX 급등  또는  톤 부정인데 VIX 급락).
# ---------------------------------------------------------------------------
def signal_tone_vs_vix(tone: Optional[float], vix_chg: Optional[float],
                       theta_t: float = DEFAULT_THRESHOLDS.theta_t,
                       theta_vix: float = DEFAULT_THRESHOLDS.theta_vix) -> Signal:
    if tone is None or vix_chg is None:
        return Signal("tone_vs_vix", False, "톤/VIX 데이터 없음", 0.0)
    ts, vs = sign(tone), sign(vix_chg)
    # 정상(동행): 부호가 반대. 이탈: 부호가 같음.
    break_comove = ts != 0 and vs != 0 and ts == vs
    big_enough = abs(tone) >= theta_t and abs(vix_chg) >= theta_vix
    if not (break_comove and big_enough):
        return Signal("tone_vs_vix", False, "동행 유지(또는 크기 미달)", 0.0)
    tone_word = "긍정" if ts > 0 else "부정"
    vix_word = "급등" if vs > 0 else "급락"
    detail = f"⚠️ 동행 이탈 — 톤 {tone_word}인데 VIX {vix_word}({vix_chg:+.2f})"
    return Signal("tone_vs_vix", True, detail, abs(tone) * abs(vix_chg))


# ---------------------------------------------------------------------------
# 종합 등급 — 발동한 신호들을 4등급으로 요약
#   🔴 경고 : 괴리(B) 발동 — 가장 강한 위험 알림
#   ⚠️ 주의 : 동행이탈(C) 또는 톤급변(A) 발동
#   🟢 정합 : 아무 경고도 없고 톤·반응이 같은 방향(정합 확인)
#   ⚪ 중립 : 판정 불가/무발동/방향 애매
# ---------------------------------------------------------------------------
def grade(signals: List[Signal], tone: Optional[float],
          reaction_ret: Optional[float]) -> str:
    fired = {s.name for s in signals if s.fired}
    if "divergence" in fired:
        return GRADE_ALERT
    if "tone_vs_vix" in fired or "tone_shift" in fired:
        return GRADE_CAUTION
    # 경고 없음 → 톤·반응 방향이 같으면 정합 확인, 아니면 중립
    if sign(tone) != 0 and sign(tone) == sign(reaction_ret):
        return GRADE_ALIGNED
    return GRADE_NEUTRAL


# ---------------------------------------------------------------------------
# 순수 조립부 — 시계열(회의 순서) 데이터로 회의별 Alert 리스트를 만든다.
#   series: 시간순 정렬된 dict 리스트
#     {date, tone, confidence, reaction_ret, vix_chg}
#   → prev_tone 은 직전 원소에서 얻는다. DB 없이 테스트 가능.
# ---------------------------------------------------------------------------
def build_alerts(series: List[dict],
                 th: Thresholds = DEFAULT_THRESHOLDS,
                 small_sample: bool = True) -> List[Alert]:
    alerts: List[Alert] = []
    prev_tone: Optional[float] = None
    for row in series:
        tone = row.get("tone")
        reaction = row.get("reaction_ret")
        vix_chg = row.get("vix_chg")
        conf = row.get("confidence") or 0.0

        sigs = [
            signal_tone_shift(prev_tone, tone, th.theta_shift),
            signal_divergence(tone, reaction, th.theta_t, th.theta_m),
            signal_tone_vs_vix(tone, vix_chg, th.theta_t, th.theta_vix),
        ]
        g = grade(sigs, tone, reaction)
        note = "참고용·투자조언 아님."
        if small_sample:
            note += " 표본 적음 → '예측' 아닌 '경향'."
        alerts.append(Alert(
            date=row["date"], grade=g, confidence=conf,
            tone=tone, reaction_ret=reaction, signals=sigs, note=note,
        ))
        prev_tone = tone if tone is not None else prev_tone
    return alerts


# ---------------------------------------------------------------------------
# DB 로더 — meetings(톤·confidence) + market(반응·vix_chg) 를 회의순으로 조립.
#   analyze_alignment 의 검증된 헬퍼(get_meeting_tone/get_reaction)를 재사용.
# ---------------------------------------------------------------------------
def load_series(con, agg_method: str = "conf_weighted", reaction_offset: int = 1) -> List[dict]:
    from analysis.analyze_alignment import get_meeting_tone, get_reaction

    rows = con.execute(
        "SELECT date, index_value, confidence FROM meetings "
        "WHERE method = ? AND granularity = 'meeting' ORDER BY date",
        (agg_method,),
    ).fetchall()

    series: List[dict] = []
    for date, tone, conf in rows:
        reac = get_reaction(con, date, reaction_offset)  # (rdate, spx_ret_cc, vix_chg) | None
        ret = reac[1] if reac else None
        vixc = reac[2] if reac else None
        series.append({
            "date": date, "tone": tone, "confidence": conf,
            "reaction_ret": ret, "vix_chg": vixc,
        })
    return series


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
    series = load_series(con)
    con.close()
    if not series:
        print("meetings 톤이 없습니다. 먼저 pipeline → collect_market 을 실행하세요.")
        return

    alerts = build_alerts(series, small_sample=len(series) < 30)
    print(f"회의 {len(alerts)}건 신호 미리보기 (θ 잠정값)\n")
    for a in alerts:
        fired = ", ".join(a.fired_names()) or "-"
        print(f"{a.date}  {a.grade}  conf={a.confidence:.3f}  발동=[{fired}]")
        for s in a.signals:
            if s.fired:
                print(f"      · {s.detail}")


if __name__ == "__main__":
    main()
