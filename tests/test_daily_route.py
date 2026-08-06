from agents.graph import route_after_collect


def test_meeting_day_routes_to_analyst():
    assert route_after_collect({"statement_path": "/x/FOMC_2026-03-18.txt"}) == "analyst"


def test_daily_day_routes_to_news_not_end():
    # 성명문 없음 → 종료(skip)가 아니라 일별(news)로 진행
    assert route_after_collect({"statement_path": ""}) == "news"
