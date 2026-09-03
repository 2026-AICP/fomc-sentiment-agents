"""대시보드 데이터 다리 — 파이썬 파이프라인 산출물을 웹 프론트용 JSON으로 내보내기.

React/Lovable 등 웹 프론트는 파이썬을 못 돌리므로, DB·CSV의 분석 결과를
정적 JSON으로 변환한다. 프론트는 이 파일들만 fetch해서 렌더(계산 없음 — 환각 차단).

산출 (기본 outputs/dashboard/):
  meta.json           생성시각·기간·건수 + 검증 수치(-0.534, 홀드아웃, CI, LOMO, 괴리 2.4x, presser 87%)
  meetings.json       회의별 Fed 톤 (conf_weighted, confidence)
  alerts.json         회의별 신호 (등급·발동·톤·시장반응) — 검증된 signals 엔진 재사용
  news_daily.json     일별 News 지수 (+ 부트스트랩 CI, 기사수)
  daily_headline.json 일별 통합 감성지수 = News : Fed(성명문·회의록·기자회견 1:1:1) = 1:1
  daily_signals.json  일별 통합 신호 누적 (에이전트 산출)
  market.json         시장 (S&P·VIX·2Y·10Y) — 차트용
  presser.json        회의별 성명문 vs 기자회견 톤·괴리

실행: python3 analysis/export_dashboard.py [outdir]
"""
import csv
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "fomc.db"
OUTDIR = ROOT / "outputs" / "dashboard"


def _f(v, nd=4):
    """float 정리 — NaN/None → None(JSON null), 아니면 반올림."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, nd)


def _csv_rows(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def export_meetings(con):
    rows = con.execute(
        "SELECT date, index_value, confidence FROM meetings "
        "WHERE method='conf_weighted' AND granularity='meeting' ORDER BY date").fetchall()
    return [{"date": d, "tone": _f(v), "confidence": _f(c, 3)} for d, v, c in rows]


def export_alerts(con):
    from analysis.signals import load_series, build_alerts
    series = load_series(con)
    alerts = build_alerts(series, small_sample=len(series) < 30)
    return [{"date": a.date, "grade": a.grade, "tone": _f(a.tone),
             "reaction": _f(a.reaction_ret, 2), "fired": a.fired_names(),
             "detail": " · ".join(s.detail for s in a.signals if s.fired)}
            for a in alerts]


# 백필(주별) → 라이브(일별) 경계. 이 날부터 라이브 일별을 쓴다.
#   라이브 CSV 에도 07-03~07-09 가 있지만 수집 초기의 부실한 표본이다(하루 2~11건).
#   같은 구간을 Standard 티어로 다시 전수 회수해 141건을 확보했으므로 백필 쪽을 쓴다.
#   두 원본에 URL 이 겹치는 기사가 12건 있는데, 이 경계로 자르면 자연히 한 번만 센다.
NEWS_LIVE_FROM = "2026-07-10"


def _news_row(r, period):
    return {"date": r["date"], "n_articles": int(r["n_articles"]),
            "index": _f(r["conf_weighted"]), "ci_lo": _f(r["ci_lo"]),
            "ci_hi": _f(r["ci_hi"]), "confidence": _f(r["confidence"], 3),
            "period": period}


def export_news_daily():
    """뉴스 지수 — 백필(주별, 2021-01~2026-07-09) + 라이브(일별, 2026-07-10~).

    ★두 구간의 집계 단위가 다른 이유: 백필 일별은 중앙값이 7건뿐이라 신뢰도 하한
      (15건, news_signals.Thresholds)을 73% 의 날이 못 넘는다. 그대로 내보내면
      5.5년의 4분의 3이 '신뢰도 낮음'으로 표시된다. 주별로 묶으면 중앙값 62건이
      되어 하한 미달이 11% 로 떨어진다. 라이브는 매일 갱신이 목적이라 일별 유지.
      프론트가 구분해 표시하도록 period 필드를 실어 보낸다.

    ★선정 규칙은 두 구간이 같다(Marketaux 본문 F → 제목+설명 F∧M). 그래서 이어
      붙일 수 있다. WSJ 백본(2000~2021)은 규칙이 다르므로 여기 섞지 않는다 —
      경위와 영향 측정은 docs/scope_impact.md 참조.
    """
    bf_csv = ROOT / "outputs" / "news_index_backfill_weekly.csv"
    if not bf_csv.exists():
        # _csv_rows 는 없는 파일에 []를 돌려주므로 그냥 두면 5.5년치가 조용히 사라지고
        # 사이트가 최근 두 달만 보여준다. 러너 로그에 남겨 알아챌 수 있게 한다.
        print(f"  warn: 백필 지수가 없습니다({bf_csv.name}) — 뉴스축이 라이브 구간만 나갑니다.")
    bf = [_news_row(r, "weekly") for r in _csv_rows(bf_csv)]
    live = [_news_row(r, "daily")
            for r in _csv_rows(ROOT / "outputs" / "news_index_live.csv")
            if r["date"] >= NEWS_LIVE_FROM]
    return bf + live


def export_daily_headline():
    """일별 통합 감성지수 — News : Fed = 1:1, Fed 내부는 성명문:회의록:기자회견 = 1:1:1.

    홈 화면의 '통합 감성지수'가 읽는 시계열. 이 파일이 없던 동안 홈은 news_daily(뉴스 단독)를
    읽으면서 이름만 '통합'이라 붙이고 있었다(2026-08 발견).

    ★척도 주의: headline 은 각 축을 z-표준화해 합친 **상대값**이라 0이 과거 평균이고,
    뉴스 원값처럼 -1~+1 범위가 아니다. 게다가 현재 z 파라미터(headline_norm.json)가
    월별 집계에서 나온 값이라 일별에 쓰면 크기가 약 4배 부풀려진다 — 부호와 상대 순서는
    맞지만 절대 크기는 아직 신뢰할 수 없다. 정상 수집이 쌓인 뒤 일별 분포로 재추정할 것.
    """
    return [{"date": r["date"], "index": _f(r["headline"]),
             "fed": _f(r["fed_carry"]), "news": _f(r["news"]),
             "method": r.get("method") or None,
             "n_articles": int(r["n_articles"]) if r.get("n_articles") else None}
            for r in _csv_rows(ROOT / "outputs" / "daily_headline.csv")]


def export_daily_signals():
    """일별 통합 신호 — grade/index 는 속보치(최초 기록 후 불변, 질문6 피드백).

    gate_reason 이 있으면 표본 부족·CI 넓음으로 경보가 관망으로 내려간 것(질문5 피드백,
    지수 자체는 그대로 표시). grade_final/index_final 은 minutes 도착 후 3축이 다 찼을 때
    딱 한 번 채워지는 확정판 — 비어 있으면 아직 미확정.
    """
    return [{"date": r["date"], "grade": r["grade"], "index": _f(r["index"]),
             "fired": [x for x in (r.get("fired") or "").split(";") if x],
             "gate_reason": r.get("gate_reason") or None,
             "n_articles": int(r["n_articles"]) if r.get("n_articles") else None,
             "ci_lo": _f(r.get("ci_lo")), "ci_hi": _f(r.get("ci_hi")),
             "fed_axes": [x for x in (r.get("fed_axes") or "").split(";") if x],
             "grade_final": r.get("grade_final") or None,
             "index_final": _f(r.get("index_final")),
             "fed_axes_final": [x for x in (r.get("fed_axes_final") or "").split(";") if x],
             "finalized_at": r.get("finalized_at") or None}
            for r in _csv_rows(ROOT / "outputs" / "daily_signals.csv")]


def export_market(con, step=5):
    """시장 시계열 — 차트용 주단위 다운샘플(매 5거래일) + 마지막 행은 항상 포함(최신 KPI).

    일별 2,383포인트를 그대로 주면 차트 폭(수백 px)에 픽셀당 6포인트가 눌려
    안티앨리어싱으로 선이 뭉개짐 → ~480포인트로 썸(표시 충실도 유지)."""
    rows = con.execute(
        "SELECT date, spx_close, spx_ret_cc, vix, vix_chg, ust2y, ust10y "
        "FROM market WHERE spx_close IS NOT NULL ORDER BY date").fetchall()
    keep = rows[::step]
    if rows and keep[-1] is not rows[-1]:
        keep.append(rows[-1])                      # 최신 행 보존 (KPI 정확성)
    return [{"date": d, "spx": _f(s, 2), "spx_ret": _f(sr, 3), "vix": _f(v, 2),
             "vix_chg": _f(vc, 2), "ust2y": _f(u2, 2), "ust10y": _f(u10, 2),
             "spread": _f(u10 - u2, 2) if u2 is not None and u10 is not None else None}
            for d, s, sr, v, vc, u2, u10 in keep]


def export_presser():
    return [{"date": r["date"], "statement": _f(r["statement"]),
             "presser": _f(r["presser"]), "gap": _f(r["gap"])}
            for r in _csv_rows(ROOT / "outputs" / "presser_tones.csv")]


# 회의록 표준 6섹션 (analysis/minutes_index.SECTIONS 와 동일)
_MIN_SECTIONS = ("DFMOMO", "SRES", "SRFS", "SEO", "PVCCEO", "CPA")


def export_minutes():
    """회의별 회의록 톤 + 성명문 대비 괴리 + 섹션별 톤 (minutes_backfill 산출)."""
    out = []
    for r in _csv_rows(ROOT / "outputs" / "minutes_tones.csv"):
        row = {"date": r["date"], "statement": _f(r.get("statement")),
               "minutes": _f(r.get("minutes")), "gap": _f(r.get("gap")),
               "n_sentences": int(r["n_sentences"]) if r.get("n_sentences") else None}
        row["sections"] = {c: _f(r.get(c)) for c in _MIN_SECTIONS if _f(r.get(c)) is not None}
        out.append(row)
    return out


def export_news_headlines(limit=20):
    """최근 기사 제목·출처·시각·링크 — 홈 화면 뉴스 목록용.

    지수(news_daily)는 집계값이라 제목이 없다. 사이트에 '무슨 기사가 들어왔는지'를
    보여주려면 원본 CSV의 헤드라인이 필요하다(점수화 대상과 동일한 F∧M 통과분).
    """
    rows = [r for r in _csv_rows(ROOT / "data" / "news" / "fed_news.csv")
            if r.get("published_at") and r.get("title")]
    rows.sort(key=lambda r: r["published_at"], reverse=True)
    return [{"title": r["title"], "source": r.get("source", ""),
             "published_at": r["published_at"], "url": r.get("url", "")}
            for r in rows[:limit]]


def export_axis_status():
    """회의별 3축(성명문·회의록·기자회견) 보유 현황 — 무엇이 아직 안 왔는지."""
    return [{"date": r["date"], "statement": r["statement"] == "1",
             "minutes": r["minutes"] == "1",
             "presser": (r["presser"] == "1") if r.get("presser") else None,
             "n_axes": int(r["n_axes"]), "expected": int(r["expected"]),
             "complete": r["complete"] == "1"}
            for r in _csv_rows(ROOT / "outputs" / "axis_status.csv")]


def _pearson(pairs):
    """[(x,y)...] → 상관계수 (표본<3 이면 None). 프론트는 계산하지 않으므로 여기서 확정."""
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs); syy = sum((b - my) ** 2 for b in ys)
    if sxx == 0 or syy == 0:
        return None
    return round(sxy / (sxx * syy) ** 0.5, 2)


def export_axis_corr():
    """세 문서 톤의 상호 상관 — FOMC 탭 '전체' 해석용 (회의일 기준 병합)."""
    mt = {r["date"]: (_f(r.get("statement")), _f(r.get("minutes")))
          for r in _csv_rows(ROOT / "outputs" / "minutes_tones.csv")}
    pt = {r["date"]: (_f(r.get("statement")), _f(r.get("presser")))
          for r in _csv_rows(ROOT / "outputs" / "presser_tones.csv")}
    sm = [(s, m) for s, m in mt.values() if s is not None and m is not None]
    sp = [(s, p) for s, p in pt.values() if s is not None and p is not None]
    mp = [(mt[d][1], pt[d][1]) for d in mt.keys() & pt.keys()
          if mt[d][1] is not None and pt[d][1] is not None]
    return {"stmt_minutes": _pearson(sm), "stmt_presser": _pearson(sp),
            "minutes_presser": _pearson(mp)}


def export_meta(con, counts):
    """검증·유의성 수치 — 검증 스크립트로 확정된 값(문서 §참조). 프론트는 표시만."""
    # encoding 명시 — 없으면 로케일 기본(한국어 윈도우 cp949)으로 읽어 죽는다.
    # 러너는 리눅스라 UTF-8 기본이어서 드러나지 않지만, 로컬 검증이 막힌다.
    norm = json.loads((ROOT / "analysis" / "headline_norm.json").read_text(encoding="utf-8"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
        "axis_corr": export_axis_corr(),
        "validation": {                       # build_headline_norm / validate_robustness
            **norm.get("validation", {}),
            "bootstrap_ci": [-0.634, -0.426],
            "holdout": [{"split": 2012, "out": -0.479}, {"split": 2014, "out": -0.509},
                        {"split": 2016, "out": -0.528}],
            "lomo_range": [-0.543, -0.526],
        },
        "divergence": {                       # validate_divergence (docs/news_fed_index.md §5)
            "rate_normal": 0.18, "rate_crisis": 0.42, "ratio": 2.4,
            "p_permutation": 0.001, "p_fisher": 0.0008,
            "note": "위기 예측이 아닌 attention signal — 추가 검토 필요 표시",
        },
        # ↓ 세 축 모두 **원본 FinBERT(T=1)** 로 재점수화한 값 (2026-08 기준).
        #   이전 수치는 성명문만 T=3.1 시절 DB 값이라 축 간 스케일이 섞여 있었다.
        "presser_finding": {                  # analysis/presser_backfill
            "n_meetings": 93, "pct_more_cautious": 0.73, "mean_gap": -0.1303,
            "p_sign_test": 9.4e-06,
            "note": "기자회견 톤이 성명문보다 일관되게 신중 (2011~2026, 4의장)",
        },
        "minutes_finding": {                  # analysis/minutes_backfill
            "n_meetings": 214, "pct_more_cautious": 0.68, "mean_gap": -0.0692,
            "p_sign_test": 1.0e-07,
            "axis_means": {"statement": 0.185, "minutes": 0.088, "presser": 0.056},
            "axis_corr": {"stmt_minutes": 0.67, "stmt_presser": 0.34, "minutes_presser": 0.49},
            "note": "공식 문서일수록 낙관적(성명문>회의록>기자회견). 축 상관 0.34~0.67 = "
                    "서로 다른 정보 → 축별 분리 분석의 근거",
        },
    }


def main():
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)

    vs = ROOT / "analysis" / "validation_series.json"    # 감성↔시장 월별(-0.534 원본, 커밋본)
    files = {
        "sentiment_vs_market.json": json.loads(vs.read_text(encoding="utf-8")) if vs.exists() else {},
        "meetings.json": export_meetings(con),
        "alerts.json": export_alerts(con),
        "news_daily.json": export_news_daily(),
        "daily_headline.json": export_daily_headline(),
        "daily_signals.json": export_daily_signals(),
        "market.json": export_market(con),
        "presser.json": export_presser(),
        "minutes.json": export_minutes(),
        "axis_status.json": export_axis_status(),
        "news_headlines.json": export_news_headlines(),
    }
    counts = {k.replace(".json", ""): len(v) for k, v in files.items()}
    files["meta.json"] = export_meta(con, counts)
    con.close()

    for name, data in files.items():
        (outdir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    total_kb = sum((outdir / n).stat().st_size for n in files) / 1024
    print(f"대시보드 JSON {len(files)}개 → {outdir}  (총 {total_kb:.0f}KB)")
    for k, v in counts.items():
        print(f"  {k}: {v}건")


if __name__ == "__main__":
    main()
