"""Phase 8+ — 뉴스 데일리 자동화 (News 축 전용 트랙).

FOMC 스케줄러(agents/scheduler.py, 이벤트·8×/년)와 별개로, 뉴스는 매일 갱신되므로
이 스크립트를 cron 이 매일 호출한다:
  ① news_scrape (Marketaux API) → 최신 뉴스 fed_news.csv 갱신
  ② news_index_live (FinBERT)   → 일별 News 감성지수(+CI) 재산출
  ③ runlog                      → 실행 기록 (logs/news_runs.jsonl)
  ④ 콘솔에 '오늘의 감성' 요약 (실시간 신호 제공의 기초)

목적(프로젝트 최종 목표): '경제 예측'이 아니라 실시간 감성 게이지 + 신호 제공.

사용:  python3 agents/news_scheduler.py             # 최근 3일 수집 + 지수 갱신
       python3 agents/news_scheduler.py --days 7    # 최근 7일
cron:  0 6 * * *  cd <repo> && python3 agents/news_scheduler.py   # 매일 06:00
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import news_scrape
from analysis import news_index_live
from agents import runlog

NEWS_LOG = ROOT / "logs" / "news_runs.jsonl"
# 수집 창 기본값 — 함수 기본값과 CLI 기본값을 여기 한 곳에서만 정한다.
# (2026-08 까지 run() 은 2, CLI 는 3 으로 갈라져 있었고 실제 운영은 CLI 쪽 3 이었다.)
DEFAULT_DAYS_BACK = 3


def run(days_back=DEFAULT_DAYS_BACK, pages=40):
    """뉴스 수집(API) → 일별 News 지수(FinBERT) → 로그 → 오늘의 감성 요약.

    하루 수집 상한 = pages × PER_PAGE 건.

    ★2026-08 Standard 전환: 요청당 50건이 되어 **전수 회수**가 가능해졌다.
    3일 창 풀이 약 366건이라 8요청이면 다 들어온다(하루 한도 10,000). pages 는
    이제 실제 필요량이 아니라 **안전 상한**이다 — 빈 페이지가 나오면 조기 종료하므로
    높게 잡아도 요청을 낭비하지 않는다. 40쪽 = 2,000건 여유로, 기사가 폭증하는 날
    (FOMC·잭슨홀)이나 group_similar 해제로 풀이 커져도 잘리지 않는다.

    ★그 이전 이력(무료 티어): pages 를 40→80 으로 올린 적이 있다. 뉴스가 많던 7월엔
    최신순 120건이 대부분 신규라 실행당 40~57건이 쌓였는데, 8월 들어 그 120건이 창
    전체에 퍼지며 대부분 이미 가진 기사와 겹쳐 실행당 4~11건으로 떨어졌다. 그 결과
    일별 기사가 신뢰도 게이트 하한(15건, news_signals.Thresholds)을 못 넘어 사이트가
    '낮음'으로 도배됐다. 전수 회수로 이 문제의 원인 자체가 사라진다.

    실측(2026-08-25 CI · 3일 창 · pages=80 · 질의문 변경 전):
      API 매칭 555건 → 받음 189건 → F∧M 통과 25건(13%) → 신규 저장 16건(중복 9)
      page 64 에서 HTTP 402 usage_limit_reached 로 중단.
    회수율·통과율은 2026-08-26 에 질의문(F 필수)과 페이지 실패 처리로 대응했다 —
    경위는 engine/news_scrape.py 의 QUERY·discover_news 주석 참조. 위 수치는 그
    이전 상태의 기록이다.

    양을 늘리는 방법은 둘인데 성질이 다르다. 여기서 쓰는 건 앞의 것이다:
      · 같은 필터로 더 깊이 긁기  → 모집단 그대로, 표본만 확대. 순수 이득.
      · 필터를 느슨하게           → CI 는 좁아지지만 지수가 재는 대상이 바뀐다.
                                    신뢰도 표시만 올라가고 타당도는 떨어지는 최악.
    (F∧M 키워드는 지도교수 지정 사항이라 임의 변경 금지 — docs/filter_audit.md)
    """
    t0 = time.perf_counter()
    # ① 최신 뉴스 수집 (Marketaux API)
    articles, new, found = news_scrape.collect(days_back=days_back, pages=pages)
    # ② 일별 News 감성지수 (FinBERT) — fed_news.csv 전체 재산출
    daily = news_index_live.build_live_index()
    dur = round(time.perf_counter() - t0, 2)

    latest = daily.iloc[-1] if len(daily) else None
    recent = daily.tail(5)["conf_weighted"].mean() if len(daily) else None

    # ③ 실행 로그 (Phase 8 runlog 재사용, 뉴스 전용 파일)
    runlog.append_run({
        "track": "news",
        "n_scraped": len(articles), "n_new": len(new), "found": found,
        "days_covered": int(len(daily)),
        "latest_index": round(float(latest["conf_weighted"]), 4) if latest is not None else None,
        "duration_s": dur, "ok": True, "status": "ok",
    }, path=NEWS_LOG)

    # ④ 오늘의 감성 요약
    print(f"\n── 뉴스 자동화 완료 ({dur}s) ──")
    print(f"  수집: {len(articles)}건 (신규 {len(new)}) | 일별 지수: {len(daily)}일치")
    if latest is not None:
        v, n = float(latest["conf_weighted"]), int(latest["n_articles"])
        mood = "부정" if v < -0.02 else "긍정" if v > 0.02 else "중립"
        trend = f" | 최근5일 평균 {recent:+.3f}" if recent is not None else ""
        print(f"  오늘의 News 감성: {v:+.3f} [{mood}]  (기사 {n}건{trend})")
        lo, hi = latest["ci_lo"], latest["ci_hi"]
        print(f"  신뢰구간: 95% CI {float(lo):+.3f} ~ {float(hi):+.3f}"
              if lo == lo else "  신뢰구간: 계산불가(표본<2)")
    else:
        print("  (아직 뉴스 없음)")
    return daily


if __name__ == "__main__":
    argv = sys.argv[1:]
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else DEFAULT_DAYS_BACK
    try:  # Windows cp949 콘솔에서도 이모지 출력
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"뉴스 데일리 자동화 — 최근 {days}일 수집 → FinBERT → 일별 지수")
    run(days_back=days)
