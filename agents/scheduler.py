"""Phase 8 — 스케줄러: 미처리 회의 자동 실행 + 파이프라인 성공률 리포트.

새 FOMC 회의(성명문은 있으나 리포트가 아직 없는 것)를 찾아 무인 실행하고,
실행 로그를 남긴 뒤 성공률을 집계한다. 상시 데몬이 아니라 "한 번 돌고 종료" →
OS 스케줄러(cron / Windows 작업스케줄러)가 주기 호출한다. (docs/phase8_ops.md)

사용:
  SENTIMENT_ENGINE=finbert python3 agents/scheduler.py         # 미처리만 실행
  SENTIMENT_ENGINE=finbert python3 agents/scheduler.py --all   # 전체 재실행
  python3 agents/scheduler.py --health                         # 성공률 리포트만
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import graph, runlog


def pending_dates(all_dates, report_dir):
    """리포트가 아직 없는 회의만 (성명문은 있으나 미처리). 순수 함수."""
    report_dir = Path(report_dir)
    return [d for d in all_dates if not (report_dir / f"report_{d}.md").exists()]


def health():
    """실행 로그 → 성공률 리포트(reports/agent_out/pipeline_health.md) + 콘솔."""
    runs = runlog.read_runs()
    s = runlog.summarize(runs)
    lines = [
        "# 파이프라인 성공률 (Phase 8)",
        "",
        f"- 총 실행: {s['total']}건",
        f"- **성공률: {s['success_rate']:.0%}**  "
        f"(정상 {s['ok']} · 부분오류 {s['partial']} · 실패 {s['failed']})",
        f"- 평균 소요: {s['avg_duration_s']:.1f}s",
        "",
        "## 최근 실행 (최대 10건)",
        "",
        "| 시각(UTC) | 회의 | 등급 | 상태 | 소요s |",
        "|---|---|---|---|--:|",
    ]
    for r in runs[-10:]:
        lines.append(f"| {str(r.get('ts',''))[:19]} | {r.get('date','')} | {r.get('grade') or '—'} "
                     f"| {r.get('status','')} | {r.get('duration_s','')} |")
    out_dir = Path(graph.REPORTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "pipeline_health.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"성공률 {s['success_rate']:.0%} ({s['ok']}/{s['total']}) → {path}")
    return path


def run(dates=None, all_=False, retries=1):
    """미처리(기본) 또는 전체(all_) 회의를 무인 실행하고 로그·성공률을 갱신한다."""
    all_dates = sorted(graph._discover_local_dates())
    if dates is None:
        dates = all_dates if all_ else pending_dates(all_dates, graph.REPORTS)
    if not dates:
        print("처리할 새 회의 없음 (모두 리포트 존재).")
        return []
    print(f"대상 {len(dates)}건 무인 실행\n── 결과 ──")
    results = graph.orchestrate(dates=dates, retries=retries, on_result=runlog.append_run)
    health()   # 실행 후 성공률 갱신
    return results


if __name__ == "__main__":
    try:  # Windows cp949 콘솔에서도 이모지 출력되게
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    argv = sys.argv[1:]
    if "--health" in argv:
        health()
    else:
        run(all_="--all" in argv)
