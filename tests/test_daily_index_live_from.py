"""통합지수가 수집 초기 구간(07-03~07-09)을 버리는지.

왜 지키는가: 뉴스 페이지(export_dashboard)는 NEWS_LIVE_FROM 으로 그 7일을
빼고 있었는데 통합지수(daily_index)는 넣고 있었다. 두 곳이 어긋난 채로
라이브 std 를 재면 0.2009 대신 0.2390 이 나오고, 그 값으로 z-파라미터를
고르면 주별·일별 판단이 뒤집힌다 — 실제로 한 번 뒤집혔다.
경위: docs/headline_norm_issue.md §8.

★출력 경로를 반드시 넘긴다. 기본값은 진짜 outputs/daily_headline.csv 라
  안 넘기면 테스트가 운영 산출물을 덮어쓴다.
"""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis import daily_index as di
from analysis.news_index_live import NEWS_LIVE_FROM

COLS = ["date", "n_articles", "mean_score", "share_pos_minus_neg",
        "conf_weighted", "ci_lo", "ci_hi", "confidence"]
DAYS = ["2026-07-03", "2026-07-08", "2026-07-09",    # 경계 이전 — 빠져야 함
        "2026-07-10", "2026-07-11"]                  # 경계 이후 — 남아야 함


@pytest.fixture
def news_csv(tmp_path):
    p = tmp_path / "news_index_live.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for i, d in enumerate(DAYS):
            w.writerow([d, 20 + i, 0.1, 0.2, 0.15, -0.1, 0.4, 0.6])
    return p


def test_pre_launch_days_are_dropped(news_csv, tmp_path):
    df = di.build_daily(news_csv=news_csv, out=tmp_path / "out.csv")
    assert list(df["date"]) == ["2026-07-10", "2026-07-11"]


def test_boundary_date_itself_is_kept(news_csv, tmp_path):
    """경계일은 포함이다(>= 이지 > 가 아니다)."""
    df = di.build_daily(news_csv=news_csv, out=tmp_path / "out.csv")
    assert NEWS_LIVE_FROM in set(df["date"])


def test_real_output_untouched(news_csv, tmp_path):
    """out 을 넘기면 운영 산출물은 건드리지 않는다."""
    real = ROOT / "outputs" / "daily_headline.csv"
    before = real.read_bytes() if real.exists() else None
    di.build_daily(news_csv=news_csv, out=tmp_path / "out.csv")
    after = real.read_bytes() if real.exists() else None
    assert before == after


def test_constant_matches_dashboard_export():
    """표시부와 같은 경계를 쓰는지 — 어긋나면 9/11 이전 상태로 돌아간다.

    export_dashboard.py 는 deploy 브랜치에만 그 로직이 있다(main 쪽은
    백필 이어붙이기가 없는 갈래다). 그래서 파일이 있을 때만 검사한다.
    """
    src = (ROOT / "analysis" / "export_dashboard.py").read_text(encoding="utf-8")
    if "NEWS_LIVE_FROM" not in src:
        pytest.skip("이 브랜치의 export_dashboard 에는 백필 이어붙이기가 없다")
    for line in src.splitlines():
        if line.startswith("NEWS_LIVE_FROM"):
            assert NEWS_LIVE_FROM in line, "표시부와 통합지수의 경계가 다르다"
            break
    else:
        # 정의 없이 import 해 쓰는 형태면 그것이 바람직한 상태다
        assert "news_index_live import" in src or "NEWS_LIVE_FROM" in src


# ── 표시부: 백필(주별)과 라이브(일별)가 겹치지 않는지 ────────────────────────
# 2026-09-11 회귀: 재수집한 백필이 09-10 까지 덮자 9주가 라이브 구간과 겹쳐
# 같은 기간이 주별·일별로 두 번 그려졌다. 그전 CSV 가 마침 07-06 에서 끝나
# 드러나지 않았을 뿐, export 가 CSV 의 끝 날짜에 기대고 있었다.

def _row(d):
    return {"date": d, "n_articles": "20", "conf_weighted": "0.1",
            "ci_lo": "-0.1", "ci_hi": "0.3", "confidence": "0.6"}


def test_backfill_and_live_never_overlap(monkeypatch):
    ed = pytest.importorskip("analysis.export_dashboard")
    if not hasattr(ed, "export_news_daily"):
        pytest.skip("이 브랜치의 export_dashboard 에는 백필 이어붙이기가 없다")

    # 백필이 경계 너머까지 덮는 상황을 만든다 (실제로 일어났던 상태)
    weekly = ["2026-06-29", "2026-07-06", "2026-07-13", "2026-08-31"]
    daily = ["2026-07-09", "2026-07-10", "2026-09-10"]

    def fake_rows(path):
        name = str(path)
        return [_row(d) for d in (weekly if "backfill" in name else daily)]

    monkeypatch.setattr(ed, "_csv_rows", fake_rows)
    out = ed.export_news_daily()

    w = [r["date"] for r in out if r["period"] == "weekly"]
    d = [r["date"] for r in out if r["period"] == "daily"]
    assert max(w) < min(d), f"주별({max(w)})이 일별({min(d)}) 구간을 침범했다"
    assert w == ["2026-06-29", "2026-07-06"]     # 경계 이후 주는 빠진다
    assert d == ["2026-07-10", "2026-09-10"]     # 경계 이전 날은 빠진다

    dates = [r["date"] for r in out]
    assert len(dates) == len(set(dates)), "같은 날짜가 두 번 나간다"
