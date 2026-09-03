"""마크다운 문서 → PDF (노션·공유용).

팀 공유 문서를 노션에 붙이거나 PDF 로 돌릴 일이 반복돼서 스크립트로 둔다.

변환 경로: Markdown → HTML(한글 조판 CSS) → Chrome 헤드리스 --print-to-pdf.
  reportlab 계열을 쓰지 않는 이유는 한글 폰트 등록이 번거롭고 표 조판이 약해서다.
  Chrome 은 윈도우에 이미 있고 맑은 고딕을 그대로 써서 한글이 깨지지 않는다.

실행:
  python scripts/md2pdf.py docs/scope_impact.md
  python scripts/md2pdf.py docs/scope_impact.md -o "출력 이름.pdf"
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
body { font-family: "Malgun Gothic","맑은 고딕",-apple-system,sans-serif;
       font-size: 10.2pt; line-height: 1.65; color: #1a1a1a; }
h1 { font-size: 19pt; margin: 0 0 4pt; padding-bottom: 8pt;
     border-bottom: 2.5px solid #1a1a1a; letter-spacing: -0.4px; }
h2 { font-size: 13.5pt; margin: 22pt 0 8pt; padding-top: 4pt;
     border-top: 1px solid #d8d8d8; page-break-after: avoid; }
h3 { font-size: 11.4pt; margin: 15pt 0 6pt; color: #333; page-break-after: avoid; }
h1+p, h2+p, h3+p { margin-top: 0; }
p, li { margin: 5pt 0; }
ul, ol { padding-left: 20pt; margin: 6pt 0; }
strong { font-weight: 700; }
hr { border: 0; border-top: 1px solid #e2e2e2; margin: 16pt 0; }
table { border-collapse: collapse; width: 100%; margin: 10pt 0;
        font-size: 9.4pt; page-break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 5pt 7pt; text-align: left;
         vertical-align: top; }
th { background: #f2f2f2; font-weight: 700; }
tr:nth-child(even) td { background: #fafafa; }
blockquote { margin: 10pt 0; padding: 8pt 12pt; border-left: 3px solid #999;
             background: #f7f7f7; page-break-inside: avoid; }
blockquote p { margin: 3pt 0; }
code { font-family: Consolas,"D2Coding",monospace; font-size: 9pt;
       background: #f0f0f0; padding: 1pt 3pt; border-radius: 2px; }
pre { background: #f6f6f6; border: 1px solid #e0e0e0; border-radius: 3px;
      padding: 8pt 10pt; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
/* 체크리스트: '- [ ]' 가 리터럴로 남는 걸 그대로 살려 인쇄해도 읽히게 */
li { page-break-inside: avoid; }
"""


def find_chrome():
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("Chrome/Edge 를 찾지 못했습니다. CHROME_CANDIDATES 에 경로를 추가하세요.")


def to_pdf(md_path: Path, out_path: Path):
    import markdown

    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    html = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<title>{md_path.stem}</title><style>{CSS}</style></head>"
            f"<body>{body}</body></html>")

    # Chrome 은 file:// 로 읽으므로 임시 HTML 을 만들어 넘긴다.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "doc.html"
        tmp.write_text(html, encoding="utf-8")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
               "--no-pdf-header-footer", f"--print-to-pdf={out_path}",
               tmp.as_uri()]
        # encoding/errors 를 명시한다 — 한국어 윈도우에서 기본이 cp949 라
        # Chrome 이 UTF-8 로 뱉는 경고 한 줄에 UnicodeDecodeError 로 죽는다.
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                           encoding="utf-8", errors="replace")
        if not out_path.exists():
            raise SystemExit(f"PDF 생성 실패\n{r.stderr[-800:]}")
    return out_path


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    md = Path(argv[0])
    if not md.is_absolute():
        md = ROOT / md
    if not md.exists():
        raise SystemExit(f"파일이 없습니다: {md}")
    out = (Path(argv[argv.index("-o") + 1]) if "-o" in argv
           else md.with_suffix(".pdf"))
    if not out.is_absolute():
        out = ROOT / out
    to_pdf(md, out)
    print(f"{md.name} → {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
