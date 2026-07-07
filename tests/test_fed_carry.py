import os, sqlite3, tempfile
from analysis.analyze_alignment import fed_tone_asof


def _db():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meetings (date TEXT, method TEXT, granularity TEXT, index_value REAL, confidence REAL)")
    con.executemany("INSERT INTO meetings VALUES (?,?,?,?,?)", [
        ("2026-01-28", "conf_weighted", "meeting", 0.20, 0.3),
        ("2026-03-18", "conf_weighted", "meeting", 0.35, 0.3),
    ])
    con.commit()
    return con


def test_carry_forward_uses_last_meeting_on_or_before():
    con = _db()
    assert fed_tone_asof(con, "2026-02-10") == 0.20   # Jan 이후, Mar 이전 → Jan 이월
    assert fed_tone_asof(con, "2026-03-18") == 0.35   # 회의 당일
    assert fed_tone_asof(con, "2026-04-01") == 0.35   # Mar 이후 이월
    assert fed_tone_asof(con, "2020-01-01") is None   # 회의 이전 → 없음
