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
    # Jan 회의 이월 — fed_composite_asof 는 항상 z-척도로 반환(질문6: statement 단독 1축도
    # combine_fed_axes 와 동일 계산으로 표준화돼야 headline 결합 시 재표준화로 폭주하지 않는다).
    from analysis.headline import combine_fed_axes
    expected = round(combine_fed_axes(0.20, None, None)["fed_composite"], 4)
    assert out["index"].get("fed_composite") == expected
