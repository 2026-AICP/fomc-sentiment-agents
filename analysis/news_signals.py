"""신호 레이어 — 일별 News 감성 신호 (규칙 기반, LLM 미사용).

일별 News 지수(outputs/news_index_live.csv)를 보고 '알려줄 만한' 순간을 규칙으로 판정.
전부 순수함수(숫자 in → 판정 out) → 재현·추적 가능, 환각 0.
목표: 조용한 숫자를 '오늘의 신호'로 (신호 발견·제공).

신호:
  1단계(일별 지수만):
    · shift      감성 급변 (직전 대비 큰 이동)
    · extreme    극단값 (최근 N일 최저/최고)
    · sign_flip  부호 전환 (긍↔부)
  2단계(+일별 시장, collect_market):
    · divergence 뉴스↔시장 괴리 ⭐ (뉴스 부호 ≠ 시장 반응 부호)
  [게이트] 신뢰도 낮으면(기사 적음/CI 넓음) '관망' → 헛경보 방지

등급:  🔴 경고(괴리) · ⚠️ 주의(급변·전환) · 🔵 관심(극단) · 🟢 안정 · ⚪ 관망(신뢰도부족)

실행:  python3 analysis/news_signals.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))     # 저장소 루트 → analysis/collect_market import 대비
NEWS_CSV = ROOT / "outputs" / "news_index_live.csv"


@dataclass
class Thresholds:
    """임계값 (잠정 — 데이터 쌓이면 분포로 보정)."""
    theta_shift: float = 0.15     # 급변: |오늘 - 직전| 이상이면 발동
    theta_sign: float = 0.05      # 부호전환: 양쪽 크기 하한
    extreme_window: int = 10      # 극단값: 최근 N일 창
    min_articles: int = 15        # 신뢰도 게이트: 기사 하한
    ci_max: float = 0.60          # 신뢰도 게이트: CI 폭 상한
    theta_div_news: float = 0.05  # 괴리: 뉴스 감성 크기 하한
    theta_div_mkt: float = 0.5    # 괴리: 시장 변동 크기 하한 (% 단위)


DEFAULT = Thresholds()


def _sign(x) -> int:
    return (x > 0) - (x < 0) if x is not None else 0


@dataclass
class Signal:
    name: str
    fired: bool
    detail: str
    value: float = 0.0


@dataclass
class Alert:
    date: str
    level: str
    value: float
    n_articles: int
    signals: List[Signal] = field(default_factory=list)
    gate_reason: Optional[str] = None


# ── 개별 신호 (순수함수: 숫자 in → 판정 out) ──
def signal_shift(prev: Optional[float], today: float, theta: float = DEFAULT.theta_shift) -> Signal:
    if prev is None:
        return Signal("shift", False, "직전 없음")
    d = today - prev
    if abs(d) < theta:
        return Signal("shift", False, f"변화 {d:+.3f} (θ={theta} 미만)", d)
    word = "급락 📉" if d < 0 else "급등 📈"
    return Signal("shift", True, f"감성 {word} (전일 대비 {d:+.3f})", d)


def signal_extreme(today: float, window_vals: List[float], window: int = DEFAULT.extreme_window) -> Signal:
    vals = window_vals[-window:]
    if len(vals) < 3:
        return Signal("extreme", False, "표본 부족")
    if today >= max(vals):
        return Signal("extreme", True, f"최근 {len(vals)}일 최고 ({today:+.3f})", today)
    if today <= min(vals):
        return Signal("extreme", True, f"최근 {len(vals)}일 최저 ({today:+.3f})", today)
    return Signal("extreme", False, "극단 아님")


def signal_sign_flip(prev: Optional[float], today: float, theta: float = DEFAULT.theta_sign) -> Signal:
    if prev is None:
        return Signal("sign_flip", False, "직전 없음")
    ps, ts = _sign(prev), _sign(today)
    if ps != 0 and ts != 0 and ps != ts and abs(prev) >= theta and abs(today) >= theta:
        word = "긍정→부정" if ts < 0 else "부정→긍정"
        return Signal("sign_flip", True, f"부호 전환 ({word})", today)
    return Signal("sign_flip", False, "전환 아님")


def signal_divergence(news: float, market_ret, th: Thresholds = DEFAULT) -> Signal:
    """⭐ 뉴스↔시장 괴리: 뉴스 감성 부호 ≠ 시장 반응 부호 (둘 다 충분히 큼)."""
    if market_ret is None:
        return Signal("divergence", False, "시장 데이터 없음")
    ns, ms = _sign(news), _sign(market_ret)
    big = abs(news) >= th.theta_div_news and abs(market_ret) >= th.theta_div_mkt
    if ns != 0 and ms != 0 and ns != ms and big:
        nw = "긍정" if ns > 0 else "부정"
        mw = "하락" if ms < 0 else "상승"
        return Signal("divergence", True,
                      f"⚠️ 괴리 — 뉴스 {nw}({news:+.3f}) vs 시장 {mw}({market_ret:+.2f}%)",
                      abs(news) * abs(market_ret))
    return Signal("divergence", False, "괴리 아님")


def confident(n_articles: int, ci_lo, ci_hi, th: Thresholds = DEFAULT):
    """신뢰도 게이트: 기사 충분 + CI 충분히 좁으면 (True, '')."""
    if n_articles < th.min_articles:
        return False, f"기사 {n_articles}건(<{th.min_articles}) — 관망(신뢰도 부족)"
    if ci_lo == ci_lo and ci_hi == ci_hi and (ci_hi - ci_lo) > th.ci_max:
        return False, f"CI 폭 {ci_hi - ci_lo:.2f} 넓음 — 관망(신뢰도 부족)"
    return True, ""


# ── 조립: 일별 시계열(+시장) → 일별 Alert ──
def build_alerts(series: List[dict], market: dict = None, th: Thresholds = DEFAULT) -> List[Alert]:
    """series: 시간순 [{date,value,n_articles,ci_lo,ci_hi}, ...].
    market(선택): {date: {'spx_ret': %, 'vix_chg': ...}} 있으면 괴리 신호 포함."""
    market = market or {}
    alerts: List[Alert] = []
    for i, row in enumerate(series):
        today = row["value"]
        prev = series[i - 1]["value"] if i > 0 else None
        window_vals = [r["value"] for r in series[:i + 1]]
        mret = (market.get(row["date"]) or {}).get("spx_ret")
        sigs = [
            signal_shift(prev, today, th.theta_shift),
            signal_extreme(today, window_vals, th.extreme_window),
            signal_sign_flip(prev, today, th.theta_sign),
            signal_divergence(today, mret, th),
        ]
        ok, gate = confident(row["n_articles"], row.get("ci_lo"), row.get("ci_hi"), th)
        fired = [s for s in sigs if s.fired]
        if not ok:
            level = "⚪ 관망"
        elif any(s.name == "divergence" for s in fired):
            level = "🔴 경고"
        elif any(s.name in ("shift", "sign_flip") for s in fired):
            level = "⚠️ 주의"
        elif fired:
            level = "🔵 관심"
        else:
            level = "🟢 안정"
        alerts.append(Alert(row["date"], level, today, row["n_articles"], sigs, None if ok else gate))
    return alerts


def load_series(csv=NEWS_CSV) -> List[dict]:
    import csv as csvmod
    out = []
    with open(csv, encoding="utf-8-sig") as f:
        for r in csvmod.DictReader(f):
            def _f(k):
                v = r.get(k)
                return float(v) if v not in (None, "", "nan") else float("nan")
            out.append({"date": r["date"], "value": float(r["conf_weighted"]),
                        "n_articles": int(float(r["n_articles"])),
                        "ci_lo": _f("ci_lo"), "ci_hi": _f("ci_hi")})
    out.sort(key=lambda x: x["date"])
    return out


def load_market_daily(dates) -> dict:
    """뉴스 날짜들의 일별 시장(spx_ret_cc %, vix_chg). 실패/오프라인 시 {} (괴리만 생략)."""
    dates = [d for d in dates if d]
    if not dates:
        return {}
    try:
        from analysis import collect_market as cm    # yfinance·인증서 우회는 여기서만
        import pandas as pd
        full = cm.compute_derived_global(cm.download_full_range(dates))
    except Exception as e:
        print(f"[market] 일별 시장 생략(오프라인?): {str(e)[:45]}")
        return {}
    out = {}
    for ts, r in full.iterrows():
        d = ts.strftime("%Y-%m-%d")
        out[d] = {"spx_ret": None if pd.isna(r["spx_ret_cc"]) else float(r["spx_ret_cc"]),
                  "vix_chg": None if pd.isna(r["vix_chg"]) else float(r["vix_chg"])}
    return out


def save_alerts(alerts: List[Alert], out: Path = ROOT / "outputs" / "news_signals.csv") -> Path:
    """일별 신호를 CSV로 저장 (대시보드·기록용). 최신일이 마지막 행."""
    import csv as csvmod
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csvmod.writer(f)
        w.writerow(["date", "level", "value", "n_articles", "fired", "detail", "gate_reason"])
        for a in alerts:
            fired = ";".join(s.name for s in a.signals if s.fired)
            detail = " · ".join(s.detail for s in a.signals if s.fired)
            w.writerow([a.date, a.level, round(a.value, 4), a.n_articles, fired, detail, a.gate_reason or ""])
    return out


def main():
    if not NEWS_CSV.exists():
        raise SystemExit(f"News 지수 CSV 없음: {NEWS_CSV}\n먼저 agents/news_scheduler.py 실행")
    series = load_series()
    market = load_market_daily([r["date"] for r in series])
    alerts = build_alerts(series, market)
    out = save_alerts(alerts)
    print(f"\n일별 News 신호 {len(alerts)}일 (규칙 기반, LLM 미사용) → 저장 {out.relative_to(ROOT)}\n── 오늘의 신호 ──")
    for a in alerts:
        print(f"{a.level}  [{a.date}]  감성 {a.value:+.3f} (기사 {a.n_articles}건)")
        for s in a.signals:
            if s.fired:
                print(f"       · {s.detail}")
        if a.gate_reason:
            print(f"       · {a.gate_reason}")
        elif not any(s.fired for s in a.signals):
            print("       · 특이신호 없음")
    print("\n※ 참고용·투자조언 아님. 예측 아닌 경향. (임계값 잠정 — 데이터 쌓이면 보정)")


if __name__ == "__main__":
    main()
