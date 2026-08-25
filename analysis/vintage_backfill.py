"""git 이력에서 시점 기록을 복원 — 자동화가 매일 커밋한 스냅샷을 되짚는다.

시점 기록(analysis/vintage.py)은 오늘부터 쌓이지만, 그 이전 구간은 이미 덮어써졌다.
다행히 자동화 봇이 매일 deploy 브랜치에 결과 파일을 커밋해 두었으므로,
**각 커밋 시점의 파일 내용 = 그날 시스템이 알고 있던 값**으로 되살릴 수 있다.

    커밋 A (8/11) 의 daily_signals.csv  →  as_of=2026-08-11 기록
    커밋 B (8/12) 의 daily_signals.csv  →  as_of=2026-08-12 기록 (달라진 회의만)

한계: 봇 커밋이 시작된 이후 구간만 복원된다. 그 이전은 복원 불가(기록이 없음).

실행: python3 analysis/vintage_backfill.py [브랜치]
"""
import csv
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.vintage import MEETING_FIELDS, MEETING_VINTAGE, record  # noqa: E402

DEFAULT_BRANCH = "origin/deploy/streamlit-dashboard"
# 복원 대상 — (파일, 그 파일에서 뽑을 값)
SIGNALS = "outputs/daily_signals.csv"
MINUTES = "outputs/minutes_tones.csv"
PRESSER = "outputs/presser_tones.csv"


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=ROOT).stdout


def _commits(branch, path):
    """(커밋, 날짜) 목록 — 오래된 것부터."""
    out = _git("log", branch, "--format=%H|%cI", "--", path).strip()
    rows = [l.split("|") for l in out.split("\n") if l]
    return [(sha, when[:10]) for sha, when in reversed(rows)]


def _blob_rows(sha, path):
    txt = _git("show", f"{sha}:{path}")
    if not txt.strip():
        return []
    return list(csv.DictReader(io.StringIO(txt)))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _latest_blob_by_day(branch, path):
    """{날짜: 그날까지의 최신 파일 내용(rows)} — 커밋이 있는 날만."""
    return {when: _blob_rows(sha, path) for sha, when in _commits(branch, path)}


def backfill(branch=DEFAULT_BRANCH):
    """세 파일의 커밋 스냅샷을 합쳐 회의별 시점 기록을 복원.

    ★파일마다 커밋된 날이 다르다. 그날 커밋이 없는 파일을 '값 없음'으로 두면
    있던 값이 사라졌다가 다시 생긴 것처럼 보이므로(허위 변경), **직전 스냅샷을
    이어받아** 각 날짜의 완전한 상태를 만든 뒤 기록한다.
    """
    snaps = {p: _latest_blob_by_day(branch, p) for p in (SIGNALS, MINUTES, PRESSER)}
    days = sorted({d for s in snaps.values() for d in s})
    if not days:
        return 0, []

    cur = {p: [] for p in snaps}       # 파일별 '현재까지 최신' 내용
    written = 0
    for when in days:
        for p in snaps:
            if when in snaps[p]:       # 그날 커밋이 있으면 갱신, 없으면 직전 것 유지
                cur[p] = snaps[p][when]

        state = {}                      # {회의일: {필드}}
        for r in cur[SIGNALS]:
            if r.get("date"):
                state.setdefault(r["date"], {}).update({
                    "combined": _f(r.get("index")), "grade": r.get("grade"),
                    "fired": r.get("fired") or "",
                })
        for path, key in ((MINUTES, "minutes"), (PRESSER, "presser")):
            for r in cur[path]:
                if not r.get("date"):
                    continue
                s = state.setdefault(r["date"], {})
                s[key] = _f(r.get(key))
                if _f(r.get("statement")) is not None:
                    s["statement"] = _f(r.get("statement"))

        for date in sorted(state):
            v = state[date]
            n = sum(v.get(k) is not None for k in ("statement", "minutes", "presser"))
            if record(MEETING_VINTAGE, date, {**v, "n_axes": n},
                      MEETING_FIELDS, as_of=when):
                written += 1
    return written, days


def main():
    branch = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BRANCH
    written, days = backfill(branch)
    if not days:
        print(f"복원할 이력이 없습니다 ({branch}).")
        return
    print(f"복원 완료: {written}행 기록 · 스냅샷 {len(days)}일 ({days[0]} ~ {days[-1]})")
    print(f"→ {MEETING_VINTAGE}")
    print("\n※ 봇 커밋 이전 구간은 기록이 없어 복원되지 않습니다.")


if __name__ == "__main__":
    main()
