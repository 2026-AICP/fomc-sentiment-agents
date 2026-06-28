"""Thin-slice 파이프라인: 함수들을 직선으로 연결 (에이전트 전 단계).

흐름: 원문 1건 → 문장 분할 → 더미 감성 → 인덱스 집계 → 보고서 1장
재실행 멱등: 결정적 PK + INSERT OR REPLACE 로 두 번 돌려도 행이 중복되지 않는다.
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import db
from engine.preprocess import split_sentences
from engine.dummy_sentiment import analyze, MODEL_TAG
from index.aggregate import aggregate_meeting
from reports.report import write_report

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "fomc.db"
DEFAULT_REPORTS = ROOT / "reports" / "out"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(fixture_path, date, doc_type="statement",
        db_path=DEFAULT_DB, report_dir=DEFAULT_REPORTS):
    fixture_path = Path(fixture_path)
    text = fixture_path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    doc_id = f"{date}_{doc_type}"

    conn = db.connect(db_path)
    db.init_db(conn)

    conn.execute(
        "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?)",
        (doc_id, date, doc_type, str(fixture_path), sha, _now()),
    )

    for idx, sentence in enumerate(split_sentences(text)):
        r = analyze(sentence)
        sid = f"{doc_id}#{idx}#{MODEL_TAG}"
        conn.execute(
            "INSERT OR REPLACE INTO sentences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, date, doc_id, doc_type, "Statement", idx, sentence,
             r["p_pos"], r["p_neu"], r["p_neg"], r["score"], r["entropy"], MODEL_TAG),
        )

    for row in aggregate_meeting(conn, date, MODEL_TAG):
        conn.execute("INSERT OR REPLACE INTO meetings VALUES (?,?,?,?,?)", row)

    conn.commit()
    report_path = write_report(conn, date, report_dir)
    conn.close()
    return report_path


if __name__ == "__main__":
    fixture = ROOT / "tests" / "fixtures" / "FOMC_2025-01-29_statement.txt"
    path = run(fixture, "2025-01-29")
    print("[OK] 보고서 생성:", path)
