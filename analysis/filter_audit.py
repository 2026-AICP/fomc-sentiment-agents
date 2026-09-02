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
  python3 analysis/filter_audit.py sample 40              # 일상 수집분에서 무작위 표본
  python3 analysis/filter_audit.py report                 # 판정 집계

  python3 analysis/filter_audit.py sample 60 --backfill   # 백필(2021~2026) 단순 무작위
  python3 analysis/filter_audit.py sample 300 --backfill --stratify   # 연도 비교까지 하려면
  python3 analysis/filter_audit.py report --backfill      # 백필 표본 집계

★백필 감사가 따로인 이유: 백필 탈락분은 27.9만 건·5.5년치라 일상 수집분(수천 건·
  며칠치)과 성격이 다르다. 통과율도 연도마다 4.7%~12.9% 로 크게 달라서, 섞어 세면
  "시기별로 필터가 다르게 작동하는가"를 볼 수 없다.
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
# 백필(2021~2026) 탈락분 — 일상 수집분과 분리해 감사한다. 구간·수집시점이 다르다.
REJECTED_BACKFILL = ROOT / "data" / "news" / "rejected_backfill.csv"
SHEET_BACKFILL = ROOT / "outputs" / "filter_audit_backfill.csv"
FIELDS = ["id", "date", "source", "title", "description", "url", "verdict", "reason"]
SEED = 42                       # 재현 가능한 표본


def _wilson(k, n, z=1.96):
    """비율의 Wilson 95% 신뢰구간.

    표본이 수십 건이면 점추정만으로는 아무 말도 할 수 없다 — 1차 감사의 33건 기준
    27.3% 는 CI 가 [15%, 44%] 라 "4건 중 1건"과 "3건 중 1건"을 구분하지 못한다.
    놓침률을 인용할 때 구간을 함께 적도록 여기서 계산해 둔다.
    """
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - m), min(1.0, c + m)


def _rows(path):
    """CSV 읽기 — 인코딩을 자동 판별한다.

    ★판정 시트는 사람이 엑셀로 열어 채운다. 한국어 윈도우 엑셀은 CSV 를 저장할 때
      기본이 CP949 라, 우리가 utf-8-sig 로 쓴 파일도 저장하고 나면 CP949 가 된다.
      utf-8-sig 로만 읽으면 UnicodeDecodeError 로 죽는다(실제로 겪음).
      쓰기는 utf-8-sig 를 유지하되(엑셀이 한글을 바로 인식), 읽기는 둘 다 받는다.
    """
    p = Path(path)
    if not p.exists():
        return []
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(p, encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"인코딩을 판별하지 못했습니다: {p}\n"
                     "  엑셀에서 '다른 이름으로 저장 → CSV UTF-8' 로 다시 저장해 보세요.")


def _stratify_by_year(rows, n, seed=SEED):
    """연도별로 균등하게 뽑는다 — 단순 무작위로는 기사 많은 해에 쏠린다.

    ★왜 층화하나: 백필 실측에서 F∧M 통과율이 연도마다 크게 달랐다
      (2021년 4.7% ~ 2026년 12.9%). 탈락 기사 수도 2022년 74,000건 대 2026년
      16,000건으로 4배 넘게 차이 난다. 단순 무작위로 뽑으면 표본의 절반이
      2022~2023 에서 나와, "시기별로 필터가 다르게 작동하는가"를 볼 수 없다.
      연도별로 같은 수를 뽑아야 그 비교가 성립한다.

    각 층에서 뽑는 수가 적어(예: 6년 × 20건) 층별 추정의 신뢰구간은 넓다.
    층별 값은 경향을 보는 용도이고, 전체 놓침률은 층 크기로 가중해 다시 계산해야 한다
    (report 가 처리한다).
    """
    rng = random.Random(seed)
    by_year = {}
    for r in rows:
        y = (r.get("published_at") or r.get("date") or "")[:4]
        if y.isdigit():
            by_year.setdefault(y, []).append(r)
    if not by_year:
        return rng.sample(rows, min(n, len(rows)))
    years = sorted(by_year)
    per = max(1, n // len(years))
    picked = []
    for y in years:
        pool = by_year[y]
        picked += rng.sample(pool, min(per, len(pool)))
    return picked


def make_sample(n=40, src=REJECTED, out=SHEET, stratify=False):
    """탈락 기사에서 무작위 n건 → 검토 시트(verdict 빈칸).

    stratify=True 면 연도별 균등 추출(백필처럼 여러 해에 걸친 자료용).
    """
    rows = _rows(src)
    if not rows:
        raise SystemExit(
            f"탈락 기사 기록이 없습니다: {src}\n"
            "engine/news_scrape.py 가 수집할 때 자동으로 쌓입니다. 먼저 수집을 한 번 돌리세요.")
    picked = (_stratify_by_year(rows, n) if stratify
              else random.Random(SEED).sample(rows, min(n, len(rows))))
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
    lo, hi = _wilson(c["2"], n)
    print(f"판정 {n}건 — 무관 {c['0']} · 주변 {c['1']} · 중요 {c['2']}")
    print(f"놓침률(중요 비율): {miss:.1%}   95% CI [{lo:.1%}, {hi:.1%}]")
    print(f"경계 포함 시:      {(c['1'] + c['2']) / n:.1%}")

    # 연도별 — 층화 표본일 때 시기별 차이를 본다
    by_year = {}
    for r in rows:
        y = (r.get("date") or "")[:4]
        if y.isdigit():
            a = by_year.setdefault(y, [0, 0])
            a[0] += 1
            a[1] += 1 if r["verdict"] == "2" else 0
    if len(by_year) > 1:
        print("\n연도별 놓침률 (표본이 얇아 경향 참고용)")
        for y in sorted(by_year):
            k, m = by_year[y][0], by_year[y][1]
            l2, h2 = _wilson(m, k)
            print(f"  {y}  {m:>2}/{k:<3} {m / k:>6.1%}   [{l2:.0%}, {h2:.0%}]")
    imp = [r for r in rows if r["verdict"] == "2"]
    if imp:
        print("\n놓친 중요 기사 예시:")
        for r in imp[:6]:
            print(f"  [{r['date']}] {r['title'][:70]}")
            if r.get("reason"):
                print(f"      ↳ {r['reason']}")
    return {"n": n, "miss_rate": miss, "counts": dict(c)}


def main():
    argv = sys.argv[1:]
    # --backfill 은 대상 파일만 고른다. 층화는 --stratify 로 따로 켠다 —
    # 둘을 묶어두면 "연도별로 뽑았으니 연도 비교가 된다"고 오해하기 쉽다.
    # 층별 20건으로는 참값 15% 와 40% 의 신뢰구간이 겹쳐 비교가 성립하지 않는다.
    # 연도 비교를 하려면 층별 50건(총 300건) 이상이 필요하다.
    backfill = "--backfill" in argv
    stratify = "--stratify" in argv
    argv = [a for a in argv if not a.startswith("--")]
    cmd = argv[0] if argv else "sample"
    src = REJECTED_BACKFILL if backfill else REJECTED
    out = SHEET_BACKFILL if backfill else SHEET

    if cmd == "sample":
        n = int(argv[1]) if len(argv) > 1 else 40
        got, total, out = make_sample(n, src=src, out=out, stratify=stratify)
        print(f"탈락 기사 {total:,}건 중 {got}건 추출"
              f"{' (연도별 층화)' if stratify else ' (단순 무작위)'} → {out}")
        print("verdict 칸에 0(무관)/1(주변)/2(중요)를 기입한 뒤 `report` 실행")
        if stratify:
            print("\n※ 층화 표본이라 층별 건수가 같습니다. 전체 놓침률을 인용할 때는")
            print("   층 크기(연도별 탈락 건수)로 가중해야 모집단 값이 됩니다.")
        else:
            print(f"\n※ 모집단 {total:,}건에서 균등 확률로 뽑았으므로 전체 놓침률을")
            print("   그대로 인용할 수 있습니다(가중 불필요).")
    elif cmd == "report":
        report(sheet=out)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
