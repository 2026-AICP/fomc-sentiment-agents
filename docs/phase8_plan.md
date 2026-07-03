# Phase 8 계획 — 스케줄러 · 로깅 · 평가(파이프라인 성공률)

> 상태: 착수. Phase 7(무인 멀티에이전트) 위에서 운영 계층 추가.
> 근거: 구축순서 Phase 8("스케줄러·로깅·평가·README / 파이프라인 성공률").

---

## 0. 목표와 합격선

| 항목 | 내용 |
|---|---|
| 산출물 | ① 실행 로깅 ② 스케줄러(미처리 회의 자동 실행) ③ 평가(파이프라인 성공률 리포트) |
| 합격선 | **파이프라인 성공률** — 무인 실행들이 성공/부분오류/실패로 집계되고 성공률이 산출됨 |
| 원칙 | 새 분석 로직 없음. Phase 7 `orchestrate()`를 **감싸서** 운영(스케줄·기록·집계)만 추가 |
| 비범위 | 웹 대시보드·상시 데몬은 안 만든다(요청 밖). 스케줄은 **OS cron/작업스케줄러**에 위임 |

## 1. 설계 (기존 자산 재사용)

- Phase 7 `agents/graph.py`: 6노드 그래프 + `orchestrate(dates, retries)` 무인 배치(재시도 포함) + `_discover_local_dates()`.
- 리포트: `reports/agent_out/report_<date>.md` (gitignore됨). DB: `data/agent_skeleton.db`.
- → Phase 8은 이 위에 **로그 기록 → 성공률 집계** 만 얹는다.

## 2. 작업 항목 + 검증 기준 (goal-driven)

1. **`agents/runlog.py`** — 실행 로그
   - `append_run(rec)`: `logs/pipeline_runs.jsonl`에 회의 1건 결과 1줄(JSONL) 추가.
   - `read_runs()`, `summarize(runs)`(순수): total·ok·부분오류·실패·**성공률**·평균소요·에러분포.
   - → 검증: `summarize`가 합성 리스트에서 성공률을 정확히 계산 (단위테스트).

2. **`agents/graph.py`** — `orchestrate(..., on_result=None)` 선택 콜백 + 소요시간
   - 회의 1건 끝날 때 결과 dict를 `on_result`로 넘김(있으면). 기본 None = Phase 7 그대로(하위호환).
   - → 검증: 기존 테스트/실행 무변화 + 콜백이 회의당 1회 호출.

3. **`agents/scheduler.py`** — 미처리 탐지 + 무인 실행 + 성공률 리포트
   - `pending_dates(all_dates, report_dir)`(순수): 리포트가 아직 없는 회의만.
   - `run()`: 미처리 회의를 `orchestrate(on_result=runlog.append_run)`로 실행.
   - `--all`(전체 재실행), `--health`(성공률 리포트 `reports/agent_out/pipeline_health.md` 생성), 인자 없음=미처리만.
   - cron/작업스케줄러에서 주기 호출(한 번 돌고 종료 — 데몬 아님).
   - → 검증: `pending_dates`가 리포트 유무로 정확히 필터 (단위테스트) + 소량 e2e 실행.

4. **문서·설정**
   - `docs/phase8_ops.md`: 스케줄 등록법(cron/Windows 작업스케줄러) + 성공률 해석.
   - `README` Phase 8 ✅, `.gitignore`에 `logs/` 추가.

## 3. 성공/부분오류/실패 정의
- **성공(ok)**: 그래프 관통 + 오류 0 + 리포트 생성.
- **부분오류**: 관통했으나 노드 일부 오류(state.errors 존재; 예: market 오프라인).
- **실패**: 그래프 레벨 예외(재시도 후에도).
- 성공률 = ok / 전체.

## 4. 순서
```
1) feat/phase8-ops 브랜치            ✅
2) runlog.py + tests/test_runlog.py       (순수함수 — 데이터 불필요)
3) graph.orchestrate 콜백 추가(하위호환)
4) scheduler.py + tests/test_scheduler.py
5) 소량 e2e (미처리 2건 실행 → 성공률 리포트 확인)
6) docs/phase8_ops.md + README + .gitignore
7) PR
```
