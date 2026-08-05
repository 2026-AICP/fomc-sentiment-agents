"""팀이 수작업 수집한 구형 회의록(2000~2008)을 표준 구조로 이관.

`minutes_scrape.py` 는 2009년부터만 자동 파싱된다 — 그 이전 회의록은 연준 HTML 구조가
달라(소제목 <strong> 없음) 기계 분할이 안 된다. 다행히 팀이 2000~2008 구간을
**섹션별로 손수 정리**해 두었으므로, 그 산출물을 자동 수집분과 같은 형식으로 옮긴다.

입력(팀 zip 구조): {src}/minutes/{CODE}/{YYYY}/{M}월[~].txt   ← 섹션별·월별
출력(표준 구조):    data/minutes/{YYYY}/{YYYYMMDD}/{YYYYMMDD}_{CODE}.txt + _titles.tsv

월 → 회의일 매핑은 DB의 성명문 날짜(=회의 종료일)를 쓴다. 한 달에 회의가 두 번인
예외(긴급 회의)는 아래 _AMBIGUOUS 로 명시 — 팀 파일은 **정기 회의** 기준이다.

실행: python3 engine/import_team_minutes.py "/path/to/FOMC Minutes"
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.minutes_scrape import STANDARD, meeting_dates, write_year_readme  # noqa: E402

OUT_DIR = ROOT / "data" / "minutes"
# 팀 정리본 이관 대상. 2009+ 는 minutes_scrape 자동 수집이 더 일관되지만,
# 자동 파싱이 실패한 회의(구형 HTML 잔존)는 팀 정리본으로 메운다 — 이미 있으면 skip.
YEARS = range(2000, 2010)
# 한 달에 회의 2회 — 팀 파일은 정기 회의분. 긴급(intermeeting) 회의는 제외한다.
_AMBIGUOUS = {"2001-01": "2001-01-31",     # 01-03 은 긴급 인하 전화회의
              "2007-08": "2007-08-07",     # 08-16 은 긴급 재할인율 조치
              "2008-01": "2008-01-30",     # 01-21 은 긴급 75bp 인하(전화회의)
              "2008-10": "2008-10-29"}     # 10-07 은 각국 공조 긴급 인하
_MONTH_FILE = re.compile(r"^(\d{1,2})월~?\.txt$")

# 팀 폴더의 섹션 코드 → 표준 코드 (표준 6섹션은 이름이 같지만, 방어적으로 매핑)
_CODE_MAP = {c: c for c in STANDARD}


def month_to_date(year: int, month: int, by_month):
    """(연,월) → 회의일. 한 달 2회면 _AMBIGUOUS 로 정기 회의 선택."""
    key = f"{year:04d}-{month:02d}"
    cands = by_month.get(key, [])
    if len(cands) == 1:
        return cands[0]
    if key in _AMBIGUOUS:
        return _AMBIGUOUS[key]
    return None                      # 회의 없음 or 판단 불가 → 호출부에서 보고


def load_team_sections(src: Path):
    """팀 폴더 → {(year, month): {code: text}}"""
    base = src / "minutes"
    if not base.exists():
        raise SystemExit(f"팀 섹션 폴더가 없습니다: {base}")
    out = defaultdict(dict)
    for code_dir in sorted(base.iterdir()):
        if not code_dir.is_dir():
            continue
        code = _CODE_MAP.get(code_dir.name)
        if not code:                                   # 표준 6섹션만 이관
            continue
        for ydir in sorted(code_dir.iterdir()):
            if not ydir.is_dir() or not ydir.name.isdigit():
                continue
            year = int(ydir.name)
            if year not in YEARS:
                continue
            for f in ydir.glob("*.txt"):
                m = _MONTH_FILE.match(f.name)
                if not m:
                    continue
                text = f.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    out[(year, int(m.group(1)))][code] = text
    return out


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not src or not src.exists():
        raise SystemExit('사용법: python3 engine/import_team_minutes.py "/path/to/FOMC Minutes"')

    by_month = defaultdict(list)
    for d in meeting_dates():
        by_month[d[:7]].append(d)

    sections = load_team_sections(src)
    print(f"팀 정리본: {len(sections)}개월 ({min(sections)[0]}~{max(sections)[0]})")

    made = skipped = unmapped = 0
    years = set()
    for (year, month), codes in sorted(sections.items()):
        date = month_to_date(year, month, by_month)
        if not date:
            print(f"  ⚠ 매핑 실패 {year}-{month:02d} (회의 {by_month.get(f'{year}-{month:02d}', [])})")
            unmapped += 1
            continue
        d = date.replace("-", "")
        mdir = OUT_DIR / d[:4] / d
        if mdir.exists() and any(mdir.glob(f"{d}_*.txt")):
            skipped += 1
            continue
        mdir.mkdir(parents=True, exist_ok=True)
        titles = []
        for code, text in sorted(codes.items()):
            (mdir / f"{d}_{code}.txt").write_text(text, encoding="utf-8")
            titles.append(f"{code}\t(팀 수작업 정리본)")
        (mdir / "_titles.tsv").write_text("\n".join(titles) + "\n", encoding="utf-8")
        made += 1
        years.add(d[:4])
        print(f"  imported {date}: 섹션 {len(codes)}개 ({', '.join(sorted(codes))})")

    for y in sorted(years):
        write_year_readme(y, OUT_DIR)
    print(f"\n이관 {made}건 · 이미 있음 {skipped}건 · 매핑실패 {unmapped}건 → {OUT_DIR}")


if __name__ == "__main__":
    main()
