"""Fed 축 3성분(statement·presser·minutes) 결합 + 속보치/확정판 불변성 테스트.

질문 6 피드백 반영분: ① statement:presser:minutes=1:1:1 z-결합(headline.combine_fed_axes),
② "과거 실시간 값을 덮어쓰면 안 된다" 원칙(analyze_alignment.upsert_fed_composite/
fed_composite_asof) — DB 계층에서 확정판 도착 후에도 속보치 행이 그대로인지 확인한다.
"""
import db
from analysis.headline import combine_fed_axes
from analysis.analyze_alignment import upsert_fed_composite, fed_composite_asof


def _conn():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def _seed_meeting(conn, date, tone=0.10):
    """fed_composite_asof/upsert_fed_composite 는 그 날짜에 'conf_weighted' 회의가
    존재한다고 전제(가장 최근 회의를 찾는 앵커)."""
    conn.execute("INSERT OR REPLACE INTO meetings VALUES (?,?,?,?,?)",
                 (date, "conf_weighted", "meeting", tone, 0.8))
    conn.commit()


# --- combine_fed_axes: 순수 함수 --------------------------------------------
def test_all_none_returns_none():
    assert combine_fed_axes(None, None, None) is None


def test_statement_only_uses_single_axis():
    fc = combine_fed_axes(0.20, None, None)
    assert fc["axes"] == ["statement"] and fc["n_axes"] == 1


def test_statement_and_presser_graceful_degrade():
    fc = combine_fed_axes(0.20, 0.05, None)
    assert fc["axes"] == ["statement", "presser"] and fc["n_axes"] == 2


def test_all_three_axes_equal_weight():
    fc = combine_fed_axes(0.20, 0.05, 0.10)
    assert fc["axes"] == ["statement", "presser", "minutes"] and fc["n_axes"] == 3
    # 세 성분 z 평균 — 같은 입력을 fed_composite_asof 없이도 재현 가능한 순수 계산인지만 확인.
    assert isinstance(fc["fed_composite"], float)


# --- DB 계층: 속보치는 확정 전까지 갱신 가능, 확정판 도착 후엔 영구 불변 -------------
def test_realtime_updatable_before_final():
    conn = _conn()
    _seed_meeting(conn, "2026-08-05")
    upsert_fed_composite(conn, "2026-08-05", -0.10, 1, 3, final=False)   # statement만
    assert fed_composite_asof(conn, "2026-08-05") == -0.10
    upsert_fed_composite(conn, "2026-08-05", -0.05, 2, 3, final=False)   # presser 도착 → 갱신
    assert fed_composite_asof(conn, "2026-08-05") == -0.05


def test_final_locks_and_realtime_frozen_afterward():
    conn = _conn()
    _seed_meeting(conn, "2026-08-05")
    upsert_fed_composite(conn, "2026-08-05", -0.05, 2, 3, final=False)   # 속보치(2축)
    upsert_fed_composite(conn, "2026-08-05", -0.30, 3, 3, final=True)    # minutes 도착 → 확정
    assert fed_composite_asof(conn, "2026-08-05") == -0.30               # 확정판 우선

    # 확정 이후 속보치 upsert 시도(예: 재실행) — 무시되어야 함(과거 실시간 값 불변).
    upsert_fed_composite(conn, "2026-08-05", 0.99, 2, 3, final=False)
    rows = list(conn.execute(
        "SELECT method, index_value FROM meetings WHERE date='2026-08-05' "
        "AND method LIKE 'fed_composite%'"))
    values = dict(rows)
    assert values["fed_composite_realtime"] == -0.05      # 손대지 않음
    assert values["fed_composite_final"] == -0.30

    # 확정판 재기록 시도도 무시(INSERT OR IGNORE) — 최초 확정값만 유지.
    upsert_fed_composite(conn, "2026-08-05", 0.0, 3, 3, final=True)
    assert fed_composite_asof(conn, "2026-08-05") == -0.30


def test_asof_carries_forward_latest_meeting_before_date():
    conn = _conn()
    _seed_meeting(conn, "2026-07-01")
    upsert_fed_composite(conn, "2026-07-01", 0.20, 1, 3, final=False)
    _seed_meeting(conn, "2026-08-05")
    upsert_fed_composite(conn, "2026-08-05", -0.10, 1, 3, final=False)
    assert fed_composite_asof(conn, "2026-07-15") == 0.20    # 7/1 회의 이월
    assert fed_composite_asof(conn, "2026-08-06") == -0.10   # 8/5 회의 이월


def test_asof_falls_back_to_legacy_statement_only():
    """이 기능 도입 전 데이터(conf_weighted 만 있고 fed_composite_* 없음)도 폴백으로 동작 —
    반환값은 combine_fed_axes 의 1축(statement 단독) 결합과 같은 z-척도여야 한다(원값
    그대로 반환하면 headline.combine() 이 다시 표준화할 때 척도가 깨진다)."""
    conn = _conn()
    _seed_meeting(conn, "2026-01-01", tone=0.42)
    expected = combine_fed_axes(0.42, None, None)["fed_composite"]
    assert fed_composite_asof(conn, "2026-01-02") == expected
