#!/bin/sh
# 뉴스 데일리 자동화 — 한 번에: 수집(API) → FinBERT 일별 News 지수 → Fed 계단 결합.
# cron/launchd/서버가 매일 이 스크립트 하나만 호출하면 됨.
#   예(cron):  0 6 * * *  /경로/fomc-sentiment-agents/scripts/run_news_daily.sh >> /경로/logs/news_cron.log 2>&1
set -e
# 저장소 루트를 스크립트 위치 기준으로 찾음 (경로 하드코딩 X → 이식성)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
export PYTHONWARNINGS=ignore TRANSFORMERS_VERBOSITY=error TOKENIZERS_PARALLELISM=false

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 뉴스 데일리 자동화 시작 ====="
python3 agents/news_scheduler.py     # ① 수집 + FinBERT → 일별 News 지수 (+오늘의 감성)
python3 analysis/daily_index.py      # ② Fed 계단 + 매일 News → 일별 결합(headline)
python3 analysis/news_signals.py     # ③ 당일(offset=0) 신호 — 뉴스 vs 당일 시장 → outputs/news_signals.csv
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 완료 ====="
