"""시장 데이터 수집·정렬·괴리 분석 자리 (Phase 5에서 구현).

  - yfinance / FRED 로 S&P500·VIX·국채금리 수집 (ET 거래일 기준)
  - 회의 인덱스 ↔ 발표 윈도우(±N일) 정렬
  - 톤-반응 정합성 / 괴리(divergence) 탐지 / 이벤트 스터디
"""


def load_market():
    raise NotImplementedError("Phase 5: 시장 데이터 구현 예정")
