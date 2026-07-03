# Phase 7 — 멀티에이전트 설계 (LangGraph)

> 상태: 설계(초안). 구현 전 팀·교수 합의. 원칙: "함수(도구) 먼저 검증 → 에이전트로 승격".
> 근거: 도구는 Phase 3~6에서 완성(scrape·sentiment·aggregate·signals·backtest·report).

---

## 0. 목적과 원칙

Phase 1~6에서 검증된 **도구(순수 함수)**를 LangGraph 노드로 감싸, 수집→감성→비교→신호→보고를
자동 연결하는 멀티에이전트 파이프라인을 만든다. **새 분석 로직은 만들지 않는다** (도구는 이미 있음).

**신뢰도 제1원칙 (금융 정보 — 사람들이 투자에 활용):**
- **숫자·신호·판정은 100% 규칙기반** (DB/계산에서 직접). LLM이 수치를 만들지 않는다.
- **재현 가능·추적 가능**해야 한다 (같은 입력 → 같은 출력).
- 모든 출력에 **신뢰도·한계·면책** 동봉. "예측 아닌 경향".

---

## 1. 아키텍처

```
                 ┌─────────────── Orchestrator ───────────────┐
                 │  트리거·라우팅·상태관리·재시도·에러처리        │
                 └───┬───────┬───────────┬──────────┬─────────┘
                     ▼       ▼           ▼          ▼
              Data Collector → Sentiment → Market → Strategy &
                             Analyst    Comparison  Reporting
```

| 에이전트 | 역할 | 감싸는 도구(기존) |
|---|---|---|
| **Orchestrator** | 흐름 제어·상태·재시도·에러 | (LangGraph 자체) |
| **Data Collector** | FOMC 성명문(·뉴스) 수집 | `engine/scrape.py` |
| **Sentiment Analyst** | 문장 감성 + 인덱스 산출 | `engine/sentiment.py`, `index/aggregate.py` |
| **Market Comparison** | 시장 데이터 정렬·정합/괴리 | `analysis/collect_market.py`, `analysis/signals.py`(정합) |
| **Strategy & Reporting** | 신호 생성 + 보고서 | `analysis/signals.py`, `analysis/backtest.py`, `reports/report.py` |

→ 각 노드 = "기존 도구를 호출하는 얇은 함수". 로직은 도구에, 조율은 그래프에.

## 2. 상태(State) 설계

에이전트 간 주고받는 데이터 (LangGraph State):

```python
class PipelineState(TypedDict):
    date: str                 # 대상 회의일
    statement_path: str       # 수집된 성명문 파일 경로
    n_sentences: int
    index: dict               # {conf_weighted, label_avg, confidence}
    market: dict              # {spx_ret, vix_chg, vix_level}
    signals: dict             # {grade, tone_shift, divergence, tone_vs_vix, confidence}
    report_path: str          # 생성된 보고서 경로
    errors: list              # 단계별 오류 (재시도·로깅용)
```

→ 각 노드가 자기 결과를 State에 채우고 다음 노드로 넘김.

## 3. 에이전트별 상세

**① Data Collector**
- 입력: date(또는 "최신 감지"). 출력: statement_path
- 도구: `scrape.discover_statements()`, `scrape.fetch_statement()`
- 멱등: 이미 수집된 회의는 건너뜀. 실패 시 재시도(Orchestrator).

**② Sentiment Analyst**
- 입력: statement_path. 출력: index
- 도구: `sentiment.analyze()`(문장별), `aggregate.aggregate_meeting()`
- 보정 엔진(finbert-cal, T=3.1) 사용 → 인덱스 정직성.

**③ Market Comparison**
- 입력: date. 출력: market
- 도구: `collect_market`(S&P500·VIX), 발표일 정렬(14:00 ET 유의)
- ust2y/10y는 FRED 키 확보 후.

**④ Strategy & Reporting**
- 입력: index + market. 출력: signals, report_path
- 도구: `signals`(A·B·C+등급), `report.write_report()`
- 백테스트 근거(적중률·CI)는 사전 계산본 인용.

## 4. 보고서 신뢰도 설계 (★ 결정: 규칙기반 확정)

**결정: 전 과정 규칙기반. LLM 미사용.** (금융 정보 — 신뢰도·재현성 최우선)

```
모든 수치·신호·등급·적중률·서술 = DB/계산에서 직접 (환각 0, 재현·감사 가능)
   예: "톤 +0.16 | 시장 -0.85% | 🔴경고 | 괴리 적중률 48%(CI 36–61%)"
   → 현 report.py 방식(환각 차단 원칙) 유지·확장
```

**왜 규칙기반만 (LLM 불필요):**
- 우리 성명문은 짧고, 보고서는 "수치·신호 정리"라 LLM의 강점(장문 요약·자유서술)이 약함.
- 금융 정보에 LLM 서술은 환각·비결정성·책임 리스크만 늘림.
- 부실 우려는 LLM이 아니라 **규칙기반 요소 추가**로 해결:
  문장별 감성표 · 직전 대비 변화 · 백테스트 근거("유사 N건 중 X건") · 국면 태그 · 신뢰도/CI.

**웹 대시보드도 동일:** 규칙기반 결과를 Streamlit으로 시각화. LLM 미사용
(대시보드는 "표현"이지 "생성"이 아님 → LLM 자리 없음).

**단, 평가에서 "LLM 활용"을 명시 요구할 경우에만** — 보고서 하단에 "AI 생성 요약"
라벨을 단 자연어 문단을 보조로 추가하되, ① 숫자는 고정 주입 ② 출력 숫자를 원본과
대조 검증 ③ 불일치 시 폐기. (기본값은 미사용.)

## 5. LLM 사용 경계 (기본: 미사용)

**기본 방침: LLM 미사용.** 전 과정(에이전트·보고서·대시보드) 규칙기반.
아래는 평가에서 "LLM 활용"을 명시 요구할 때만 적용하는 예외 경계:

| 용도 | LLM 사용? |
|---|---|
| 인덱스·신호·적중률 등 수치 | ❌ 절대 (규칙기반) |
| 신호 발동 판정(A/B/C) | ❌ (규칙기반 임계값) |
| 회의 요약 자연어 풀이 (보조) | ⚪ 기본 미사용 / 요구 시만(검증 게이트) |

→ 넣더라도 LLM은 "말투"만, "판단·숫자"는 규칙기반.

## 6. 트리거 (실행 시점)

```
· 수동:      python3 로 파이프라인 1회 (지금 단계)
· 반자동:    새 회의 날짜 지정 실행
· 자동(Phase 8): 스케줄러가 새 FOMC 감지 → 파이프라인 → 갱신
```

## 7. 구현 계획 (thin-slice — 과도하게 X)

```
1단계: 최소 뼈대 (3노드)
   Collector → Analyst → Reporting  (Market·Strategy 나중)
   → 도구 감싸서 end-to-end 1회 돌아가나 (더미/1건)

2단계: 확장
   + Market Comparison, + Strategy(신호)
   → 5에이전트 완성, 무인 1회 관통 (합격선)

3단계: LLM 요약 (선택)
   + Strategy 노드에 검증된 LLM 요약

4단계: (Phase 8) 스케줄러 자동화
```

## 8. 의존성·한계

- `requirements.txt`의 langgraph·langchain 활성화 필요 (현재 주석).
- LLM 쓰면 Claude API 키·비용 (환경변수로).
- 표본 작음·상관≠인과·톤≠스탠스 (기존 한계 동일).
- 에이전트는 "판단"이 아니라 "검증된 도구의 조율" — 신뢰도는 도구 품질에서.

## 9. 결정 필요 항목

| 항목 | 선택지 | 결정/권장 |
|---|---|---|
| LLM 요약 | 넣음 / 안 넣음 | **안 넣음 (규칙기반 확정)** — 신뢰도·재현성 우선 |
| 트리거 | 수동 / 자동 | 수동부터 (Phase 8에서 자동) |
| 뉴스 수집 | 포함 / FOMC만 | FOMC만부터 |
