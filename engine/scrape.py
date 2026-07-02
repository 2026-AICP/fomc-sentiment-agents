"""FOMC 성명문 자동 수집 도구 (Phase 3+ / Data Collector 에이전트용 tool).

federalreserve.gov 에서 FOMC 성명문을 수집한다. 에이전트가 아니라 "도구"다:
  discover_statements() → fetch_statement() → 문장 분할 → 저장
Phase 7 에서 이 함수들을 Data Collector 에이전트 노드로 감싼다.

수집 구조:
  ① 달력 페이지에서 성명문 링크 목록 발견 (정규식)
  ② 각 링크의 본문(div#article) 다운로드·추출
  ③ 문장 분할 (engine.preprocess 재사용) → 회의별 .txt 저장
     (기존 데이터와 동일 형식: FOMC_statement_YYYY-MM-DD.txt, 문장 1줄씩)

의존: requests, beautifulsoup4
사용:  python3 engine/scrape.py           # 최근 3건 수집 → data/statements/
       python3 engine/scrape.py 10        # 최근 10건
"""
import re
import sys
import time
from pathlib import Path

BASE = "https://www.federalreserve.gov"
CALENDAR = f"{BASE}/monetarypolicy/fomccalendars.htm"
# 성명문 링크: /newsevents/pressreleases/monetaryYYYYMMDD[a].htm  ('a'=정책성명문, 'b'=이행지침 등 → 'a'만)
LINK_RE = re.compile(r"/newsevents/pressreleases/monetary(\d{8})([a-z])?\.htm")
HEADERS = {"User-Agent": "Mozilla/5.0 (AICP FOMC research)"}
DELAY = 1.0   # 요청 간 딜레이(초) — 서버 예의


def _get(url):
    import requests
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def discover_statements(limit=None):
    """달력 페이지 → [(date 'YYYY-MM-DD', url), ...] 최신순. 정책성명문('a'/무접미)만."""
    html = _get(CALENDAR)
    seen, out = set(), []
    for m in LINK_RE.finditer(html):
        ymd, letter = m.group(1), m.group(2)
        if letter not in (None, "a"):       # 'b','c'(이행지침 등) 제외
            continue
        if ymd in seen:
            continue
        seen.add(ymd)
        date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        out.append((date, BASE + m.group(0)))
    out.sort(reverse=True)                   # 최신순
    return out[:limit] if limit else out


def fetch_statement(url):
    """성명문 페이지 → 본문 텍스트 (문단 이어붙임). 메뉴·광고 제외."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(_get(url), "html.parser")
    article = soup.find("div", {"id": "article"})
    if not article:
        return ""
    paras = [p.get_text(" ", strip=True) for p in article.find_all("p")]
    paras = [p for p in paras if len(p) > 40]   # 짧은 자투리(날짜·서명 등) 제외
    return " ".join(paras)


def collect(out_dir="data/statements", limit=3):
    """최근 성명문 수집 → 회의별 .txt 저장 (문장 1줄씩). 이미 있으면 건너뜀(멱등)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from engine.preprocess import split_sentences

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for date, url in discover_statements(limit):
        fpath = out_dir / f"FOMC_statement_{date}.txt"
        if fpath.exists():                    # 중복 방지
            print(f"  skip {date} (이미 있음)")
            continue
        text = fetch_statement(url)
        if not text:
            print(f"  warn {date}: 본문 추출 실패 {url}")
            continue
        sents = split_sentences(text)
        fpath.write_text("\n".join(sents), encoding="utf-8")
        saved.append(date)
        print(f"  saved {date}: {len(sents)}문장 → {fpath.name}")
        time.sleep(DELAY)
    return saved


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(f"FOMC 성명문 최근 {n}건 수집...")
    got = collect(limit=n)
    print(f"완료: {len(got)}건 신규 수집")
