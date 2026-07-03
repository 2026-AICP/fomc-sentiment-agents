# Phase 8 — 운영: 스케줄러 · 로깅 · 파이프라인 성공률

> 상태: 완료. Phase 7 무인 파이프라인(`agents/graph.py`) 위에 **운영 계층**만 추가.
> 새 분석 로직 없음 — 스케줄·기록·집계뿐. 계획: `docs/phase8_plan.md`.

---

## 1. 무엇이 추가됐나

| 파일 | 역할 |
|---|---|
| `agents/runlog.py` | 실행 결과를 `logs/pipeline_runs.jsonl`(회의 1건=1줄)로 기록 + `summarize`(성공률 집계, 순수) |
| `agents/scheduler.py` | 미처리 회의 탐지 → 무인 실행 → 로그·성공률 갱신. "한 번 돌고 종료"(데몬 아님) |
| `agents/graph.py` | `orchestrate(..., on_result=콜백)` 1개 추가(하위호환) — 로그 연결용 |

## 2. 사용법

```bash
# 미처리(리포트 없는) 회의만 실행 + 성공률 갱신
SENTIMENT_ENGINE=finbert python3 agents/scheduler.py

# 전체 재실행
SENTIMENT_ENGINE=finbert python3 agents/scheduler.py --all

# 성공률 리포트만 (실행 없이 집계)
python3 agents/scheduler.py --health
```

- 산출물: `reports/agent_out/pipeline_health.md` (성공률 + 최근 실행표), `logs/pipeline_runs.jsonl` (원장). 둘 다 `.gitignore`.
- Windows는 `python3` 대신 `py`(또는 이 레포 `.venv\Scripts\python.exe`). 콘솔 이모지 위해 `PYTHONUTF8=1` 권장.

## 3. 스케줄 등록 (OS에 위임)

상시 데몬을 만들지 않는다. 스케줄러는 "한 번 실행"이므로 **OS 스케줄러**가 주기 호출한다.
FOMC는 연 8회뿐이라 하루 1회 체크로 충분(새 회의 없으면 즉시 종료).

**Linux/macOS (cron) — 매일 09:00:**
```cron
0 9 * * *  cd /path/to/fomc-sentiment-agents && SENTIMENT_ENGINE=finbert .venv/bin/python agents/scheduler.py >> logs/cron.log 2>&1
```

**Windows (작업 스케줄러):**
```powershell
$py  = "C:\...\fomc-sentiment-agents\.venv\Scripts\python.exe"
$dir = "C:\...\fomc-sentiment-agents"
$act = New-ScheduledTaskAction -Execute $py -Argument "agents\scheduler.py" -WorkingDirectory $dir
$trg = New-ScheduledTaskTrigger -Daily -At 9am
Register-ScheduledTask -TaskName "FOMC-Pipeline" -Action $act -Trigger $trg
# 환경변수는 래퍼 .bat(SENTIMENT_ENGINE·PYTHONUTF8 설정)로 지정 권장
```

## 4. 성공률 해석 (합격선)

- **성공률 = 정상(ok) / 전체.** 회의 1건 실행 = 로그 1줄.
- 상태 구분:
  - **ok**: 그래프 관통 + 오류 0 + 리포트 생성.
  - **부분오류**: 관통했으나 노드 일부 오류(예: market 오프라인 → Fed만으로 진행).
  - **실패**: 그래프 레벨 예외(재시도 후에도). 배치는 죽지 않고 다음 회의로 계속.
- 로컬 검증: 2건 실행 → **성공률 100%(2/2)**. `market` 노드는 네트워크 실패 시 부분오류로 강등되며 전체는 계속된다.

## 5. 한계 / 다음(선택)
- 스케줄은 OS에 위임(이식성·단순성). 분산 큐·재시도 백오프는 범위 밖.
- 통합 z-표준화(GPU 재생성 후), 웹 대시보드(Streamlit)는 여전히 선택 과제.
- 뉴스 실시간 축은 발표일 근처에만 유효(과거 회의는 Fed 단독) — 성공률과 무관.
