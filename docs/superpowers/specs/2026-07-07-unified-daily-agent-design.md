# 통합 실시간 감성 에이전트 (Unified Daily Sentiment Agent) — 설계

_2026-07-07 · approach B_

## 목적

FOMC·뉴스 감성 index를 **시장위험 지표(S&P·VIX·2년물 금리)** 와 **매일 비교**해 **실시간 신호**로 제공한다. 하나의 LangGraph 에이전트가 매일 자동 실행되며, FOMC 성명문이 나온 날은 그 톤도 흡수한다. **예측이 아니라 "오늘의 현황" 신호(경향).**

## 범위 밖 (YAGNI)

- 거시 경제지표(GDP·물가·고용) 비교 — 별개 방향(예측성), 하지 않음
- offset=1 회의 백테스트(`signals.py`+`analyze_alignment`) — **검증용으로 별도 유지**(이 에이전트가 아님)
- LLM 기반 오케스트레이션 — "규칙기반·LLM 미사용" 원칙 유지

## 아키텍처

매일 07:00 KST(=22:00 UTC, 미국 마감 후) 스케줄 → LangGraph 에이전트 1회:

```
collector ─ 오늘 새 FOMC 성명문 있나?
   ├─ 있음 → analyst: 성명문 FinBERT → Fed 톤(신규)
   └─ 없음 → Fed 톤 = 직전 회의 이월(carry-forward)
        ↓
news ──── 오늘 뉴스 → News 톤 → 결합(headline)
        ↓
market ── 오늘 시장(S&P·VIX·2년물, 당일 = offset=0)
        ↓
strategy ─ 신호 A(급변)·B(괴리)·C(톤-VIX)·D(톤-금리)
        ↓
reporting ─ 오늘의 지수·신호 → outputs → (deploy) → 대시보드
```

## 구성요소

**재사용(그대로):** `graph.py` 6노드 골격 · `news_index_live` · `collect_market`(S&P·VIX·2년물) · `signals.py` 신호함수 A~D · `daily-news.yml` 스케줄

**새로/변경(핵심 3):**
1. **일별 모드 라우팅** (`graph.py`) — collector가 성명문 유무 판단 → 없으면 Fed 이월 경로(analyst 건너뜀)
2. **신호 레이어 offset=0 일원화** (아래 §신호)
3. **스케줄이 에이전트 구동** — `daily-news.yml`이 단순 래퍼 대신 `graph.orchestrate(오늘)` 호출

## 신호 레이어 (핵심 결정)

- strategy 노드가 신호 **A·B·C·D를 당일(offset=0)** 로 계산: 톤 vs **당일** 시장.
- `signals.py` 함수는 순수(`tone, market_ret → 판정`)라 일별에 그대로 적용됨.
- **스케일 분리**: 표시용 index는 z-표준화(headline), **신호 계산용 톤은 raw conf_weighted** — θ가 raw 기준으로 보정됐으므로 raw 유지(θ 재보정 회피).
- **신뢰도 게이트**(기사수·CI, `news_signals`에서) → 저데이터 날 '관망'으로 헛경보 방지.
- News 전용 extra(extreme/sign_flip)는 선택; 회의 offset=1 백테스트는 분리 보존.

## 산출물

- `outputs/daily_index.csv` (일별 결합 지수 + CI)
- `outputs/daily_signals.csv` (일별 신호 A~D + 등급 + 게이트)
- → deploy 브랜치 커밋 → 대시보드가 읽음(대시보드 표시는 별도 작업)

## 테스트

- 일별 모드(성명문 없는 날) 라우팅 단위테스트 — Fed 이월·analyst 건너뜀
- 신호 A~D 순수함수 (기존 테스트 유지)
- 오프라인 더미엔진 스모크 — 그래프가 관통(END 도달)하는지

## 리스크·완결 조건

- **FRED 2년물**: `FRED_API_KEY` 시크릿 필요(refresh.yml에서 이미 사용 → 설정됨).
- **시장 시점**: 미국 기준. 07:00 KST = 미국 마감 후 → "간밤 신호". 날짜는 미국(ET) 기준 정렬.
- **대시보드 표시**: 이 에이전트는 `daily_signals.csv`를 산출까지. 화면 표시는 deploy(대시보드) 팀 작업.
- **완결**: 스케줄이 에이전트를 구동하고, 일별 지수+신호 CSV가 매일 deploy에 갱신되면 완료.
