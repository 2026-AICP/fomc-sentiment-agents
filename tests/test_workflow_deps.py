"""매일 도는 수집기가 쓰는 외부 패키지가 워크플로에 설치되는지 검사.

사고 기록: engine/presser_scrape.py 는 PDF 를 읽으려고 함수 안에서 pypdf 를 import 하는데
daily-news.yml 이 pypdf 를 설치하지 않았다. 수집 단계가 ModuleNotFoundError 를 경고로 삼키고
넘어가 기자회견 자동 수집이 연결 이후 한 번도 성공하지 못했다(2026-09-16 회의에서 발견).
함수 안의 지연 import 까지 잡도록 소스 전체에서 import 문을 찾는다.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-news.yml"
# 매일 자동화(scripts/run_news_daily.sh)가 직접 실행하는 수집기
DAILY_SCRAPERS = ["engine/scrape.py", "engine/minutes_scrape.py", "engine/presser_scrape.py"]
# import 이름 → pip 패키지 이름 (표준 라이브러리·저장소 내부 모듈은 검사 대상 아님)
THIRD_PARTY = {"requests": "requests", "bs4": "beautifulsoup4", "pypdf": "pypdf"}


def _imported(path):
    src = (ROOT / path).read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", src, re.M))


def _installed():
    text = WORKFLOW.read_text(encoding="utf-8")
    pkgs = set()
    for line in re.findall(r"pip install ([^\n#]+)", text):
        pkgs.update(tok for tok in line.split() if not tok.startswith("-"))
    return pkgs


def test_daily_scrapers_dependencies_are_installed_in_workflow():
    installed = _installed()
    missing = {f"{mod} ({path})"
               for path in DAILY_SCRAPERS for mod in _imported(path)
               if mod in THIRD_PARTY and THIRD_PARTY[mod] not in installed}
    assert not missing, f"daily-news.yml 에 설치되지 않은 의존성: {sorted(missing)}"
