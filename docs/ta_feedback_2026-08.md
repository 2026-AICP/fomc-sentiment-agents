# 조교 피드백 반영 — 질문 5·6 (2026-08)

조교님께 여쭤본 두 가지 설계 질문(표본 적은 날의 신호 발동 기준 / Fed 축 확장 시
의사록 지연 처리)에 대한 답변과, 이를 코드에 반영한 내용을 정리한다.

## 질문 5 — 표본이 적은 날의 신호 발동 기준

**문제**: 일별 감성지수는 부트스트랩 95% CI를 계산해 대시보드에 표시하지만, 신호
등급(경고·주의·중립·정합)은 이 CI를 무시하고 점추정치만으로 발동됐다. 실제로 기사
6건(CI가 0을 크게 걸침)인 날에도 "주의"가 발동했다 — `analysis/news_signals.py`의
`confident()` 게이트는 이미 존재했지만, 실제 대시보드용 신호를 만드는
`agents/graph.py::strategy_node`에는 연결돼 있지 않았다.

**답변**: A안(게이팅)·B안(표시)의 절충 — **측정(지수·CI·기사 수)은 그대로 두고,
경보만 게이팅**한다.

**반영**:
- `agents/graph.py::strategy_node` — `news_signals.confident()`를 재사용해, 뉴스
  표본이 `min_articles`(15건) 미만이거나 CI 폭이 `ci_max`(0.60) 이상이면 "주의/경고"를
  `⚪ 관망`(`analysis/signals.GRADE_WATCH`)으로 낮춘다. 결합 지수(`headline`) 값 자체는
  전혀 건드리지 않는다 — 게이트는 등급에만 적용.
- `outputs/daily_signals.csv` / `daily_signals.json`에 `gate_reason`·`n_articles`·
  `ci_lo`·`ci_hi`를 추가해, 왜 관망으로 내려갔는지와 원래 측정값을 함께 노출한다.
- 대시보드(Overview)는 관망 사유가 있으면 KPI 옆에 그대로 표시한다.

## 질문 6 — Fed 축 확장 시 의사록 공개 지연 처리

**문제**: Fed 축을 성명문 단독에서 성명문·기자회견·의사록 1:1:1 결합으로 확장하기로
검증했다(`docs/fed_weights.md`, VIX 상관 -0.418→-0.577). 그러나 의사록은 회의 3주
후 공개되므로, 회의 당일엔 성명문(+기자회견)만으로 지수를 낼 수밖에 없다.

**답변**: 절충안(속보치/확정판 이원화) — 학술적으로 가장 정직한 설계. 단,
**과거 실시간 값을 덮어쓰면 안 된다**는 원칙을 지킨다.

**반영**:
- `analysis/headline.py::combine_fed_axes()` — statement:presser:minutes = 1:1:1
  z-표준화 결합(`analysis/headline_norm.json`의 presser·minutes 통계,
  `analysis/build_fed_axis_norm.py`로 재현). 가용한 성분끼리만 재정규화해, 회의
  당일엔 자동으로 1~2축 결합이 된다.
- `analysis/analyze_alignment.py::upsert_fed_composite()` — 회의별 결합값을
  `meetings` 테이블에 `fed_composite_realtime`(속보치, 확정 전까지만 갱신 가능)과
  `fed_composite_final`(확정판, minutes 도착으로 3축이 다 찼을 때 **단 한 번만** 기록,
  이후 절대 재작성 안 함) 두 method로 분리 저장한다.
- `agents/graph.py::append_daily_signal()` — `outputs/daily_signals.csv`의
  `grade`/`index`(그 날짜에 처음 기록된 속보치)는 재방문해도 절대 수정하지 않는다.
  확정판이 나오면 `grade_final`/`index_final`/`finalized_at`에만 추가로 기록된다 —
  이미 보여준 "그날의 신호"는 사후에 바뀌지 않는다.
- 대시보드는 확정판이 있으면 "회의록 반영 확정판 …" 을 속보치 옆에 병기한다(속보치를
  대체하지 않음).

### 한계

- 재정규화 방식(가용 성분끼리 z 평균)은 `headline.py`의 "뉴스 없으면 Fed 단독" 폴백과
  같은 철학이지만, 성분 수가 다른 회의 간 결합값의 분산이 완전히 같지는 않다.
- 확정판은 의사록 도착 시점에 딱 한 번만 계산한다 — 그 이후 데이터 정정(예: 오분석
  재처리)은 이 메커니즘의 범위 밖이다.
