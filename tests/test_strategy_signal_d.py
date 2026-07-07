from agents import graph


def test_strategy_includes_tone_vs_rate(monkeypatch, tmp_path):
    # 톤 긍정(+0.30)인데 2년물 급등(+0.10%p) = 금리 동행 이탈 → 신호 D 발동
    import sqlite3
    dbp = tmp_path / "m.db"
    con = sqlite3.connect(dbp)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", str(dbp))     # 빈 meetings → prev_tone None (에러 없이)
    state = graph._init_state("2026-02-10")
    state["index"] = {"conf_weighted": 0.30}
    state["market"] = {"spx_ret_cc": 0.1, "vix_chg": 0.0, "ust2y_chg": 0.10}
    out = graph.strategy_node(state)
    assert "tone_vs_rate" in out["signals"]["fired"]
