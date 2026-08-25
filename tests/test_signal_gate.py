"""신뢰도 게이트의 판정 함수 `news_signals.confident()` 단위 테스트.

게이트가 파이프라인에 제대로 배선됐는지(=strategy_node 가 등급을 낮추는지)는
tests/test_strategy_gate.py 가 본다. 여기서는 그 아래 단계 — "몇 건부터 믿을 만한가"를
정하는 판정 함수 자체만 고정한다. 둘을 나눠 둬야 배선이 바뀌어도 임계값 회귀를 잡는다.

임계값(기사 15건·CI 폭 0.60)은 아직 잠정값이다(news_signals.Thresholds 주석 참조).
분포 기반 보정은 정상 수집 데이터가 쌓인 뒤 docs/signal_calibration.md 와 같은
절차(분위수 + 민감도 분석)로 할 것 — 그때 이 테스트의 기대값도 함께 바뀐다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.news_signals import DEFAULT, confident


def test_blocks_small_sample():
    """기사가 하한 미만이면 사유와 함께 막는다 — 사유에 실제 건수가 들어가야
    대시보드가 '왜 관망인지'를 그대로 보여줄 수 있다."""
    ok, why = confident(1, None, None)
    assert not ok and "1건" in why


def test_passes_enough_articles_and_narrow_ci():
    ok, why = confident(60, -0.07, 0.26)
    assert ok and why == ""


def test_blocks_wide_ci_even_with_enough_articles():
    """기사 수가 충분해도 어조가 크게 엇갈리면(=CI 폭 초과) 막는다.
    두 조건은 서로 다른 실패를 잡는다 — 표본 부족 vs 표본 내 불일치."""
    ok, why = confident(60, -0.5, 0.5)          # 폭 1.00 > ci_max
    assert not ok and "CI" in why


def test_ci_absent_falls_back_to_article_count():
    """기사 1건이면 부트스트랩 CI 가 NaN 이라 폭을 못 잰다. 이때도 개수 하한이
    남아 있어야 게이트가 뚫리지 않는다."""
    assert confident(DEFAULT.min_articles, float("nan"), float("nan"))[0]
    assert not confident(DEFAULT.min_articles - 1, float("nan"), float("nan"))[0]
