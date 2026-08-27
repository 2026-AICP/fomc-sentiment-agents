"""Layer 2 — 일별 결합(headline) 시계열 (프로젝트 모델).

Fed 축(성명문·회의록·기자회견 1:1:1 결합, 8×/년)을 계단(carry-forward)으로 깔고
매일 News 지수와 1:1 로 결합한다:
  발표일:     새 성명문 + 그날 뉴스
  발표 이후:  그 성명문 값 유지(carry) + 매일 뉴스
  다음 발표:  성명문 갱신
→ 일별 변동은 News 가 만들고, Fed 는 느린 기준선(계단).

입력:
  · Fed:  data/fomc.db — fed_composite(성명문:회의록:기자회견 = 1:1:1, docs/fed_weights.md)
          ★2026-08: 이전엔 conf_weighted(성명문 단독)를 썼다. PR #4 가 3축 결합을
          agents/graph.py 에만 연결하는 바람에, 같은 날짜의 '통합 지수'가 이 파일과
          outputs/daily_signals.csv 에서 서로 다른 값이 됐다(8/25 는 부호까지 반대였다).
          두 경로가 fed_composite_asof 를 함께 쓰도록 통일한다.
  · News: outputs/news_index_live.csv (agents/news_scheduler.py 산출, 일별)
결합:  analysis.headline.combine — 각 축 z-표준화 후 News:Fed = 1:1
산출:  outputs/daily_headline.csv (date, fed_carry, news, headline, method, n_articles)

실행:  python3 analysis/daily_index.py   (먼저 agents/news_scheduler.py 실행 필요)
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.analyze_alignment import fed_composite_asof
from analysis.headline import combine

DB = ROOT / "data" / "fomc.db"           # 통일 DB (에이전트·pipeline 과 공유)
NEWS_CSV = ROOT / "outputs" / "news_index_live.csv"
OUT = ROOT / "outputs" / "daily_headline.csv"


def load_fed_series(db=DB):
    """(회의일, Fed 3축 결합값) 시간순 리스트. 없으면 빈 리스트.

    값은 fed_composite_asof 가 돌려주는 **z-척도**다(확정판 > 속보치 > 레거시 순).
    회의 시점에 회의록이 아직 없으면 가용한 축끼리만 결합되므로, 회의 당일엔 1~2축,
    회의록 도착 후엔 3축이 된다 — 과거 값을 소급 수정하지 않는 설계(조교 질문 6).
    """
    if not Path(db).exists():
        return []
    con = sqlite3.connect(db)
    try:
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM meetings WHERE granularity='meeting' ORDER BY date")]
        return [(d, v) for d in dates
                if (v := fed_composite_asof(con, d)) is not None]
    finally:
        con.close()


def fed_carry(fed_series, day):
    """day(YYYY-MM-DD) 이하 가장 최근 회의의 Fed 값 (계단). 이전 회의 없으면 None."""
    val = None
    for d, v in fed_series:
        if d <= day:
            val = v
        else:
            break
    return val


def build_daily(news_csv=NEWS_CSV, out=OUT):
    """일별 News + Fed 계단 → 일별 결합(headline) DataFrame(및 CSV 저장)."""
    import pandas as pd
    if not Path(news_csv).exists():
        raise SystemExit(f"News 지수 CSV 없음: {news_csv}\n먼저 agents/news_scheduler.py 실행")
    news = pd.read_csv(news_csv)
    fed_series = load_fed_series()
    rows = []
    for _, r in news.iterrows():
        day = str(r["date"])
        fed = fed_carry(fed_series, day)
        nv = float(r["conf_weighted"])
        # fed 는 이미 z-척도라 combine() 이 다시 표준화하면 척도가 깨진다
        # → fed_stats=(0,1) 로 그대로 통과시킨다 (agents/graph.py 와 동일 처리).
        h = combine(fed, nv, fed_stats=(0.0, 1.0))
        rows.append({
            "date": day,
            "fed_carry": round(fed, 4) if fed is not None else None,
            "news": round(nv, 4),
            "headline": round(h["headline"], 4) if h else None,
            "method": h["method"] if h else None,
            "n_articles": int(r["n_articles"]),
        })
    df = pd.DataFrame(rows)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def main():
    import pandas as pd
    df = build_daily()
    print(f"일별 결합 지수 {len(df)}일 → {OUT}")
    print("── 일별 (Fed 계단 + 매일 News = headline) ──")
    for _, r in df.iterrows():
        fed = f"{r['fed_carry']:+.3f}" if pd.notna(r["fed_carry"]) else "  —  "
        print(f"  {r['date']}  Fed {fed} + News {r['news']:+.3f} "
              f"→ headline {r['headline']:+.3f} ({r['method']}) | 기사 {int(r['n_articles'])}")
    print("\n※ Fed 는 최근 회의의 3축 결합값을 다음 회의까지 유지(계단). 일별 변동은 News가 만듦.")


if __name__ == "__main__":
    main()
