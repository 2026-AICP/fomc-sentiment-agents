"""알림 적중 임계값 산출 — 사전 등록용 (docs/notification_design.md §7-5).

알림을 보낸 뒤 "그래서 맞았나"를 판정하려면 기준이 있어야 한다. 그 기준을 결과를
본 뒤에 정하면 체리피킹이므로, **알림을 켜기 전에 한 번 계산해 고정한다.**

적중 정의(문서 §7-2):
  · 양측 — 변동의 크기만 본다. 🔴 경고의 정체는 divergence(뉴스↔시장 괴리)라
    오를지 내릴지를 예측하는 신호가 아니다.
  · 주 기준 5거래일. 부기준 1·3·10거래일은 강건성 확인용 — 넷을 다 돌려 좋은 걸
    고르면 다중비교이므로 주 기준을 미리 못 박는다.
  · |S&P 누적수익률| 또는 |ΔVIX| 가 전 거래일 분포 상위 10%면 적중.

왜 절대 수치가 아니라 분위수인가:
  임계값을 사람이 고르면 "왜 하필 그 값이냐"에 답해야 한다. 초안에서 예시로 든
  "S&P -1%"는 실제로는 하위 17% 언저리여서 아무 날이나 찍어도 여섯 번에 한 번은
  '적중'했다. 분위수로 두면 데이터가 임계값을 정하고, **무작위 날짜의 적중률이
  정의상 10%**라 귀무가설이 공짜로 딸려온다.

미래 정보 차단(TA 질문 4-3: 절대 random split 금지):
  표본은 2000-01-01 ~ 계산일이고 평가 대상은 **계산일 이후 발송되는 알림뿐**이다.
  임계값이 평가 대상보다 앞선 정보만 쓰므로 미래가 과거로 새지 않는다.

한 번 고정하고 다시 계산하지 않는다. 재계산은 사후 조정이 되어 사전 등록의
의미가 사라진다 — 그래서 결과 파일이 이미 있으면 --force 없이는 덮어쓰지 않는다.

실행:  python3 analysis/hit_thresholds.py            # 최초 1회
       python3 analysis/hit_thresholds.py --force    # 원칙상 하지 않는다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis import collect_market as cm   # 인증서 우회 + yfinance 설정 재사용
import numpy as np
import pandas as pd

START = "2000-01-01"
HORIZONS = (1, 3, 5, 10)      # 거래일. 주 기준은 5, 나머지는 강건성 확인용
PRIMARY = 5
PCT = 90                      # 상위 10% = 90분위
CRISIS_YEARS = (2008, 2020)   # 제외 버전용 (TA 질문 4-4: 위기 한두 개가 결과를 만드는지)

OUT_JSON = ROOT / "outputs" / "hit_thresholds.json"
OUT_DOC = ROOT / "docs" / "alert_hit_thresholds.md"


def download() -> pd.DataFrame:
    """^GSPC·^VIX 일별 종가. collect_market 과 같은 경로(yfinance, auto_adjust)."""
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    print(f"다운로드: ^GSPC · ^VIX  {START} ~ {end}")
    raw = cm.yf.download(["^GSPC", "^VIX"], start=START, end=end,
                         progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        raise RuntimeError("yfinance 가 빈 데이터를 반환했다.")
    df = pd.DataFrame({"spx": raw["Close"]["^GSPC"],
                       "vix": raw["Close"]["^VIX"]}).dropna()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def moves(df: pd.DataFrame, h: int) -> pd.DataFrame:
    """t 시점에서 h 거래일 뒤까지의 |누적변동|. 양측이므로 절대값."""
    return pd.DataFrame({
        "spx": (df.spx.shift(-h) / df.spx - 1).abs() * 100,   # % 단위
        "vix": (df.vix.shift(-h) - df.vix).abs(),             # 포인트 단위
    }).dropna()


def summarize(m: pd.DataFrame) -> dict:
    """90분위 임계값 + 각 조건과 합집합의 실제 발생률.

    합집합률이 핵심이다. 주 기준은 "S&P 또는 VIX"라 실제 무작위 발생률은 10%가
    아니라 그보다 높다(완전독립 19% ~ 완전상관 10%). 이 수치를 모르면
    "무작위 대비 몇 배"를 말할 수 없다 — 문서 §7-6.
    """
    t_spx = float(np.percentile(m.spx, PCT))
    t_vix = float(np.percentile(m.vix, PCT))
    hit_spx, hit_vix = m.spx > t_spx, m.vix > t_vix
    return {
        "n_days": int(len(m)),
        "thr_spx_abs_ret_pct": round(t_spx, 4),
        "thr_vix_abs_chg_pt": round(t_vix, 4),
        "rate_spx": round(float(hit_spx.mean()), 4),
        "rate_vix": round(float(hit_vix.mean()), 4),
        "rate_union": round(float((hit_spx | hit_vix).mean()), 4),
        "rate_both": round(float((hit_spx & hit_vix).mean()), 4),
    }


def build(df: pd.DataFrame) -> dict:
    full = {str(h): summarize(moves(df, h)) for h in HORIZONS}
    ex = df[~df.index.year.isin(CRISIS_YEARS)]
    excl = {str(h): summarize(moves(ex, h)) for h in HORIZONS}
    return {
        "computed_at": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "sample": {"start": df.index.min().strftime("%Y-%m-%d"),
                   "end": df.index.max().strftime("%Y-%m-%d"),
                   "n_trading_days": int(len(df))},
        "definition": {
            "sided": "two",                 # 양측 — 크기만 본다
            "primary_horizon_days": PRIMARY,
            "secondary_horizon_days": [h for h in HORIZONS if h != PRIMARY],
            "percentile": PCT,
            "rule": "|S&P 누적수익률| 또는 |ΔVIX| 가 90분위 초과면 적중",
        },
        "thresholds": full,
        "thresholds_ex_crisis": {"excluded_years": list(CRISIS_YEARS), **excl},
        "note": ("한 번 고정하고 재계산하지 않는다. 평가 대상은 computed_at 이후 "
                 "발송된 알림뿐이며, 그래야 임계값이 평가 대상보다 앞선 정보만 쓴다."),
    }


def _row(h, s):
    return (f"| {h}거래일 | {s['thr_spx_abs_ret_pct']:.2f}% | {s['thr_vix_abs_chg_pt']:.2f}pt "
            f"| {s['rate_spx']:.1%} | {s['rate_vix']:.1%} | **{s['rate_union']:.1%}** |")


def _delta(res, key):
    """주 기준 임계값이 위기 제외로 몇 % 움직였는지 — 부호를 붙여 돌려준다."""
    p = str(PRIMARY)
    full = res["thresholds"][p][key]
    return f"{(res['thresholds_ex_crisis'][p][key] / full - 1) * 100:+.1f}%"


def write_doc(res: dict) -> None:
    p, sm = str(PRIMARY), res["sample"]
    u = res["thresholds"][p]["rate_union"]
    lines = [
        "# 알림 적중 임계값 — 사전 등록 기록",
        "",
        f"`analysis/hit_thresholds.py` 산출. 계산일 **{res['computed_at']}**, "
        f"표본 {sm['start']} ~ {sm['end']} ({sm['n_trading_days']:,} 거래일).",
        "",
        "설계 근거는 `docs/notification_design.md` §7 에 있다. 이 문서는 그 §7-5 가",
        "요구한 **숫자를 고정한 기록**이다. 재계산하지 않는다.",
        "",
        "## 적중 정의",
        "",
        "발송일 종가 기준 h 거래일 뒤까지의 **|누적변동|** 이, 전 거래일 분포의",
        f"**{PCT}분위(상위 {100 - PCT}%)** 를 넘으면 적중. **양측**(크기만 본다) —",
        "🔴 경고의 정체인 divergence 는 방향을 예측하는 신호가 아니기 때문이다.",
        "",
        f"**주 기준 {PRIMARY}거래일.** 나머지는 강건성 확인용이며, 넷을 다 돌려 좋은 걸",
        "고르면 다중비교이므로 주 기준을 미리 못 박는다.",
        "",
        "## 임계값 (전체 표본)",
        "",
        "| 기간 | S&P \\|누적수익률\\| | VIX \\|변화\\| | S&P 단독 | VIX 단독 | **합집합 = 귀무가설** |",
        "|---|---|---|---|---|---|",
        *[_row(h, res["thresholds"][str(h)]) for h in HORIZONS],
        "",
        "**맨 오른쪽이 귀무가설이다.** 주 기준은 \"S&P *또는* VIX\"이므로 무작위 날짜의",
        f"적중률은 10%가 아니라 **{u:.1%}** 다. 두 변동이 상관돼 있어 완전독립(19%)보다",
        "낮다. 알림 적중률은 이 값과 비교해야 한다 — 10%와 비교하면 성과가 부풀려진다.",
        "",
        f"### 주 기준({PRIMARY}거래일) 판정식",
        "",
        "```",
        f"적중  ⟺  |S&P {PRIMARY}일 누적수익률| > {res['thresholds'][p]['thr_spx_abs_ret_pct']:.2f}%",
        f"          또는  |VIX {PRIMARY}일 변화| > {res['thresholds'][p]['thr_vix_abs_chg_pt']:.2f}pt",
        f"귀무가설(무작위 날짜의 적중률) = {u:.1%}",
        "```",
        "",
        f"## 위기 제외 ({', '.join(str(y) for y in CRISIS_YEARS)}년 제거)",
        "",
        "TA 질문 4-4(\"위기 한두 개가 결과를 만드는지\")의 정신을 적중 기준에도 적용한다.",
        "",
        "| 기간 | S&P \\|누적수익률\\| | VIX \\|변화\\| | S&P 단독 | VIX 단독 | 합집합 |",
        "|---|---|---|---|---|---|",
        *[_row(h, res["thresholds_ex_crisis"][str(h)]) for h in HORIZONS],
        "",
        f"**위기를 빼도 기준이 거의 그대로다.** 주 기준({PRIMARY}거래일) 임계값은 "
        f"{res['thresholds'][p]['thr_spx_abs_ret_pct']:.2f}% → "
        f"{res['thresholds_ex_crisis'][p]['thr_spx_abs_ret_pct']:.2f}% ("
        f"{_delta(res, 'thr_spx_abs_ret_pct')}), "
        f"{res['thresholds'][p]['thr_vix_abs_chg_pt']:.2f}pt → "
        f"{res['thresholds_ex_crisis'][p]['thr_vix_abs_chg_pt']:.2f}pt ("
        f"{_delta(res, 'thr_vix_abs_chg_pt')}) 로 움직였고, 귀무가설은 "
        f"{res['thresholds'][p]['rate_union']:.1%} → "
        f"{res['thresholds_ex_crisis'][p]['rate_union']:.1%} 로 사실상 동일하다.",
        "",
        "즉 이 임계값은 **2008·2020 두 사건이 만든 값이 아니다.** 위기를 빼도 같은",
        "수준이므로, \"위기 때문에 기준이 비현실적으로 높다\"는 반론은 성립하지 않는다.",
        "",
        "**주 기준은 전체 표본 쪽이다.** 위기 제외는 참고용 — 알림은 위기가 다시 와도",
        "발송되므로, 위기를 뺀 분포로 기준을 잡으면 실제보다 헐거워진다.",
        "",
        "## 미래 정보 차단",
        "",
        f"표본은 계산일({res['computed_at']})까지이고 평가 대상은 **그 이후 발송된 알림뿐**이다.",
        "임계값이 평가 대상보다 앞선 정보만 쓰므로 미래가 과거로 새지 않는다.",
        "TA 질문 4-3(\"절대 random train-test split 금지\")과 같은 원칙이다.",
        "",
        "## 한계",
        "",
        "- **판정에 최소 1년이 걸린다.** 🔴 이 월 1~2회면 연 12~24건이고, 위 귀무가설과",
        "  유의하게 구분하려면 그 이상이 필요하다(`notification_design.md` §8-1).",
        "- 임계값은 **전 거래일** 분포다. FOMC 당일만 보면 변동이 더 크므로, Fed 일정",
        "  알림의 적중률을 이 기준으로 재면 자연히 높게 나온다. 신호 알림과 섞지 말 것.",
        "- `n_recipients` 는 발송 시도 수이지 도달 수가 아니다(§8-4).",
        "",
    ]
    OUT_DOC.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    # 문서 문구만 고칠 때 쓴다. 고정된 JSON 을 그대로 읽어 문서만 다시 뽑으므로
    # 임계값이 바뀌지 않는다. --force 는 재다운로드라 고정값을 덮어쓴다.
    if "--doc-only" in sys.argv[1:]:
        write_doc(json.loads(OUT_JSON.read_text(encoding="utf-8")))
        print(f"문서만 재생성: {OUT_DOC.relative_to(ROOT)} (임계값은 그대로)")
        return

    force = "--force" in sys.argv[1:]
    if OUT_JSON.exists() and not force:
        raise SystemExit(
            f"이미 고정돼 있다: {OUT_JSON.relative_to(ROOT)}\n"
            "재계산은 사후 조정이라 사전 등록의 의미를 없앤다. 정말 필요하면 --force."
        )
    res = build(download())
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    write_doc(res)

    p = str(PRIMARY)
    t = res["thresholds"][p]
    print(f"\n표본 {res['sample']['start']} ~ {res['sample']['end']} "
          f"({res['sample']['n_trading_days']:,} 거래일)")
    print(f"\n주 기준 {PRIMARY}거래일 — 적중 판정식")
    print(f"  |S&P 누적수익률| > {t['thr_spx_abs_ret_pct']:.2f}%  또는  "
          f"|ΔVIX| > {t['thr_vix_abs_chg_pt']:.2f}pt")
    print(f"  귀무가설(무작위 적중률) = {t['rate_union']:.1%}   "
          f"[S&P 단독 {t['rate_spx']:.1%} · VIX 단독 {t['rate_vix']:.1%} · "
          f"둘 다 {t['rate_both']:.1%}]")
    print("\n부기준")
    for h in HORIZONS:
        if h == PRIMARY:
            continue
        s = res["thresholds"][str(h)]
        print(f"  {h:>2}거래일 — S&P {s['thr_spx_abs_ret_pct']:5.2f}% · "
              f"VIX {s['thr_vix_abs_chg_pt']:5.2f}pt · 합집합 {s['rate_union']:.1%}")
    print(f"\n저장: {OUT_JSON.relative_to(ROOT)} · {OUT_DOC.relative_to(ROOT)}")
    print("※ 한 번 고정한 값이다. 재계산하지 말 것.")


if __name__ == "__main__":
    main()
