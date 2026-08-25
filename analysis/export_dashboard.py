"""대시보드 데이터 다리 — 파이썬 파이프라인 산출물을 웹 프론트용 JSON으로 내보내기.

React/Lovable 등 웹 프론트는 파이썬을 못 돌리므로, DB·CSV의 분석 결과를
정적 JSON으로 변환한다. 프론트는 이 파일들만 fetch해서 렌더(계산 없음 — 환각 차단).

산출 (기본 outputs/dashboard/):
  meta.json           생성시각·기간·건수 + 검증 수치(-0.534, 홀드아웃, CI, LOMO, 괴리 2.4x, presser 87%)
  meetings.json       회의별 Fed 톤 (conf_weighted, confidence)
  alerts.json         회의별 신호 (등급·발동·톤·시장반응) — 검증된 signals 엔진 재사용
  news_daily.json     일별 News 지수 (+ 부트스트랩 CI, 기사수)
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


def export_news_daily():
    return [{"date": r["date"], "n_articles": int(r["n_articles"]),
             "index": _f(r["conf_weighted"]), "ci_lo": _f(r["ci_lo"]),
             "ci_hi": _f(r["ci_hi"]), "confidence": _f(r["confidence"], 3)}
            for r in _csv_rows(ROOT / "outputs" / "news_index_live.csv")]


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


def export_meta(con, counts):
    """검증·유의성 수치 — 검증 스크립트로 확정된 값(문서 §참조). 프론트는 표시만."""
    norm = json.loads((ROOT / "analysis" / "headline_norm.json").read_text())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
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
