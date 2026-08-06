import os, sqlite3, tempfile
from agents import graph


def test_daily_date_runs_to_end(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.execute("INSERT INTO meetings VALUES ('2026-01-28','conf_weighted','meeting',0.20,0.3)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", path)
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)   # 뉴스 없음
    monkeypatch.setattr(graph.cm, "download_full_range",
                        lambda d: (_ for _ in ()).throw(RuntimeError("offline")))
    app = graph.build_graph()
    result = app.invoke(graph._init_state("2026-02-10"))   # 회의 아님(일별 모드)
    assert "grade" in result["signals"]           # strategy까지 관통
    assert result["report_path"]                  # reporting 도달
