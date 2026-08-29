"""세 축(성명문·회의록·기자회견) 완성도 추적 + 미완성 회의 재방문 목록.

★자동화 설계의 핵심 — **세 축은 도착 시각이 다르다**:
    성명문   회의 당일
    기자회견 회의 며칠 후 (트랜스크립트 게시)
    회의록   회의 **3주 후**
따라서 "회의 당일 한 번 처리하고 끝"이면 늦게 오는 축을 영원히 놓친다.
매일 **미완성 회의를 다시 방문**해야 사람 개입 없이 3축이 채워진다.

  pending_meetings(months=6) → 최근 N개월 회의 중 3축이 덜 찬 날짜들 (재처리 대상)
  write_status()             → outputs/axis_status.csv (회의별 보유 축·톤·완성도)

실행: python3 analysis/axis_status.py          # 현황 출력 + CSV 갱신
"""
import csv
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.minutes_index import has_minutes                      # noqa: E402
from analysis.presser_index import has_presser                      # noqa: E402

DB = ROOT / "data" / "fomc.db"
OUT = ROOT / "outputs" / "axis_status.csv"
STATEMENT_DIR = ROOT / "data" / "statements"
# 재방문 창 — 회의록이 3주 후 공개되므로 6개월이면 충분히 여유롭다(회의 약 4건).
DEFAULT_MONTHS = 6
# 기자회견은 2011-04 신설 → 그 전 회의는 '없는 게 정상'이라 미완성으로 세지 않는다.
PRESSER_START = "2011-04-01"


def has_statement(date: str) -> bool:
    return (STATEMENT_DIR / f"FOMC_statement_{date}.txt").exists()


def meeting_dates():
    """회의일 — DB 우선(가장 정확), 없으면 성명문 파일명."""
    if DB.exists():
        con = sqlite3.connect(DB)
        rows = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM documents WHERE doc_type='statement' ORDER BY date")]
        con.close()
        if rows:
            return rows
    import re
    return sorted(m.group(1) for f in STATEMENT_DIR.glob("FOMC_statement_*.txt")
                  if (m := re.search(r"(\d{4}-\d{2}-\d{2})", f.name)))


def expected_axes(date: str):
    """그 회의에서 **기대되는** 축 — 기자회견은 2011-04 이후에만 존재."""
    axes = ["statement", "minutes"]
    if date >= PRESSER_START:
        axes.append("presser")
    return axes


def axis_state(date: str):
    """{축: 보유여부} + 완성도. 기대되지 않는 축은 제외한다."""
    have = {"statement": has_statement(date), "minutes": has_minutes(date),
            "presser": has_presser(date)}
    exp = expected_axes(date)
    return have, exp, sum(1 for a in exp if have[a]), len(exp)


def finalized_dates(db=None):
    """확정판(fed_composite_final)이 기록된 회의일 집합. DB 없으면 None.

    db 기본값을 None 으로 두고 호출 시점에 모듈 변수 DB 를 읽는다 — 기본 인자로
    DB 를 직접 걸면 import 시점 경로가 고정돼 테스트의 monkeypatch 가 무시된다.
    """
    db = DB if db is None else db
    if not Path(db).exists():
        return None
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute(
            "SELECT date FROM meetings "
            "WHERE method='fed_composite_final' AND granularity='meeting'")}
    finally:
        con.close()


def pending_meetings(months=DEFAULT_MONTHS):
    """최근 N개월 회의 중 **확정판(3축 결합)이 아직 기록되지 않은** 날짜 — 매일 재방문 대상.

    ★판정 기준 교체(2026-08): '파일이 다 수집됐는가' → '확정판이 DB 에 기록됐는가'.
    파일 기준의 결함: 회의록 **파일**이 도착한 아침, 수집 단계(run_news_daily ⓪-b)가
    에이전트 단계(③)보다 먼저 돌아 그 회의를 '완성'으로 바꿔 버린다 — 그 순간 재방문
    목록에서 빠져, 정작 톤 산출과 3축 결합은 영영 실행되지 않는다.
    (실제 사고: 2026-07-29 — minutes 파일은 있는데 minutes_tones·composite 가 없었다.)
    확정판은 에이전트가 3축을 실제로 결합해야만 생기므로(graph.py, minutes 포함 시 1회 기록)
    이 기준이면 수집과 처리 사이의 간극이 없다. DB 가 없으면 종전 파일 기준으로 폴백.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=months * 31)).strftime("%Y-%m-%d")
    dates = [d for d in meeting_dates() if d >= cutoff]
    done = finalized_dates()
    if done is not None:
        return [d for d in dates if d not in done]
    return [d for d in dates                      # 폴백(초기 부트스트랩): 종전 기준
            if (lambda st: st[2] < st[3])(axis_state(d))]


def write_status(path=OUT):
    """전 회의 축 현황 → CSV (무엇이 아직 안 왔는지 한눈에)."""
    rows = []
    for d in meeting_dates():
        have, exp, got, total = axis_state(d)
        rows.append({"date": d,
                     "statement": int(have["statement"]), "minutes": int(have["minutes"]),
                     "presser": int(have["presser"]) if "presser" in exp else "",
                     "n_axes": got, "expected": total,
                     "complete": int(got == total)})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "statement", "minutes", "presser",
                                          "n_axes", "expected", "complete"])
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    rows = write_status()
    done = sum(r["complete"] for r in rows)
    print(f"축 현황: {len(rows)}회의 중 완성 {done} · 미완성 {len(rows) - done}  → {OUT}")
    for axis in ("statement", "minutes", "presser"):
        n = sum(1 for r in rows if r[axis] == 1)
        print(f"  {axis:10} {n}회의")
    pend = pending_meetings()
    print(f"\n재방문 대상(최근 {DEFAULT_MONTHS}개월 미완성): {len(pend)}건")
    for d in pend:
        have, exp, got, total = axis_state(d)
        miss = [a for a in exp if not have[a]]
        print(f"  {d}  {got}/{total}  대기중: {', '.join(miss)}")


if __name__ == "__main__":
    main()
