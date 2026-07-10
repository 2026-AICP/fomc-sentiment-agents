"""FOMC 기자회견(press conference) 트랜스크립트 수집 도구.

성명문(engine/scrape.py)과 짝을 이루는 도구. federalreserve.gov 의 기자회견 트랜스크립트
(PDF)에서 **의장 발언만** 추출해 저장한다(기자 질문·진행자 제외 → 의장 톤만 점수화).

★의장은 제목에서 자동 감지 — 하드코딩 안 함.
  2026-06 Powell→Warsh 교체처럼 사람이 바뀌고 호칭('Chair'/'Chairman')이 달라져도 견고.

수집 구조:
  URL: /mediacenter/files/FOMCpresconf{YYYYMMDD}.pdf
  ① PDF 다운로드 → pypdf 텍스트 추출
  ② 제목("... Chair/Chairman {성}'s Press Conference")에서 의장 성 추출
  ③ 그 의장 발언 턴(CHAIR/CHAIRMAN {성}.)만 골라 이어붙임 → 문장 분할
  ④ data/pressers/FOMC_presconf_{date}.txt 저장 (성명문과 동일 형식)

의존: requests, pypdf
사용:  python3 engine/presser_scrape.py 2026-06-17        # 특정 회의
       python3 engine/presser_scrape.py --recent 4        # 최근 회의 N건
※ 트랜스크립트는 회의 며칠 후 게시(없으면 404 → 건너뜀). 기자회견은 2011년~ 존재.
"""
import io
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.federalreserve.gov/mediacenter/files"
HEADERS = {"User-Agent": "Mozilla/5.0 (AICP FOMC research)"}
OUT_DIR = ROOT / "data" / "pressers"
DELAY = 1.0

# 제목: "... Chair Powell's Press Conference" / "... Chairman Warsh's Press Conference"
TITLE_RE = re.compile(r"Chair(?:man)?\s+([A-Z][a-zA-Z]+)[’'`]s Press Conference")
# 화자 라벨: 줄 시작의 ALL-CAPS 이름 + 마침표 (PDF 추출 기준). 본문 문장(혼합대소문자)과 구분.
_NEXT_SPEAKER = r"\n[A-Z][A-Z’'`\.\- ]{2,30}?\.\s"


def presser_url(date: str) -> str:
    """'YYYY-MM-DD' → 트랜스크립트 PDF URL."""
    return f"{BASE}/FOMCpresconf{date.replace('-', '')}.pdf"


def detect_chair(text: str):
    """트랜스크립트 제목에서 의장 성(surname) 자동 추출. 실패 시 None."""
    m = TITLE_RE.search(text)
    return m.group(1) if m else None


def _strip_page_noise(text: str) -> str:
    """페이지 머리말('... Press Conference FINAL')·쪽번호('Page X of Y') 제거."""
    text = re.sub(r"[A-Z][a-z]+ \d{1,2}, \d{4}\s+Chair(?:man)?\s+\w+[’'`]s Press Conference\s+FINAL",
                  " ", text)
    text = re.sub(r"Page \d+ of \d+", " ", text)
    return text


def extract_chair_remarks(text: str, surname: str = None) -> str:
    """의장(CHAIR/CHAIRMAN + 성) 발언 턴만 이어붙여 반환. 기자·진행자 제외.

    surname 미지정 시 제목에서 자동 감지. 페이지 노이즈는 사전 제거.
    """
    surname = surname or detect_chair(text)
    if not surname:
        return ""
    clean = _strip_page_noise(text)
    # 의장 라벨로 시작 → 다음 화자 라벨(또는 문서 끝) 직전까지가 한 턴
    pat = re.compile(
        rf"CHAIR(?:MAN)?\s+{re.escape(surname.upper())}\.\s+(.*?)(?={_NEXT_SPEAKER}|\Z)", re.S)
    turns = [t.replace("\n", " ") for t in pat.findall(clean)]
    return re.sub(r"\s{2,}", " ", " ".join(turns)).strip()


def _fetch_pdf_text(url: str):
    """PDF URL → 전체 텍스트. 404(미게시/없음)면 None."""
    import requests
    from pypdf import PdfReader
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    rd = PdfReader(io.BytesIO(r.content))
    return "\n".join((p.extract_text() or "") for p in rd.pages)


def fetch_presser(date: str):
    """'YYYY-MM-DD' → (surname, 의장 발언 텍스트). 트랜스크립트 없으면 None."""
    text = _fetch_pdf_text(presser_url(date))
    if text is None:
        return None
    surname = detect_chair(text)
    remarks = extract_chair_remarks(text, surname) if surname else ""
    return (surname, remarks) if remarks else None


def collect(dates, out_dir=OUT_DIR):
    """회의 날짜들 → 의장 발언 .txt 저장(문장 1줄씩). 멱등(있으면 skip). 미게시 회의는 건너뜀."""
    sys.path.insert(0, str(ROOT))
    from engine.preprocess import split_sentences
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for date in dates:
        fpath = out_dir / f"FOMC_presconf_{date}.txt"
        if fpath.exists():
            print(f"  skip {date} (이미 있음)")
            continue
        try:
            got = fetch_presser(date)
        except Exception as e:
            print(f"  warn {date}: {type(e).__name__} {str(e)[:40]}")
            continue
        if not got:
            print(f"  skip {date} (트랜스크립트 미게시/없음)")
            continue
        surname, remarks = got
        sents = split_sentences(remarks)
        fpath.write_text("\n".join(sents), encoding="utf-8")
        saved.append(date)
        print(f"  saved {date}: 의장 {surname} · {len(sents)}문장 → {fpath.name}")
        time.sleep(DELAY)
    return saved


def _recent_meeting_dates(limit):
    """data/statements 의 최근 회의 날짜 N건(성명문 파일명 기준)."""
    dates = sorted(m.group(1) for f in (ROOT / "data" / "statements").glob("FOMC_statement_*.txt")
                   if (m := re.search(r"(\d{4}-\d{2}-\d{2})", f.name)))
    return dates[-limit:] if limit else dates


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--recent":
        dates = _recent_meeting_dates(int(args[1]) if len(args) > 1 else 4)
    elif args:
        dates = args
    else:
        dates = _recent_meeting_dates(4)
    print(f"기자회견 트랜스크립트 수집: {dates}")
    got = collect(dates)
    print(f"완료: {len(got)}건 신규 → {OUT_DIR}")
