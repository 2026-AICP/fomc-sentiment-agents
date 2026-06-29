"""감성 보고서 생성. 수치는 DB에서 직접 인용 (환각 차단 원칙).

포함 내용:
  1. 회의 인덱스 (label_avg / conf_weighted)
  2. 회의 전체 감성 분해 (평균 긍정/중립/부정 %)
  3. 문장별 감성 분해 (긍정/중립/부정 % + 불확실성)
  (시장 비교·신호는 Phase 5~6 에서 추가)
"""
from pathlib import Path


def write_report(conn, date: str, report_dir) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    meetings = conn.execute(
        "SELECT method, index_value, confidence FROM meetings WHERE date = ? "
        "AND granularity = 'meeting' ORDER BY method",
        (date,),
    ).fetchall()

    sentences = conn.execute(
        "SELECT sentence_idx, sentence, p_pos, p_neu, p_neg, entropy "
        "FROM sentences WHERE date = ? ORDER BY sentence_idx",
        (date,),
    ).fetchall()
    n_sent = len(sentences)

    # 회의 전체 평균 감성 (퍼센티지)
    avg = conn.execute(
        "SELECT AVG(p_pos), AVG(p_neu), AVG(p_neg) FROM sentences WHERE date = ?",
        (date,),
    ).fetchone()
    avg_pos, avg_neu, avg_neg = (v or 0.0 for v in avg)

    lines = [
        f"# FOMC 감성 보고서 — {date}",
        "",
        f"- 분석 문장 수: {n_sent}",
        "",
        "## 1. 회의 인덱스",
    ]
    for method, value, conf in meetings:
        lines.append(f"- {method}: {value:+.4f} (confidence {conf:.3f})")

    lines += [
        "",
        "## 2. 회의 전체 감성 분해 (평균)",
        f"- 긍정 {avg_pos*100:.1f}%  |  중립 {avg_neu*100:.1f}%  |  부정 {avg_neg*100:.1f}%",
        "",
        "## 3. 문장별 감성 분해",
        "",
        "| # | 문장 | 긍정% | 중립% | 부정% | 불확실성 |",
        "|---|------|------:|------:|------:|--------:|",
    ]
    for idx, sent, pp, pn, pg, ent in sentences:
        s = sent.replace("|", "/")
        if len(s) > 90:
            s = s[:87] + "..."
        lines.append(
            f"| {idx} | {s} | {pp*100:.1f} | {pn*100:.1f} | {pg*100:.1f} | {ent:.2f} |"
        )

    lines += ["", "_(시장 비교·위험/기회 신호는 Phase 5~6 에서 추가)_"]

    out = report_dir / f"report_{date}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
