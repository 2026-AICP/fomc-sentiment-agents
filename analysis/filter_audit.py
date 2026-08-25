"""뉴스 필터 감사 — "걸러낸 기사 중 정말 중요한 걸 얼마나 놓쳤나".

지도교수 지정 키워드(F그룹 AND M그룹)는 정밀도가 높은 대신, 통화정책 기사인데도
제목·요약에 지정 단어가 없으면 탈락한다. 그 놓침(false negative) 비율을 재는 도구다.

★판정 기준 — 표본을 보기 **전에** 정한다(키워드 유무가 아니라 기사 내용으로 판단).
  중요(2): 연준의 정책 결정·기조·인사, 또는 통화정책 자체를 정면으로 다룬 기사.
           지수에 들어갔어야 할 기사.
  주변(1): 금리·물가·고용 등 거시 지표 기사인데 연준 정책과의 연결이 간접적인 것.
           들어가도 되고 빠져도 되는 경계.
  무관(0): 개별 종목·상품·기업 실적·해외 이슈 등 연준 정책과 상관없는 기사.

  → 놓침률 = 중요(2) 비율. 이 값이 높으면 필터가 실제로 신호를 잃고 있다는 뜻.

실행:
  python3 analysis/filter_audit.py sample 40    # 무작위 표본 → 검토 시트 생성
  python3 analysis/filter_audit.py report       # 판정 결과 집계
"""
import csv
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REJECTED = ROOT / "data" / "news" / "rejected_news.csv"
SHEET = ROOT / "outputs" / "filter_audit_sample.csv"
FIELDS = ["id", "date", "source", "title", "description", "url", "verdict", "reason"]
SEED = 42                       # 재현 가능한 표본


def _rows(path):
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def make_sample(n=40, src=REJECTED, out=SHEET):
    """탈락 기사에서 무작위 n건 → 검토 시트(verdict 빈칸)."""
    rows = _rows(src)
    if not rows:
        raise SystemExit(
            f"탈락 기사 기록이 없습니다: {src}\n"
            "engine/news_scrape.py 가 수집할 때 자동으로 쌓입니다. 먼저 수집을 한 번 돌리세요.")
    picked = random.Random(SEED).sample(rows, min(n, len(rows)))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, r in enumerate(picked, 1):
            w.writerow({"id": i, "date": r.get("published_at", "")[:10],
                        "source": r.get("source", ""), "title": r.get("title", ""),
                        "description": (r.get("description") or "")[:200],
                        "url": r.get("url", ""), "verdict": "", "reason": ""})
    return len(picked), len(rows), out


def report(sheet=SHEET):
    """판정 집계 — 놓침률과 예시."""
    rows = [r for r in _rows(sheet) if (r.get("verdict") or "").strip() in ("0", "1", "2")]
    if not rows:
        raise SystemExit(f"판정된 행이 없습니다: {sheet}\n"
                         "verdict 칸에 0(무관)/1(주변)/2(중요)를 채우세요.")
    c = Counter(r["verdict"] for r in rows)
    n = len(rows)
    miss = c["2"] / n
    print(f"판정 {n}건 — 무관 {c['0']} · 주변 {c['1']} · 중요 {c['2']}")
    print(f"놓침률(중요 비율): {miss:.1%}")
    print(f"경계 포함 시:      {(c['1'] + c['2']) / n:.1%}")
    imp = [r for r in rows if r["verdict"] == "2"]
    if imp:
        print("\n놓친 중요 기사 예시:")
        for r in imp[:6]:
            print(f"  [{r['date']}] {r['title'][:70]}")
            if r.get("reason"):
                print(f"      ↳ {r['reason']}")
    return {"n": n, "miss_rate": miss, "counts": dict(c)}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sample"
    if cmd == "sample":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        got, total, out = make_sample(n)
        print(f"탈락 기사 {total}건 중 {got}건 무작위 추출 → {out}")
        print("verdict 칸에 0(무관)/1(주변)/2(중요)를 기입한 뒤 `report` 실행")
    elif cmd == "report":
        report()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
