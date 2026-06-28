"""Thin-slice 검증 테스트. 네트워크 의존 없음(고정 픽스처 사용)."""
import math
from pathlib import Path

import db
import pipeline
from engine.dummy_sentiment import analyze

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "FOMC_2025-01-29_statement.txt"
DATE = "2025-01-29"


def test_schema_has_all_tables_and_columns(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"documents", "sentences", "meetings", "market"} <= tables

    cols = {r[1] for r in conn.execute("PRAGMA table_info(sentences)")}
    assert {"p_pos", "p_neu", "p_neg", "entropy", "model_tag"} <= cols


def test_dummy_engine_contract():
    """확률 합=1, 엔트로피>=0 — Phase 3 진짜 엔진도 같은 계약을 지켜야 함."""
    r = analyze("The Committee decided to maintain the target range.")
    assert set(r) == {"p_pos", "p_neu", "p_neg", "score", "entropy"}
    assert math.isclose(r["p_pos"] + r["p_neu"] + r["p_neg"], 1.0, abs_tol=1e-9)
    assert r["entropy"] >= 0.0
    # 결정적: 같은 입력 → 같은 출력
    assert analyze("x") == analyze("x")


def test_pipeline_runs_and_is_idempotent(tmp_path):
    dbp = tmp_path / "t.db"
    rep = tmp_path / "reports"

    out1 = pipeline.run(FIXTURE, DATE, db_path=dbp, report_dir=rep)
    assert Path(out1).exists()

    conn = db.connect(dbp)
    n_sent_1 = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    n_meet_1 = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    conn.close()
    assert n_sent_1 > 0
    assert n_meet_1 == 2  # label_avg + conf_weighted

    # 두 번째 실행 → 행 수 동일(멱등)
    pipeline.run(FIXTURE, DATE, db_path=dbp, report_dir=rep)
    conn = db.connect(dbp)
    n_sent_2 = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    n_meet_2 = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    conn.close()
    assert n_sent_2 == n_sent_1
    assert n_meet_2 == n_meet_1
