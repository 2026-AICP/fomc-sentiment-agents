"""Fed 축 내부 가중치 후보 비교 — statement:presser:minutes 홀드아웃 검증.

News:Fed 50:50 을 정당화한 방식(docs/news_fed_index.md §3b)과 동일하게,
가중치를 데이터로 튜닝하지 않고 **사전 고정한 후보**를 안 본 기간에서 비교한다:

  기준선  statement 단독 (현행 Fed 축)
  A안     2:2:1  — 시장영향·적시성 우선 (statement·presser ≫ minutes; USMPD·Rosa 2013)
  B안     1:1:1  — 균등 1/N (News:Fed 50:50 과 동일 논리)

방법: 성분별 z-표준화 → 가중결합(회의 단위) → 월 그리드(step) → VIX 상관.
  홀드아웃: 앞 구간으로 z-파라미터 fit → 안 본 뒤 구간에서 상관 재측정.
  presser 는 2011-04 신설 — 없는 회의는 남은 성분끼리 가중치 재정규화.

추가 검증 2종:
  ① 이벤트 스터디 — 각 성분의 톤 vs "자기 발표일" 당일 시장반응(ΔVIX·S&P수익률).
     statement·presser 는 회의일, minutes 는 공개일 근사(회의+21일, 다음 거래일).
     톤 수준과 Δ톤(전회의 대비, 서프라이즈 근사) 둘 다 본다. USMPD·Rosa(2013) 방법론.
     ※ statement 와 presser 는 같은 날이라 일별 종가로는 완전 분리 불가 — 해석 시 명시.
  ② 다중 타깃 — 월별 통합값을 VIX 수준 외에 S&P 월수익률·10y 금리 월변화(^TNX)와도
     대조해 "VIX 과적합"이 아님을 확인.

주의(해석 시 명시): 홀드아웃의 월 그리드는 세 성분 모두 회의일 기준 정렬(레포
관례). minutes 실제 공개는 회의 3주 뒤라 실시간 관점에서는 낙관적 정렬이다.

실행: python3 analysis/validate_fed_weights.py
  (선행: outputs/minutes_tones.csv · outputs/presser_tones.csv — 각 backfill 스크립트)
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.validate_robustness import block_boot_ci

MINUTES_CSV = ROOT / "outputs" / "minutes_tones.csv"
PRESSER_CSV = ROOT / "outputs" / "presser_tones.csv"

CANDIDATES = {  # (w_statement, w_presser, w_minutes) — 사전 고정
    "기준선 stmt 단독": (1, 0, 0),
    "A안 2:2:1": (2, 2, 1),
    "B안 1:1:1": (1, 1, 1),
}
CUTS = (2014, 2016, 2018)  # presser(2011-04~)가 학습·검정 양쪽에 들어가는 분할점


def meetings():
    """회의별 statement·minutes·presser 톤 (presser 없는 회의는 NaN)."""
    for p in (MINUTES_CSV, PRESSER_CSV):
        if not p.exists():
            raise SystemExit(f"{p} 없음 — 먼저 backfill 스크립트를 실행하세요.")
    m = pd.read_csv(MINUTES_CSV, parse_dates=["date"])[["date", "statement", "minutes"]]
    p = pd.read_csv(PRESSER_CSV, parse_dates=["date"])[["date", "presser"]]
    return m.merge(p, on="date", how="left").set_index("date").sort_index()


def composite(df, base, weights):
    """base 구간으로 성분별 z-파라미터 fit → df 회의별 가중결합.

    성분이 없는 회의(NaN)는 남은 성분끼리 가중치 재정규화 — headline.py 의
    "뉴스 없으면 Fed 단독" 폴백과 같은 철학.
    """
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for col, w in zip(("statement", "presser", "minutes"), weights):
        if w == 0:
            continue
        z = (df[col] - base[col].mean()) / base[col].std()
        num = num.add(w * z, fill_value=0)
        den = den.add(w * z.notna(), fill_value=0)
    return num / den


def daily_market(start, end):
    """일별 시장 데이터 (yfinance 1회 호출): ΔVIX, S&P 수익률(%), 10y 금리·변화."""
    import yfinance as yf
    px = yf.download(["^VIX", "^GSPC", "^TNX"], start=str(start.date()),
                     end=str(end.date()), progress=False, auto_adjust=False)["Close"]
    if px.empty:
        raise SystemExit("yfinance 빈 응답 — 네트워크/인증서(ASCII 경로) 확인.")
    df = pd.DataFrame({
        "vix": px["^VIX"], "vix_chg": px["^VIX"].diff(),
        "spx_ret": px["^GSPC"].pct_change() * 100,
        "tnx": px["^TNX"], "tnx_chg": px["^TNX"].diff(),
    })
    df.index = df.index.astype("datetime64[ns]")  # merge_asof 용 해상도 통일
    df.index.name = "date"
    return df


def event_study(df, mkt):
    """① 성분별 톤 vs 자기 발표일 당일 시장반응. minutes 는 회의+21일 근사."""
    print("── ① 이벤트 스터디: 톤 vs 발표일 당일 반응 (수준 | Δ톤=전회의 대비) ──")
    for name in ("statement", "presser", "minutes"):
        s = df[name].dropna()
        dates = s.index + pd.Timedelta(days=21) if name == "minutes" else s.index
        ev = pd.DataFrame({"date": dates.astype("datetime64[ns]"),
                           "tone": s.values, "tone_chg": s.diff().values})
        ev = pd.merge_asof(ev.sort_values("date"), mkt.reset_index(), on="date",
                           direction="forward", tolerance=pd.Timedelta("7D")).dropna()
        r = {k: (ev[k].corr(ev.vix_chg), ev[k].corr(ev.spx_ret)) for k in ("tone", "tone_chg")}
        print(f"  {name:<9} ({len(ev)}건)  수준: ΔVIX {r['tone'][0]:+.3f} · S&P {r['tone'][1]:+.3f}"
              f"   Δ톤: ΔVIX {r['tone_chg'][0]:+.3f} · S&P {r['tone_chg'][1]:+.3f}")
    print("  ※ 기대 부호: ΔVIX 음(-), S&P 양(+). statement·presser 는 같은 날이라 일별로는 분리 불가.\n")


def multi_target(df, mkt):
    """③ 다중 타깃: 월별 통합값 vs VIX 수준 · S&P 월수익률 · 10y 금리 월변화."""
    m = pd.DataFrame({
        "vix": mkt.vix.resample("MS").mean(),
        "spx_ret": mkt.spx_ret.resample("MS").sum(),
        "tnx_chg": mkt.tnx.resample("MS").mean().diff(),
    })
    print("── ③ 다중 타깃 (전체 구간, 월별): VIX수준 | S&P월수익률 | Δ10y금리 ──")
    for name, w in CANDIDATES.items():
        s = composite(df, df, w).resample("MS").last().ffill()
        j = pd.concat([s.rename("comp"), m], axis=1, sort=True).dropna()
        print(f"  {name:<14} VIX {j.comp.corr(j.vix):+.3f} | "
              f"S&P {j.comp.corr(j.spx_ret):+.3f} | Δ10y {j.comp.corr(j.tnx_chg):+.3f}   ({len(j)}개월)")
    print("  ※ 기대 부호: VIX 음(-), S&P 양(+). Δ10y 는 참고용(부호 선험 약함).\n")


def monthly_corr(comp, vix):
    """회의별 통합값 → 월 그리드(step, fed_monthly 관례) → VIX 상관."""
    s = comp.resample("MS").last().ffill()
    df = pd.concat([s.rename("comp"), vix], axis=1, sort=True).dropna()
    return df.comp.corr(df.vix), df


def main():
    df = meetings()
    mkt = daily_market(df.index.min() - pd.Timedelta(days=5),
                       df.index.max() + pd.Timedelta(days=35))
    vix = mkt.vix.resample("MS").mean()  # build_headline_norm.vix_monthly 와 동일 정의
    n_presser = df.presser.notna().sum()
    print(f"회의 {len(df)}건 ({df.index.min().date()}~{df.index.max().date()}) · "
          f"presser 있는 회의 {n_presser}건\n")

    event_study(df, mkt)
    multi_target(df, mkt)

    print("── 전체 구간: VIX 상관 + 블록 부트스트랩 95% CI (block=12개월, 3000회) ──")
    for name, w in CANDIDATES.items():
        r, m = monthly_corr(composite(df, df, w), vix)
        lo, hi = block_boot_ci(m.comp, m.vix)
        print(f"  {name:<14} {r:+.3f}   95% CI [{lo:+.3f}, {hi:+.3f}]   ({len(m)}개월)")

    print("\n── 홀드아웃 (앞=학습으로 z-파라미터 fit, 뒤=안 본 기간 검정) ──")
    for cut in CUTS:
        fit, test = df[df.index < f"{cut}-01-01"], df[df.index >= f"{cut}-01-01"]
        row = []
        for name, w in CANDIDATES.items():
            r_test, _ = monthly_corr(composite(test, fit, w), vix)
            row.append(f"{name} {r_test:+.3f}")
        print(f"  {cut} 분할 (검정 {len(test)}회의):  " + " | ".join(row))

    print("\n※ 홀드아웃에서 일관되게 |상관|이 가장 큰 후보를 채택. "
          "minutes 는 회의일 정렬(공개는 3주 뒤)임을 해석 시 명시할 것.")


if __name__ == "__main__":
    main()
