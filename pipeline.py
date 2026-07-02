"""Thin-slice 파이프라인: 함수들을 직선으로 연결 (에이전트 전 단계).

흐름: 원문 1건 → 문장 분할 → 더미 감성 → 인덱스 집계 → 보고서 1장
재실행 멱등: 결정적 PK + INSERT OR REPLACE 로 두 번 돌려도 행이 중복되지 않는다.
"""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import db
from engine.preprocess import split_sentences
# 엔진 선택: 기본 dummy(테스트 오프라인·결정적), SENTIMENT_ENGINE=finbert 면 진짜 모델
if os.getenv("SENTIMENT_ENGINE", "dummy").lower() == "finbert":
    from engine.sentiment import analyze, MODEL_TAG
else:
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
    import glob
    import re

    fixture_dir = ROOT / "tests" / "fixtures"
    # fixtures 폴더의 모든 성명문 파일을 날짜순으로 찾는다
    files = sorted(glob.glob(str(fixture_dir / "FOMC_*_statement.txt")))

    if not files:
        print("[경고] fixtures 폴더에 성명문 파일이 없습니다.")
    else:
        print(f"처리 대상: {len(files)}개 회의\n")

    ok, fail = 0, 0
    for fpath in files:
        fname = Path(fpath).name
        # 파일명에서 날짜(YYYY-MM-DD)를 뽑아낸다
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        if not m:
            print(f"  [건너뜀] 날짜를 못 찾음: {fname}")
            continue
        date = m.group(1)
        try:
            path = run(Path(fpath), date)
            print(f"  [OK] {date} → {path}")
            ok += 1
        except Exception as e:
            print(f"  [실패] {date}: {e}")
            fail += 1

    print(f"\n완료: 성공 {ok}건, 실패 {fail}건")