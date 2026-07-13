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
    return [{"date": r["date"], "grade": r["grade"], "index": _f(r["index"]),
             "fired": [x for x in (r.get("fired") or "").split(";") if x]}
            for r in _csv_rows(ROOT / "outputs" / "daily_signals.csv")]


def export_market(con):
    rows = con.execute(
        "SELECT date, spx_close, spx_ret_cc, vix, vix_chg, ust2y, ust10y "
        "FROM market WHERE spx_close IS NOT NULL ORDER BY date").fetchall()
    return [{"date": d, "spx": _f(s, 2), "spx_ret": _f(sr, 3), "vix": _f(v, 2),
             "vix_chg": _f(vc, 2), "ust2y": _f(u2, 2), "ust10y": _f(u10, 2)}
            for d, s, sr, v, vc, u2, u10 in rows]


def export_presser():
    return [{"date": r["date"], "statement": _f(r["statement"]),
             "presser": _f(r["presser"]), "gap": _f(r["gap"])}
            for r in _csv_rows(ROOT / "outputs" / "presser_tones.csv")]


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
        "presser_finding": {                  # analysis/presser_backfill (docs/presser_analysis.md)
            "n_meetings": 92, "pct_more_cautious": 0.87, "mean_gap": -0.113,
            "p_sign_test": 1.7e-13,
            "note": "기자회견 톤이 성명문보다 일관되게 신중 (2011~2026, 4의장)",
        },
        "calibration": {                      # analysis/reliability_diagram
            "temperature": 3.1, "ece_raw": 0.294, "ece_calibrated": 0.112,
            "entropy_raw": 0.24, "entropy_calibrated": 0.79,
        },
    }


def main():
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)

    files = {
        "meetings.json": export_meetings(con),
        "alerts.json": export_alerts(con),
        "news_daily.json": export_news_daily(),
        "daily_signals.json": export_daily_signals(),
        "market.json": export_market(con),
        "presser.json": export_presser(),
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
