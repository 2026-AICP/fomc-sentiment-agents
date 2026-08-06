"""2d Step 2 — 회의 성명문(2pm ET) 기준 pre/post 뉴스 감성 분리 검증.

FinBERT 모델 없이 돌도록 score_articles 를 가짜 스코어러로 주입(monkeypatch).
검증: (1) 2pm ET → UTC 컷오프가 DST 자동(여름 18Z/겨울 19Z),
      (2) 컷오프 기준 pre/post 로 정확히 나뉘고 shift(=post−pre)가 계산,
      (3) 한쪽 기사 0이면 shift=None.
"""
import csv
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analysis.news_index_live as nil

HDR6 = ["date", "title", "description", "source", "url", "published_at"]


def _write_csv(path, rows, header=HDR6):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def _fake_scorer(df):
    """모델 대체: text 에 'after' 있으면 +0.8, 아니면 +0.2. entropy 고정."""
    out = df.reset_index(drop=True).copy()
    out["score"] = [0.8 if "after" in str(t) else 0.2 for t in out["text"]]
    out["entropy"] = 0.5
    out["p_pos"], out["p_neg"], out["p_neu"] = 0.6, 0.2, 0.2
    return out


def test_statement_cutoff_dst():
    """2pm ET 컷오프가 DST에 따라 여름 18:00Z / 겨울 19:00Z."""
    summer = pd.Timestamp(nil.statement_cutoff_utc("2026-06-17"))   # EDT
    winter = pd.Timestamp(nil.statement_cutoff_utc("2026-01-28"))   # EST
    assert summer.hour == 18 and summer.tz is None
    assert winter.hour == 19


def test_pre_post_split_and_shift(tmp_path, monkeypatch):
    """17:00Z(발표 전)=pre, 19:00Z(발표 후)=post 로 분리 + shift 계산."""
    p = _write_csv(tmp_path / "n.csv", [
        ["2026-06-17", "run-up", "before statement expectations, some long text here", "r.com",
         "u1", "2026-06-17T17:00:00Z"],
        ["2026-06-17", "reaction", "after the statement, market reaction long text here", "r.com",
         "u2", "2026-06-17T19:00:00Z"],
    ])
    monkeypatch.setattr(nil, "score_articles", _fake_scorer)
    res = nil.index_pre_post(p, meeting_date="2026-06-17")
    assert res["pre"]["n_articles"] == 1
    assert res["post"]["n_articles"] == 1
    assert res["pre"]["conf_weighted"] == pytest.approx(0.2)
    assert res["post"]["conf_weighted"] == pytest.approx(0.8)
    assert res["shift"] == pytest.approx(0.6)


def test_pre_post_empty_side_gives_none_shift(tmp_path, monkeypatch):
    """post 만 있고 pre 가 비면 shift=None (한쪽 없으면 비교 불가)."""
    p = _write_csv(tmp_path / "n.csv", [
        ["2026-06-17", "reaction", "after the statement, market reaction long text here", "r.com",
         "u2", "2026-06-17T19:00:00Z"],
    ])
    monkeypatch.setattr(nil, "score_articles", _fake_scorer)
    res = nil.index_pre_post(p, meeting_date="2026-06-17")
    assert res["pre"] is None
    assert res["post"]["n_articles"] == 1
    assert res["shift"] is None


def test_window_days_bound(tmp_path, monkeypatch):
    """before_days/after_days 밖의 기사는 제외된다."""
    p = _write_csv(tmp_path / "n.csv", [
        ["2026-06-10", "old", "way before the window, long enough text to be scored", "r.com",
         "u0", "2026-06-10T12:00:00Z"],                       # cutoff-7일 → 제외
        ["2026-06-17", "reaction", "after the statement reaction, long enough text now", "r.com",
         "u2", "2026-06-17T19:00:00Z"],
    ])
    monkeypatch.setattr(nil, "score_articles", _fake_scorer)
    res = nil.index_pre_post(p, meeting_date="2026-06-17", before_days=2, after_days=2)
    assert res["pre"] is None                                 # 7일 전은 pre(2일) 밖
    assert res["post"]["n_articles"] == 1
