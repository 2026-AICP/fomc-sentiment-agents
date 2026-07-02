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