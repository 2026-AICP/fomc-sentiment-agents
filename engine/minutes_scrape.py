"""FOMC 회의록(minutes) 수집 — 기존 팀 수집본과 **동일 형식**으로 자동화.

성명문(scrape.py)·기자회견(presser_scrape.py)과 짝을 이루는 세 번째 도구:
  ① 회의일 → 회의록 HTML (신형/구형 URL 자동 판별)
  ② <strong> 소제목으로 섹션 분할 → 약어 코드 부여 (팀 명명규칙 재현)
  ③ data/minutes/{YYYY}/{YYYYMMDD}/{YYYYMMDD}_{CODE}.txt 저장 + 연도 README 생성

표준 6섹션 (팀 README 정의):
  DFMOMO  Developments in Financial Markets and Open Market Operations
  SRES    Staff Review of the Economic Situation
  SRFS    Staff Review of the Financial Situation
  SEO     Staff Economic Outlook
  PVCCEO  Participants' Views on Current Conditions and the Economic Outlook
  CPA     Committee Policy Action(s)
그 외 섹션은 README 에 `*` 로 표시(팀 관례). 시대별로 소제목 문구가 달라
(예: 2009~2013 DFMFRBS = ...and the Federal Reserve's Balance Sheet) 약어는 제목에서 자동 생성한다.

파일 형식: **문단당 1줄, 문단 사이 빈 줄**, 소제목은 본문에 포함하지 않음 (팀 파일과 동일).
회의록은 회의 **3주 후** 공개 → 최근 회의는 미게시(404)일 수 있고, 그때는 조용히 건너뛴다.

실행:
  python3 engine/minutes_scrape.py            # 최근 120일 회의만 (매일 자동화용 기본값)
  python3 engine/minutes_scrape.py all        # 전 회의 백필 (요청 많음 — 수동 1회용)
  python3 engine/minutes_scrape.py 2026       # 특정 연도만
  python3 engine/minutes_scrape.py 2026-01-28 # 특정 회의만
의존: requests, beautifulsoup4
"""
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.federalreserve.gov"
HEADERS = {"User-Agent": "Mozilla/5.0 (AICP FOMC research)"}
OUT_DIR = ROOT / "data" / "minutes"
DB = ROOT / "data" / "fomc.db"
DELAY = 1.0
RECENT_DAYS = 120        # 매일 자동 실행 시 살펴볼 창(회의록은 회의 3주 후 공개)

# 표준 6섹션 — 이 코드들만 README 에서 `*` 없이 나열(팀 관례)
STANDARD = ("DFMOMO", "SRES", "SRFS", "SEO", "PVCCEO", "CPA")
# 행정·절차 섹션 — 경제 감성이 아니라 조직 안건(임원 선출·규정 승인)이라 제외(팀 수집본과 동일).
# 투표 명단(Voting for/against)·전자투표(notation vote)도 같은 이유로 _END_PARA 에서 잘라낸다.
SKIP_CODES = {"AOM"}                 # Annual Organizational Matters
# 본문을 담는 블록 요소 — 문단 외에 정책지시문(blockquote)·목록(ul/ol)도 본문이다.
_BLOCKS = ("p", "blockquote", "ul", "ol")
# 약어 생성 시 건너뛰는 관사·전치사·접속사 (팀 코드 재현: SRES=Staff Review of the Economic Situation)
_STOP = {"of", "the", "in", "and", "on", "for", "to", "a", "an", "at", "by", "with"}
# 소제목 아닌 <strong>: 날짜 머리말("January 28-29, 2025"), 투표 라벨("Voting for this action:")
_DATE_HEAD = re.compile(r"^[A-Z][a-z]+\s+\d")
# 본문 종료 표지 — 투표 기록(이름 나열)은 감성분석에 노이즈라 제외(팀 수집본과 동일).
# 문단으로도, 굵은 소제목으로도 나타나므로 _is_heading 에서도 같이 배제한다.
_END_PARA = re.compile(r"^Voting (for|against) this action", re.IGNORECASE)


def minutes_urls(date: str):
    """'YYYY-MM-DD' → 후보 URL들. 2008+ 는 신형, 그 이전은 구형 경로를 쓴다."""
    d = date.replace("-", "")
    return [f"{BASE}/monetarypolicy/fomcminutes{d}.htm",     # 신형 (2008~)
            f"{BASE}/fomc/minutes/{d}.htm"]                   # 구형 (~2007)


def _acronym(title: str) -> str:
    """소제목 → 약어. 관사·전치사 제외한 각 단어 첫 글자 (팀 코드 규칙)."""
    words = re.findall(r"[A-Za-z']+", title)
    return "".join(w[0].upper() for w in words if w.lower() not in _STOP)


# 표준 6섹션은 시대별로 소제목 문구가 달라(예: 2021 "…Current **Economic** Conditions…",
# 2022 "Financial Developments…") 글자 그대로 약어를 만들면 코드가 갈린다(PVCECEO/FDOMO).
# 섹션별 시계열이 끊기지 않도록 **역할 기준으로 표준 코드에 정규화**한다(팀도 PVCCEO 로 통일).
_CANON = [
    (re.compile(r"participants'?\s+views", re.I), "PVCCEO"),
    (re.compile(r"staff\s+review.*economic", re.I), "SRES"),
    (re.compile(r"staff\s+review.*financial", re.I), "SRFS"),
    (re.compile(r"staff\s+economic\s+outlook", re.I), "SEO"),
    (re.compile(r"committee\s+policy\s+action", re.I), "CPA"),
    (re.compile(r"open\s+market\s+operations|financial\s+markets", re.I), "DFMOMO"),
]


def section_code(title: str) -> str:
    """소제목 → 코드. 표준 6섹션은 문구가 달라도 같은 코드로, 그 외는 약어 자동 생성."""
    for pat, code in _CANON:
        if pat.search(title):
            return code
    return _acronym(title)


def _is_heading(text: str) -> bool:
    """섹션 소제목인지 — 길이·콜론·날짜머리말·투표라벨·구분선을 배제."""
    t = text.strip()
    if not (15 <= len(t) <= 120) or t.endswith(":") or _DATE_HEAD.match(t):
        return False
    if _END_PARA.match(t):                       # "Voting for/against this action"
        return False
    return len(re.findall(r"[A-Za-z]{2,}", t)) >= 2      # 구분선(____)·기호만인 줄 배제


def parse_sections(html: str):
    """회의록 HTML → [(code, title, body), ...]. body 는 문단 사이 빈 줄로 이은 텍스트."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("div", {"id": "article"}) or soup
    for fn in article.find_all("div", class_="footnotes"):     # 각주 블록 제외
        fn.decompose()
    out, cur = [], None
    # 본문은 <p> 외에 정책지시문(blockquote)·항목목록(ul/ol)에도 있다 → 함께 수집.
    # 중첩(blockquote 안의 p)은 바깥 요소에서 이미 처리되므로 건너뛴다.
    for p in article.find_all(_BLOCKS):
        if p.find_parent(_BLOCKS):
            continue
        strong = p.find("strong") if p.name == "p" else None
        head = strong.get_text(" ", strip=True) if strong else ""
        # 소제목 문단: <strong> 으로 시작하는 문단 (각주번호는 제거)
        if strong and p.get_text(strip=True).startswith(head):
            title = re.sub(r"\s*\d+$", "", head)
            if _is_heading(title):
                cur = {"code": section_code(title), "title": title, "paras": []}
                out.append(cur)
                # 제목 뒤에 같은 문단에 본문이 이어지면 그것도 담는다
                rest = p.get_text(" ", strip=True)[len(head):].strip()
                if len(rest) > 40:
                    cur["paras"].append(rest)
                continue
        if cur is not None:
            t = p.get_text(" ", strip=True)
            if _END_PARA.match(t):        # 투표 기록부터는 수집 중단(다음 소제목에서 재개)
                cur = None
            elif t:
                cur["paras"].append(t)
    return [(s["code"], s["title"], "\n\n".join(s["paras"]))
            for s in out if s["paras"] and s["code"] not in SKIP_CODES]


def fetch_minutes(date: str):
    """'YYYY-MM-DD' → [(code, title, body), ...]. 미게시/없으면 None."""
    import requests
    for url in minutes_urls(date):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            raise RuntimeError(f"네트워크 오류: {type(e).__name__}") from None
        if r.status_code == 200:
            r.encoding = "utf-8"                      # en-dash 등 깨짐 방지
            secs = parse_sections(r.text)
            if secs:
                return secs
    return None


def write_year_readme(year: str, out_dir=OUT_DIR):
    """연도 README — 표준 6섹션 범례 + 회의별 추가 섹션(`*`) 목록 (팀 형식)."""
    ydir = Path(out_dir) / year
    if not ydir.exists():
        return None
    legend = {
        "DFMOMO": "Developments in Financial Markets and Open Market Operations",
        "SRES": "Staff Review of the Economic Situation",
        "SRFS": "Staff Review of the Financial Situation",
        "SEO": "Staff Economic Outlook",
        "PVCCEO": "Participants' Views on Current Conditions and the Economic Outlook",
        "CPA": "Committee Policy Action",
    }
    lines = [f"{c}: {t}" for c, t in legend.items()]
    lines.append("")
    lines.append("#Asterisks(*) used to indicate contents existing in addition to the six repetitive ones.")
    lines.append("")
    for mdir in sorted(p for p in ydir.iterdir() if p.is_dir()):
        extras = [f.stem.split("_")[-1] for f in sorted(mdir.glob("*.txt"))
                  if f.stem.split("_")[-1] not in STANDARD]
        if extras:
            lines.append(mdir.name)
            titles = _titles_index(mdir)
            for c in extras:
                lines.append(f"*{c}: {titles.get(c, '')}")
            lines.append("")
    path = ydir / f"{year}_README.txt"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _titles_index(mdir: Path):
    """회의 폴더의 _titles.tsv (code<TAB>title) → dict. 없으면 빈 dict."""
    tf = mdir / "_titles.tsv"
    if not tf.exists():
        return {}
    out = {}
    for line in tf.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            c, t = line.split("\t", 1)
            out[c] = t
    return out


def collect(dates, out_dir=OUT_DIR):
    """회의일들 → 섹션별 .txt 저장. 멱등(이미 있으면 skip), 미게시는 건너뜀."""
    out_dir = Path(out_dir)
    saved, years = [], set()
    for date in dates:
        d = date.replace("-", "")
        mdir = out_dir / d[:4] / d
        if mdir.exists() and any(mdir.glob(f"{d}_*.txt")):
            print(f"  skip {date} (이미 있음)")
            continue
        try:
            secs = fetch_minutes(date)
        except Exception as e:
            print(f"  warn {date}: {type(e).__name__} {str(e)[:40]}")
            continue
        if not secs:
            print(f"  skip {date} (회의록 미게시 — 회의 3주 후 공개)")
            continue
        mdir.mkdir(parents=True, exist_ok=True)
        titles = []
        for code, title, body in secs:
            (mdir / f"{d}_{code}.txt").write_text(body, encoding="utf-8")
            titles.append(f"{code}\t{title}")
        (mdir / "_titles.tsv").write_text("\n".join(titles) + "\n", encoding="utf-8")
        std = sum(1 for c, _, _ in secs if c in STANDARD)
        saved.append(date)
        years.add(d[:4])
        try:
            shown = mdir.relative_to(ROOT)
        except ValueError:                       # out_dir 이 레포 밖일 때(테스트 등)
            shown = mdir
        print(f"  saved {date}: 섹션 {len(secs)}개 (표준 {std}/6) → {shown}")
        time.sleep(DELAY)
    for y in sorted(years):
        write_year_readme(y, out_dir)
    return saved


def meeting_dates(year=None):
    """DB 성명문 날짜 = 회의 종료일 (회의록 URL과 동일 규칙)."""
    if not DB.exists():
        return []
    con = sqlite3.connect(DB)
    rows = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM documents WHERE doc_type='statement' ORDER BY date")]
    con.close()
    return [d for d in rows if not year or d.startswith(str(year))]


def recent_dates(days=RECENT_DAYS):
    """최근 N일 안에 열린 회의만 — 매일 자동 실행용(과거 전체 재시도 방지).

    회의록은 회의 3주 후 공개 → 120일 창이면 미게시분을 놓치지 않으면서
    요청은 회의 2~3건으로 유지된다(과거 200여 회의를 매일 두드리지 않음).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return [d for d in meeting_dates() if d >= cutoff]


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg and re.fullmatch(r"\d{4}-\d{2}-\d{2}", arg):
        dates, scope = [arg], arg
    elif arg and re.fullmatch(r"\d{4}", arg):
        dates, scope = meeting_dates(arg), f"{arg}년"
    elif arg == "all":
        dates, scope = meeting_dates(), "전체(백필)"
    else:                                  # 기본 = 최근 창 (자동화 안전 기본값)
        dates, scope = recent_dates(), f"최근 {RECENT_DAYS}일"
    if not dates:
        print(f"수집 대상 없음 [{scope}] — 새 회의가 없거나 DB가 비었습니다.")
        return
    print(f"회의록 수집 [{scope}] {len(dates)}건 ({dates[0]} ~ {dates[-1]})")
    saved = collect(dates)
    print(f"\n신규 저장 {len(saved)}건 → {OUT_DIR}")


if __name__ == "__main__":
    main()
