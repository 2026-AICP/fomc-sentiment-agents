"""백테스트 DB 배선(글루) 통합테스트 — 합성 SQLite, 네트워크·모델 없음.

순수 함수는 test_backtest.py 가, 여기서는 load_series/load_outcomes/run_backtest 가
실제 스키마 위에서 SQL·조립을 올바로 하는지(크래시 없이 리포트 생성) 확인한다.
"""
import db
from analysis.signals import load_series
from analysis.backtest import load_outcomes, run_backtest


def _seed(conn):
    """6개 회의 + 각 회의일 이후 3거래일 시장데이터를 넣는다."""
    meetings = [
        ("2000-01-05", -0.10, 0.40),
        ("2000-02-02", 0.15, 0.38),   # 직전 대비 +0.25 급변
        ("2000-03-01", -0.18, 0.41),
        ("2000-04-05", 0.05, 0.30),
        ("2000-05-03", 0.12, 0.33),
        ("2000-06-07", -0.08, 0.35),
    ]
    for date, tone, conf in meetings:
        conn.execute("INSERT OR REPLACE INTO meetings VALUES (?,?,?,?,?)",
                     (date, "conf_weighted", "meeting", tone, conf))

    # 각 회의일 + 다음 2거래일 종가 (하나는 큰 낙폭이 나도록)
    market = [
        # date, close, ret%, vix, vix_chg
        ("2000-01-05", 1400, 0.1, 20, 0.1), ("2000-01-06", 1410, 0.7, 19, -1.0), ("2000-01-07", 1408, -0.1, 19, 0.0),
        ("2000-02-02", 1420, 0.2, 21, 0.5), ("2000-02-03", 1360, -4.2, 28, 7.0), ("2000-02-04", 1350, -0.7, 29, 1.0),  # 큰 낙폭
        ("2000-03-01", 1380, 0.3, 22, 0.2), ("2000-03-02", 1385, 0.4, 21, -1.0), ("2000-03-03", 1390, 0.4, 20, -1.0),
        ("2000-04-05", 1500, 0.1, 18, 0.0), ("2000-04-06", 1495, -0.3, 19, 1.0), ("2000-04-07", 1498, 0.2, 18, -1.0),
        ("2000-05-03", 1450, 0.2, 23, 0.5), ("2000-05-04", 1400, -3.4, 30, 7.0), ("2000-05-05", 1395, -0.4, 31, 1.0),  # 큰 낙폭
        ("2000-06-07", 1470, 0.1, 20, 0.0), ("2000-06-08", 1472, 0.1, 20, 0.0), ("2000-06-09", 1475, 0.2, 19, -1.0),
    ]
    for row in market:
        conn.execute("INSERT OR REPLACE INTO market VALUES (?,?,?,?,?,?,?)",
                     (row[0], row[1], row[2], row[3], row[4], None, None))
    conn.commit()


def test_load_series_joins_tone_and_reaction(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    _seed(conn)
    series = load_series(conn, "conf_weighted", reaction_offset=1)
    assert len(series) == 6
    first = series[0]
    assert set(first) == {"date", "tone", "confidence", "reaction_ret", "vix_chg", "ust2y_chg"}
    # 반응=발표+1거래일 → 2000-01-05 의 반응은 2000-01-06 의 ret(0.7)
    assert abs(first["reaction_ret"] - 0.7) < 1e-9


def test_load_outcomes_computes_drawdown(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    _seed(conn)
    dates = [r["date"] for r in load_series(conn)]
    dds, rets = load_outcomes(conn, dates, n_days=2)
    assert len(dds) == 6
    # 2000-02-02 창(1420→1360→1350)은 큰 낙폭
    assert dds[1] > 3.0


def test_run_backtest_writes_report(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    _seed(conn)
    out = run_backtest(conn, report_dir=tmp_path / "out")
    assert out is not None and out.exists()
    text = out.read_text(encoding="utf-8")
    assert "신호 적중률 vs 단순보유" in text
    assert "국면별" in text
