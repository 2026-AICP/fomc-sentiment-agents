"""Phase 8 — 파이프라인 실행 로그 (JSONL) + 성공률 집계.

무인 실행(agents/graph.orchestrate)의 회의별 결과를 한 줄씩 기록하고,
성공률·부분오류·실패를 집계한다. summarize 는 순수 함수라 테스트가 쉽다.

로그: logs/pipeline_runs.jsonl (gitignore됨) — 회의 1건 = 1줄.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
RUNLOG = ROOT / "logs" / "pipeline_runs.jsonl"


def append_run(rec: dict, path: Path = RUNLOG) -> None:
    """실행 결과 1건을 JSONL 로 추가. ts 없으면 현재 UTC 시각을 넣는다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"ts": rec.get("ts") or datetime.now(timezone.utc).isoformat(), **rec}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def read_runs(path: Path = RUNLOG) -> List[dict]:
    """JSONL 로그를 리스트로 읽는다 (없으면 빈 리스트)."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            out.append(json.loads(ln))
    return out


def summarize(runs: List[dict]) -> dict:
    """실행 목록 → 성공률 집계 (순수).

    성공률 = ok / 전체. 부분오류·실패는 별도 카운트.
    """
    n = len(runs)
    ok = sum(1 for r in runs if r.get("ok"))
    failed = sum(1 for r in runs if str(r.get("status", "")).startswith("실패"))
    partial = sum(1 for r in runs if str(r.get("status", "")).startswith("부분오류"))
    durs = [r["duration_s"] for r in runs if isinstance(r.get("duration_s"), (int, float))]
    avg_dur = sum(durs) / len(durs) if durs else 0.0
    return {
        "total": n,
        "ok": ok,
        "partial": partial,
        "failed": failed,
        "success_rate": ok / n if n else 0.0,
        "avg_duration_s": avg_dur,
    }
