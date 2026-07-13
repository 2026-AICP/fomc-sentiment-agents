"""감성 보고서 생성. 수치는 DB에서 직접 인용 (환각 차단 원칙).

포함 내용:
  1. 회의 인덱스 (label_avg / conf_weighted)
  2. 회의 전체 감성 분해 (평균 긍정/중립/부정 %)
  3. 문장별 감성 분해 (긍정/중립/부정 % + 불확실성)
  4. 시장·신호 알림 카드 (Phase 6 — market 데이터 있을 때만)
"""
from pathlib import Path


def _signal_section(conn, date: str):
    """Phase 6 알림 카드. market 데이터가 있으면 신호 등급을, 없으면 안내만.

    signals.build_alerts 를 전체 시계열에 돌려 직전 톤(tone_shift용)까지
    올바로 반영한 뒤, 이 회의(date)의 Alert 를 골라 카드로 렌더한다.
    """
    try:
        from analysis.signals import load_series, build_alerts
    except Exception:
        return []

    series = load_series(conn)
    if not series:
        return []
    alerts = build_alerts(series, small_sample=len(series) < 30)
    alert = next((a for a in alerts if a.date == date), None)
    if alert is None:
        return []

    lines = ["", "## 4. 시장·신호 알림 (Phase 6)"]
    if alert.reaction_ret is None:
        lines.append("- _시장 데이터 없음 — `analysis/collect_market.py` 실행 후 재생성_")
        return lines

    lines.append(f"- **종합 등급: {alert.grade}**  (신뢰도 {alert.confidence:.3f})")
    lines.append(f"- 톤 {alert.tone:+.3f}  |  시장 반응 {alert.reaction_ret:+.2f}%")
    fired = [s for s in alert.signals if s.fired]
    if fired:
        lines.append("- 발동 신호:")
        for s in fired:
            lines.append(f"    - {s.detail}")
    else:
        lines.append("- 발동 신호: 없음")
    lines.append(f"- _{alert.note}_")
    return lines


def _news_section(news, headline, pre_post=None, presser=None):
    """Phase 7 — News 축·통합·발표전후(2d)·성명문vs기자회견(#4) 카드. 값을 넘길 때만 렌더."""
    if not news and not headline and not pre_post and not presser:
        return []
    lines = ["", "## 5. News 축 & 통합 (Phase 7)"]
    if news:
        lo, hi = news.get("ci_lo"), news.get("ci_hi")
        ci = (f"(95% CI {lo:+.3f} ~ {hi:+.3f})" if lo == lo and hi == hi
              else "(CI 계산불가: 표본<2)")     # lo==lo → NaN 판별
        lines.append(f"- News 지수: {news['conf_weighted']:+.3f} {ci}  |  기사 {news['n_articles']}건")
    elif headline:
        lines.append("- News 지수: 해당 기간 실시간 뉴스 없음 (과거 회의 — Fed 단독)")
    if headline:
        lines.append(
            f"- **통합(headline): {headline['headline']:+.3f}**  "
            f"({headline['method']} — Fed {headline['w_fed']*100:.0f}% · News {headline['w_news']*100:.0f}%)")
    if pre_post:                                       # 2d Step 2: 발표 전/후 뉴스 감성 변화
        pre, post, shift = pre_post.get("pre"), pre_post.get("post"), pre_post.get("shift")
        if shift is not None:
            lines.append(
                f"- **발표 전/후 뉴스 감성 (2d): {pre['conf_weighted']:+.3f} (전, {pre['n_articles']}건)"
                f" → {post['conf_weighted']:+.3f} (후, {post['n_articles']}건)  |  변화 {shift:+.3f}**")
        elif pre or post:
            side, w = ("발표 후", post) if post else ("발표 전", pre)
            lines.append(f"- 발표 전/후 뉴스: {side}만 수집됨 ({w['n_articles']}건) — 변화 계산 불가")
    if presser:                                        # #4 Step 3: 성명문 vs 기자회견 톤 괴리
        lines.append(
            f"- **성명문 vs 기자회견 (#4): {presser['statement_tone']:+.3f} (성명문)"
            f" → {presser['tone']:+.3f} (기자회견, {presser['n_sentences']}문장)"
            f"  |  괴리 {presser['gap']:+.3f}**")
    return lines


def write_report(conn, date: str, report_dir, news: dict = None,
                 headline: dict = None, pre_post: dict = None, presser: dict = None) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    meetings = conn.execute(
        "SELECT method, index_value, confidence FROM meetings WHERE date = ? "
        "AND granularity = 'meeting' ORDER BY method",
        (date,),
    ).fetchall()

    sentences = conn.execute(
        "SELECT sentence_idx, sentence, p_pos, p_neu, p_neg, entropy "
        "FROM sentences WHERE date = ? ORDER BY sentence_idx",
        (date,),
    ).fetchall()
    n_sent = len(sentences)

    # 회의 전체 평균 감성 (퍼센티지)
    avg = conn.execute(
        "SELECT AVG(p_pos), AVG(p_neu), AVG(p_neg) FROM sentences WHERE date = ?",
        (date,),
    ).fetchone()
    avg_pos, avg_neu, avg_neg = (v or 0.0 for v in avg)

    lines = [
        f"# FOMC 감성 보고서 — {date}",
        "",
        f"- 분석 문장 수: {n_sent}",
        "",
        "## 1. 회의 인덱스",
    ]
    for method, value, conf in meetings:
        lines.append(f"- {method}: {value:+.4f} (confidence {conf:.3f})")

    lines += [
        "",
        "## 2. 회의 전체 감성 분해 (평균)",
        f"- 긍정 {avg_pos*100:.1f}%  |  중립 {avg_neu*100:.1f}%  |  부정 {avg_neg*100:.1f}%",
        "",
        "## 3. 문장별 감성 분해",
        "",
        "| # | 문장 | 긍정% | 중립% | 부정% | 불확실성 |",
        "|---|------|------:|------:|------:|--------:|",
    ]
    for idx, sent, pp, pn, pg, ent in sentences:
        s = sent.replace("|", "/")
        if len(s) > 90:
            s = s[:87] + "..."
        lines.append(
            f"| {idx} | {s} | {pp*100:.1f} | {pn*100:.1f} | {pg*100:.1f} | {ent:.2f} |"
        )

    lines += _signal_section(conn, date)
    lines += _news_section(news, headline, pre_post, presser)

    out = report_dir / f"report_{date}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main():
    """DB의 모든 회의 리포트를 재생성한다 (시장수집 후 신호 카드 반영용).

    pipeline 은 수집 시점에 리포트를 쓰므로 market 이 아직 비어있다.
    collect_market 실행 후 이걸 돌리면 알림 카드가 채워진다.

    실행: python -m reports.report   (또는 python reports/report.py)
    """
    import sqlite3
    import sys
    from pathlib import Path
    try:  # Windows cp949 콘솔에서도 이모지 출력되게
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 직접 실행 대비

    db_path = "data/fomc.db"
    report_dir = "reports/out"
    con = sqlite3.connect(db_path)
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM meetings ORDER BY date")]
    for d in dates:
        write_report(con, d, report_dir)
    con.close()
    print(f"{len(dates)}개 회의 리포트 재생성 완료 → {report_dir}/")


if __name__ == "__main__":
    main()
