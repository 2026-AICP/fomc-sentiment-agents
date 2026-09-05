"""2d 시간대 정밀화 — load_live_news 가 기사 시각(published_at)을 보존하는지 검증.

핵심: 스크래퍼가 이제 published_at(전체 타임스탬프)을 저장하고,
load_live_news 가 그 시각을 dt 로 살려낸다(없으면 date 로 폴백 — 구 CSV 호환).
이게 회의 직전/후 뉴스 흐름을 구분(Step 2)하기 위한 토대다.
"""
import csv
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.news_index_live import load_live_news


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


HDR6 = ["date", "title", "description", "source", "url", "published_at"]
DESC = "a description that is clearly longer than twenty characters here"


def test_published_at_preserves_intraday_time(tmp_path):
    """published_at 에 시각이 있으면 dt 가 자정이 아니라 그 시각을 보존한다."""
    p = _write_csv(tmp_path / "n.csv", HDR6, [
        ["2026-06-17", "Fed holds rates", DESC, "reuters.com", "u1",
         "2026-06-17T18:30:00.000000Z"],
    ])
    df = load_live_news(p)
    assert len(df) == 1
    dt = pd.Timestamp(df["dt"].iloc[0])
    assert (dt.hour, dt.minute) == (18, 30)          # 시각 보존 (자정 아님)


def test_empty_published_at_falls_back_to_date(tmp_path):
    """published_at 이 비면 date(일자)로 폴백 → 자정. (구 행 하위호환)"""
    p = _write_csv(tmp_path / "n.csv", HDR6, [
        ["2026-06-17", "Fed keeps policy", DESC, "wsj.com", "u2", ""],
    ])
    df = load_live_news(p)
    assert len(df) == 1
    dt = pd.Timestamp(df["dt"].iloc[0])
    assert dt.date().isoformat() == "2026-06-17"
    assert (dt.hour, dt.minute) == (0, 0)            # 시각 없음 → 자정


def test_old_five_column_csv_still_loads(tmp_path):
    """published_at 컬럼이 아예 없는 구 5컬럼 CSV도 안 깨지고 로드된다."""
    p = _write_csv(tmp_path / "n.csv",
                   ["date", "title", "description", "source", "url"], [
        ["2026-06-17", "Fed statement released", DESC, "ap.com", "u3"],
    ])
    df = load_live_news(p)
    assert len(df) == 1                              # 폴백 경로로 정상 로드
    assert pd.Timestamp(df["dt"].iloc[0]).date().isoformat() == "2026-06-17"


def test_mixed_rows_intraday_and_dateonly(tmp_path):
    """시각 있는 행과 없는 행이 섞여도 각각 올바르게 처리된다."""
    p = _write_csv(tmp_path / "n.csv", HDR6, [
        ["2026-06-17", "with time", DESC, "reuters.com", "u1",
         "2026-06-17T14:05:00.000000Z"],
        ["2026-06-17", "date only", DESC, "wsj.com", "u2", ""],
    ])
    df = load_live_news(p).sort_values("dt").reset_index(drop=True)
    assert len(df) == 2
    assert (pd.Timestamp(df["dt"].iloc[0]).hour) == 0    # 폴백(자정)이 먼저
    assert (pd.Timestamp(df["dt"].iloc[1]).hour) == 14   # 시각 보존이 나중


def test_collect_migrates_old_5col_csv(tmp_path, monkeypatch):
    """구 5컬럼 CSV에 collect() append 시 자동 6컬럼 이관 + 신행 시각 보존(프로덕션 안전)."""
    import engine.news_scrape as ns
    p = _write_csv(tmp_path / "fed_news.csv",
                   ["date", "title", "description", "source", "url"],
                   [["2026-06-10", "old Fed article", DESC, "wsj.com", "old1"]])
    # 제목에 Fed 앵커 포함 → 2a 관련성 필터를 통과(필터는 신규 수집분에만 적용)
    new_art = {"date": "2026-06-17", "title": "Fed raises interest rates", "description": DESC,
               "source": "reuters.com", "url": "new1",
               "published_at": "2026-06-17T18:30:00.000000Z"}
    monkeypatch.setattr(ns, "discover_news", lambda *a, **k: ([new_art], 1))
    # 탈락분도 임시 경로로 — 안 바꾸면 _log_rejected 가 실제
    # data/news/rejected_news.csv 에 쓴다(2026-09 발견, 테스트 격리 누락).
    monkeypatch.setattr(ns, "REJECTED", tmp_path / "rejected.csv")
    ns.collect(out=p)                                    # API 미호출(monkeypatch)

    with open(p, encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert "published_at" in header                      # 헤더 이관됨
    df = load_live_news(p).sort_values("dt").reset_index(drop=True)
    assert len(df) == 2                                  # 구행 + 신행 둘 다 살아있음
    assert pd.Timestamp(df["dt"].iloc[0]).hour == 0      # 구행: date 폴백(자정)
    assert pd.Timestamp(df["dt"].iloc[1]).hour == 18     # 신행: 시각 보존


def test_index_for_window_single_day_includes_intraday(tmp_path, monkeypatch):
    """당일치 창(before=after=0)이 그날의 '하루 전체'를 포함하는지 고정.

    경계 버그 회귀 방지(2026-08): hi 가 당일 00:00 이면 자정 행만 잡혀 창이 비고,
    통합지수가 Fed 단독으로 조용히 폴백한다.
    """
    import csv
    from analysis import news_index_live as nil
    p = tmp_path / "news.csv"
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "title", "description", "source", "url", "published_at"])
        w.writerow(["2026-08-04", "Fed says a", "d", "s", "u1", "2026-08-04T10:00:00"])
        w.writerow(["2026-08-04", "Fed says b", "d", "s", "u2", "2026-08-04T23:50:00"])
        w.writerow(["2026-08-05", "Fed says c", "d", "s", "u3", "2026-08-05T00:10:00"])
        w.writerow(["2026-08-03", "Fed says d", "d", "s", "u4", "2026-08-03T09:00:00"])
    # 검증 대상은 '창 경계'뿐 — 채점(_score_window)은 모킹해 FinBERT 모델 없이도 돈다
    # (모델은 로컬·CI 환경에만 있고 저장소엔 없어, 실채점하면 환경 의존 테스트가 된다).
    monkeypatch.setattr(nil, "_score_window",
                        lambda df: {"n_articles": len(df)} if len(df) else None)
    r = nil.index_for_window(csv_path=p, center="2026-08-04", before=0, after=0)
    assert r is not None and r["n_articles"] == 2      # 당일 2건만 — 전날·다음날 제외
