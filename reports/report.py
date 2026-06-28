"""더미 보고서 생성 (Phase 2). 수치는 DB에서 직접 인용 (환각 차단 원칙)."""
from pathlib import Path


def write_report(conn, date: str, report_dir) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    meetings = conn.execute(
        "SELECT method, index_value, confidence FROM meetings WHERE date = ? "
        "AND granularity = 'meeting' ORDER BY method",
        (date,),
    ).fetchall()
    n_sent = conn.execute(
        "SELECT COUNT(*) FROM sentences WHERE date = ?", (date,)
    ).fetchone()[0]

    lines = [
        f"# FOMC 감성 보고서 — {date}",
        "",
        f"- 분석 문장 수: {n_sent}",
        "",
        "## 인덱스",
    ]
    for method, value, conf in meetings:
        lines.append(f"- {method}: {value:+.4f} (confidence {conf:.3f})")
    lines += ["", "_(thin-slice 더미 보고서. 시장 비교·신호는 Phase 5~6에서 추가)_"]

    out = report_dir / f"report_{date}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
