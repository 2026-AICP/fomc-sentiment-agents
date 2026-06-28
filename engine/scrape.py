"""FOMC 원문 수집 자리 (Phase 3+에서 구현).

작년 scrape.py 골격 참고하되 보강할 것:
  - minutes 탐지 필터 강화 (무관한 PDF 오수집 방지)
  - 다운로드 실패 시 재시도 + 중복(sha) 관리
지금(thin-slice)은 tests/fixtures/ 의 고정 샘플만 사용한다.
"""


def discover_statements():
    raise NotImplementedError("Phase 3+: 실제 크롤링 구현 예정")
