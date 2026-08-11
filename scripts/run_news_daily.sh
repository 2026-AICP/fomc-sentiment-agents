#!/bin/sh
# 뉴스 데일리 자동화 — 한 번에: 수집(API) → FinBERT 일별 News 지수 → Fed 계단 결합.
# cron/launchd/서버가 매일 이 스크립트 하나만 호출하면 됨.
#   예(cron):  0 6 * * *  /경로/fomc-sentiment-agents/scripts/run_news_daily.sh >> /경로/logs/news_cron.log 2>&1
set -e
# 저장소 루트를 스크립트 위치 기준으로 찾음 (경로 하드코딩 X → 이식성)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
export PYTHONWARNINGS=ignore TRANSFORMERS_VERBOSITY=error TOKENIZERS_PARALLELISM=false

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 데일리 자동화 시작 ====="
python3 engine/scrape.py 3           # ⓪ 최신 FOMC 성명문 증분 수집 (FOMC일이면 새 성명문 확보 → 에이전트가 흡수)
# ⓪-b 회의록(minutes) — 회의 3주 후 공개라 매일 최근 창만 확인(공개되는 날 자동 수집).
#     멱등이라 이미 있으면 요청조차 안 함. 실패해도 아래 뉴스 파이프라인은 계속 진행.
python3 engine/minutes_scrape.py || echo "  warn: 회의록 수집 실패(건너뜀)"
# ⓪-c 기자회견 트랜스크립트 — 회의 며칠 후 게시. 최근 4회의만 확인(멱등, 있으면 skip).
python3 engine/presser_scrape.py || echo "  warn: 기자회견 수집 실패(건너뜀)"
python3 agents/news_scheduler.py     # ① 수집 + FinBERT → 일별 News 지수 (+오늘의 감성)
python3 analysis/daily_index.py      # ② Fed 계단 + 매일 News → 일별 결합(headline)
TODAY_ET="$(TZ=America/New_York date +%F)"   # ③ 통합 에이전트 — 미국(ET) 오늘 날짜 기준
# ③이 실패해도(의존성·네트워크 등) 이미 저장된 수집 결과는 유효하므로 ④는 반드시 실행한다.
# set -e 아래서 한 단계 실패가 뒤 단계를 통째로 막던 문제 방지
# (2026-08: langgraph 미설치로 ③이 죽어 대시보드가 4일간 갱신 안 됨).
python3 - "$TODAY_ET" <<'PY' || echo "  warn: 에이전트 단계 실패 — 대시보드 갱신은 계속 진행"
import sys
from agents import graph
from analysis.axis_status import pending_meetings, write_status

# 오늘 + **미완성 회의 재방문**.
# 세 축은 도착 시각이 다르다(성명문 당일 / 기자회견 며칠 후 / 회의록 3주 후).
# 오늘 날짜만 처리하면 늦게 도착하는 축을 영원히 놓치므로, 최근 6개월 회의 중
# 아직 3축이 안 찬 것을 매일 다시 돌려 새로 도착한 축을 흡수한다.
today = sys.argv[1]
pending = [d for d in pending_meetings() if d != today]
if pending:
    print(f"  재방문(축 미완성): {pending}")
graph.orchestrate(dates=[today] + pending)   # 신호 A~D(offset=0) → outputs/daily_signals.csv
write_status()                               # outputs/axis_status.csv 갱신
PY
# ④ 대시보드 데이터 갱신 — 프론트는 계산하지 않고 이 JSON만 읽는다(환각 차단).
#    실패해도 위 파이프라인 결과는 이미 저장됐으므로 경고만 남긴다.
python3 analysis/export_dashboard.py dashboard-web/public/data \
  || echo "  warn: 대시보드 JSON 갱신 실패(건너뜀)"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 완료 ====="
