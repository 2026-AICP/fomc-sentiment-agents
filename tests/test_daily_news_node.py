import os, sqlite3, tempfile
from agents import graph


def _seed_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.execute("INSERT INTO meetings VALUES ('2026-01-28','conf_weighted','meeting',0.20,0.3)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", path)


def test_news_node_fills_fed_from_carry_when_index_empty(monkeypatch):
    _seed_db(monkeypatch)
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)  # 실시간 뉴스 없음
    state = graph._init_state("2026-02-10")   # 회의 아님 → index 비어있음
    out = graph.news_node(state)
    assert out["index"].get("conf_weighted") == 0.20   # Jan 이월
