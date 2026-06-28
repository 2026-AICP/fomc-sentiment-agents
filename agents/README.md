# agents/ — 멀티에이전트 (Phase 7)

여기는 **Phase 7 전까지 빈 스텁**입니다. 실제 로직은 `pipeline.py`(순수 함수)가 담당하고,
1~6단계가 모두 검증된 뒤 그 함수들을 LangGraph 노드로 "승격"합니다.

| 파일 | 에이전트 | 역할 |
|------|---------|------|
| `orchestrator.py` | Orchestrator | 트리거·라우팅·상태관리·재시도 |
| `collector.py` | Data Collector | FOMC 원문·뉴스·시장지표 수집 |
| `analyst.py` | Sentiment Analyst | 문장 감성 + 인덱스 산출 |
| `comparison.py` | Market Comparison | 톤 ↔ S&P500 ↔ VIX 비교·괴리 |
| `strategy.py` | Strategy & Reporting | 규칙 신호 + 보고서 생성 |
