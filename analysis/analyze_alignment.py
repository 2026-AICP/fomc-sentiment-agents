"""
Phase 5 — 톤-반응 정합성 분석 (문서 27·29·31번)

meetings(감성 톤)와 market(시장 반응)을 회의일 기준으로 join하여,
톤과 시장이 같은 방향으로 움직였는지(alignment_flag)와
얼마나 어긋났는지(divergence_score)를 산출한다.

[지표 정의 — 방식 ① 방향 일치]
 - alignment_flag  : 톤 부호와 시장 반응 부호가 같으면 1, 다르면 0
 - divergence_score: 방향이 반대일 때 |톤| × |반응| 의 크기 (같은 방향이면 0)

[한계 — 명시]
 - 감성 톤(pos/neg)을 "비둘기/매파"로 해석함. 이 둘은 상관은 있으나
   동일 축이 아니므로(정책 스탠스 ≠ 금융 감성), 해석 시 주의.
 - 회의가 적을 때 divergence_score는 절대 크기라 회의 간 비교에 부적합.
   회의가 쌓이면 '서프라이즈 기반(방식 ②)'으로 승격 예정. (아래 TODO 참고)

실행:  python3 analysis/analyze_alignment.py
"""

import sqlite3

DB_PATH = "data/fomc.db"

# 어느 집계방식의 톤을 쓸지. FOMC는 보일러플레이트가 많아 conf_weighted 권장.
AGG_METHOD = "conf_weighted"   # 'label_avg' 로 바꾸면 단순평균 톤 사용

# 시장 반응 대표값을 발표일 기준 며칠 뒤 수익률로 볼지 (0=발표당일, 1=다음 거래일)
REACTION_OFFSET = 1


def get_meeting_tone(con, agg=AGG_METHOD):
    """meetings에서 (회의날짜, 톤점수) 목록을 가져온다.

    meetings 컬럼: date, method, granularity, index_value, confidence
    지정한 집계방식(agg)의 행만 골라 score를 톤으로 쓴다.
    """
    rows = con.execute(
        "SELECT date, index_value FROM meetings WHERE method = ? ORDER BY date",
        (agg,),
    ).fetchall()
    return rows   # [(date, tone), ...]


def fed_tone_asof(con, date, method=AGG_METHOD):
    """date 시점 Fed 톤 = 그날 이전(포함) 마지막 회의의 index_value (이월). 없으면 None.

    일별(비-FOMC) 날에도 Fed 축을 유지하기 위한 carry-forward. 통합 에이전트가 사용.
    """
    row = con.execute(
        "SELECT index_value FROM meetings WHERE method=? AND granularity='meeting' "
        "AND date<=? ORDER BY date DESC LIMIT 1", (method, date)).fetchone()
    return row[0] if row else None


def fed_composite_asof(con, date):
    """date 시점 Fed 축 결합값(statement+presser+minutes, 1:1:1, z-척도) — 확정판 있으면
    확정판, 없으면 속보치, 이 기능 이전 데이터(레거시, fed_composite_* 행 없음)면
    statement 단독을 같은 z-척도로 변환해 반환(combine_fed_axes 1축 결합과 동일 계산이라
    반환값은 항상 z-척도로 일관됨 — 호출부가 재표준화 여부를 신경 쓰지 않아도 된다).

    질문 6 피드백(운영 반영 시 minutes 3주 지연 처리): '그날 이전 최신 회의'를 먼저 찾고,
    그 회의에 한해 확정판 > 속보치 > 레거시 순으로 값을 고른다. 확정판이 나중에 추가돼도
    이미 이월된 과거 일자의 daily_signals.csv 행은 건드리지 않는다(agents/graph.py 참고) —
    이 함수는 그 시점에 '무엇을 보여줄지'만 결정하고, 과거 기록을 소급 수정하지 않는다.
    """
    row = con.execute(
        "SELECT date FROM meetings WHERE method=? AND granularity='meeting' "
        "AND date<=? ORDER BY date DESC LIMIT 1", (AGG_METHOD, date)).fetchone()
    if not row:
        return None
    mdate = row[0]
    for method in ("fed_composite_final", "fed_composite_realtime"):
        v = con.execute(
            "SELECT index_value FROM meetings WHERE date=? AND method=? AND granularity='meeting'",
            (mdate, method)).fetchone()
        if v is not None:
            return v[0]
    stmt = con.execute(
        "SELECT index_value FROM meetings WHERE date=? AND method=? AND granularity='meeting'",
        (mdate, AGG_METHOD)).fetchone()
    if stmt is None:
        return None
    from analysis.headline import combine_fed_axes    # 지연 import(순환 회피)
    fc = combine_fed_axes(stmt[0], None, None)
    return fc["fed_composite"] if fc else None


def upsert_fed_composite(con, date, value, n_axes, expected, final):
    """Fed 축 결합값을 meetings에 기록 — 확정판(final)은 최초 1회만, 이후 절대 재작성 않음.

    원칙(질문 6 피드백): "과거 실시간 값을 덮어쓰면 안 된다." 속보치(fed_composite_realtime)는
    확정 전까지는(presser 도착 등) 갱신 가능하지만, 확정판이 이미 기록됐다면 더 손대지 않는다.
    확정판(fed_composite_final)은 minutes 도착으로 3축이 다 찼을 때 단 한 번만 기록된다.
    """
    completeness = round(n_axes / expected, 4) if expected else None
    if final:
        con.execute("INSERT OR IGNORE INTO meetings VALUES (?,?,?,?,?)",
                    (date, "fed_composite_final", "meeting", round(value, 4), completeness))
    else:
        already_final = con.execute(
            "SELECT 1 FROM meetings WHERE date=? AND method='fed_composite_final' "
            "AND granularity='meeting'", (date,)).fetchone()
        if already_final:
            return
        con.execute("INSERT OR REPLACE INTO meetings VALUES (?,?,?,?,?)",
                    (date, "fed_composite_realtime", "meeting", round(value, 4), completeness))
    con.commit()


def get_reaction(con, meeting_date, offset=REACTION_OFFSET):
    """회의일 기준 offset 거래일 뒤의 시장 반응(수익률·VIX변화)을 가져온다.

    market은 거래일만 들어있으므로, 회의일 이상인 날짜를 순서대로 정렬해
    offset 번째 행을 반응일로 본다. (주말/휴장 자동 스킵)
    반환: (반응일, spx_ret_cc, vix_chg) 또는 데이터 부족 시 None
    """
    rows = con.execute(
        "SELECT date, spx_ret_cc, vix_chg FROM market "
        "WHERE date >= ? ORDER BY date LIMIT ?",
        (meeting_date, offset + 1),
    ).fetchall()
    if len(rows) < offset + 1:
        return None            # 반응일 데이터가 아직 없음
    return rows[offset]        # offset 번째(0=당일, 1=다음날)


def get_ust2y_change(con, meeting_date, offset=REACTION_OFFSET):
    """반응일의 2년물 국채금리 변화(전 거래일 대비, %p). 데이터 없으면 None.

    2년물은 Fed 정책에 가장 민감한 만기 → '시장이 소화한 금리 서프라이즈'의 대리(proxy).
    (진짜 Fed Funds 선물 기반 서프라이즈는 무료 데이터 부재로 미구현 — signal_design 참고.)
    """
    rows = con.execute(
        "SELECT date FROM market WHERE date >= ? ORDER BY date LIMIT ?",
        (meeting_date, offset + 1),
    ).fetchall()
    if len(rows) < offset + 1:
        return None
    rdate = rows[offset][0]
    r = con.execute(
        "SELECT ust2y FROM market WHERE date <= ? AND ust2y IS NOT NULL ORDER BY date DESC LIMIT 2",
        (rdate,),
    ).fetchall()
    if len(r) < 2:
        return None
    return r[0][0] - r[1][0]


def sign(x):
    """부호만 뽑는다: 양수 +1, 음수 -1, 0은 0."""
    if x is None:
        return 0
    return (x > 0) - (x < 0)


def compute_alignment(tone, reaction_ret):
    """방향 일치 지표를 계산한다.

    alignment_flag  : 톤 부호 == 반응 부호 -> 1, 아니면 0
    divergence_score: 부호가 반대면 |톤| × |반응|, 같으면 0
    """
    ts, rs = sign(tone), sign(reaction_ret)

    if ts == 0 or rs == 0:
        # 톤이나 반응이 0이면 방향 판정 불가 -> 중립 처리
        return None, 0.0

    aligned = 1 if ts == rs else 0
    divergence = 0.0 if aligned else abs(tone) * abs(reaction_ret)
    return aligned, divergence


def main():
    con = sqlite3.connect(DB_PATH)

    meetings = get_meeting_tone(con)
    if not meetings:
        print(f"'{AGG_METHOD}' 방식의 회의 톤이 없습니다. meetings/method를 확인하세요.")
        con.close()
        return

    print(f"분석 대상: {len(meetings)}개 회의 (톤 집계방식={AGG_METHOD}, 반응=발표+{REACTION_OFFSET}거래일)\n")
    print(f"{'회의일':<12}{'톤':>10}{'반응일':>13}{'수익률%':>10}{'정합':>6}{'괴리':>10}")

    results = []
    for mdate, tone in meetings:
        reac = get_reaction(con, mdate)
        if reac is None:
            print(f"{mdate:<12}{tone:>10.4f}{'(반응데이터 없음)':>16}")
            continue
        rdate, ret, vixc = reac
        flag, div = compute_alignment(tone, ret)

        flag_str = "-" if flag is None else ("일치" if flag == 1 else "괴리")
        ret_str = "NULL" if ret is None else f"{ret:.3f}"
        print(f"{mdate:<12}{tone:>10.4f}{rdate:>13}{ret_str:>10}{flag_str:>6}{div:>10.4f}")
        results.append((mdate, tone, rdate, ret, flag, div))

    # 요약: 회의가 여러 개면 정합 비율을 낸다 (지금은 1건이라 참고용)
    judged = [r for r in results if r[4] is not None]
    if judged:
        align_rate = sum(r[4] for r in judged) / len(judged)
        print(f"\n정합률(방향 일치 비율): {align_rate:.0%}  (판정 가능 {len(judged)}건 기준)")
        if len(judged) < 5:
            print("※ 회의 수가 적어 통계적 의미는 제한적입니다. 골조 검증 단계.")

    con.close()

    # TODO(방식 ②): 회의가 충분히 쌓이면 divergence_score를
    #   '직전 회의 대비 톤 변화(서프라이즈) vs 실제 반응의 잔차'로 승격.
    #   compute_alignment()만 교체하면 나머지 파이프라인은 그대로 재사용 가능.


if __name__ == "__main__":
    main()