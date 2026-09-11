import os, sqlite3, tempfile
from agents import graph
from analysis import vintage


def test_daily_date_runs_to_end(monkeypatch, tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.execute("INSERT INTO meetings VALUES ('2026-01-28','conf_weighted','meeting',0.20,0.3)")
    con.commit(); con.close()
    monkeypatch.setattr(graph, "DB", path)
    # 시점 기록도 임시 경로로 돌린다. 안 하면 reporting 단계가 진짜
    # outputs/vintage_meetings.csv 에 행을 쓴다 — 그 파일은 "그때 알고 있던 값"의
    # 불변 기록이라(질문 6) 테스트가 가짜 행을 남기면 안 된다. DB 와 달리
    # graph 가 아니라 vintage 모듈의 상수라 거기서 갈아끼운다.
    monkeypatch.setattr(vintage, "MEETING_VINTAGE", tmp_path / "vintage_meetings.csv")
    monkeypatch.setattr(graph, "index_for_window", lambda **kw: None)   # 뉴스 없음
    monkeypatch.setattr(graph.cm, "download_full_range",
                        lambda d: (_ for _ in ()).throw(RuntimeError("offline")))
    app = graph.build_graph()
    result = app.invoke(graph._init_state("2026-02-10"))   # 회의 아님(일별 모드)
    assert "grade" in result["signals"]           # strategy까지 관통
    assert result["report_path"]                  # reporting 도달
