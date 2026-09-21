"""기자회견 스크래퍼 파싱 검증 — 의장 자동 감지 + 의장 발언만 추출 (네트워크 없이).

핵심: 의장을 하드코딩하지 않고 제목에서 감지 → Powell('CHAIR')·Warsh('CHAIRMAN')
호칭이 달라도, 사람이 바뀌어도 견고. 기자 질문·진행자 발언은 제외.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.presser_scrape import (detect_chair, extract_chair_remarks, presser_url)

POWELL = """January 28, 2026   Chair Powell's Press Conference  FINAL

Page 1 of 2

Transcript of Chair Powell's Press Conference
January 28, 2026

CHAIR POWELL.  Good afternoon. The economy is on a firm footing and inflation is easing.

CHRIS RUGABER.  Chris Rugaber, Associated Press. Can you talk about the path of rates?

CHAIR POWELL.  We see the current stance of policy as appropriate to promote our goals.

MICHELLE SMITH.  Thank you very much."""

WARSH = """June 17, 2026   Chairman Warsh's Press Conference  FINAL

Page 1 of 2

Transcript of Chairman Warsh's Press Conference
June 17, 2026

CHAIRMAN WARSH.  Good afternoon. My focus is on restoring price stability and credibility.

NICK TIMIRAOS.  Nick Timiraos, Wall Street Journal. Your view on the balance sheet?

CHAIRMAN WARSH.  We will take a fresh look at the balance sheet in the coming months.

MICHELLE SMITH.  Thank you."""


def test_detect_chair_handles_powell_and_warsh():
    assert detect_chair(POWELL) == "Powell"
    assert detect_chair(WARSH) == "Warsh"          # Chairman·다른 사람도 감지


def test_extract_only_powell_remarks():
    r = extract_chair_remarks(POWELL)
    assert "firm footing" in r and "current stance" in r   # 의장 발언 포함
    assert "Associated Press" not in r             # 기자 질문 제외
    assert "Thank you very much" not in r          # 진행자 제외


def test_extract_only_warsh_remarks():
    r = extract_chair_remarks(WARSH)
    assert "price stability" in r
    assert "balance sheet in the coming months" in r
    assert "Wall Street Journal" not in r          # 기자 질문 제외
    assert "Nick Timiraos" not in r


def test_no_title_returns_empty():
    assert extract_chair_remarks("random text, no transcript title here") == ""


def test_presser_url_pattern():
    assert presser_url("2026-06-17").endswith("/FOMCpresconf20260617.pdf")


# 연준은 원고를 먼저 PRELIMINARY(잠정본)로 올리고 나중에 FINAL 로 바꾼다. 페이지 머리글이
# 의장 발언 한가운데(페이지가 넘어가는 자리)에 끼므로 잠정본 머리글도 지워야 한다.
# 실측: 2026-09-16 원고에서 9조각, 2026-07-29 저장본에서 2조각이 문장 안에 남았다.
WARSH_PRELIM = """September 16, 2026 Chairman Warsh’s Press Conference PRELIMINARY 
 
Page 1 of 2 
 
Transcript of Chairman Warsh’s Press Conference 
September 16, 2026 
 
CHAIRMAN WARSH.  Good day. Resilience and the potential for even September 16, 2026 Chairman Warsh’s Press Conference PRELIMINARY 
 
Page 2 of 2 
 
greater performance are why optimism is warranted.

MICHELLE SMITH.  Thank you."""


def test_preliminary_page_header_is_stripped():
    r = extract_chair_remarks(WARSH_PRELIM)
    assert "PRELIMINARY" not in r and "Press Conference" not in r   # 머리글 조각이 남지 않는다
    assert "potential for even greater performance" in r            # 끊긴 문장이 다시 이어진다
