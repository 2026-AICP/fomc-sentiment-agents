"""F그룹 질의어 누락 규모 측정 — FOMC 단독 질의 vs 기존 코퍼스.

읽기 전용 조사다. 수집 파일도 임계값도 건드리지 않는다.

## 왜

HRS(2017) (iii) 에 따라 FOMC·Federal Open Market Committee 를 F그룹에 넣었는데
(engine/news_scrape.py `_F_RE`), **API 질의어(`QUERY`)에는 안 들어가 있다.**

    QUERY = '"federal reserve" | fed'

그래서 FOMC 만 있고 fed 가 없는 기사는 애초에 회수된 적이 없다. 통과분에도
탈락분에도 없으므로 **기존 데이터로는 규모를 잴 수 없다** — 질의를 새로 던져야 한다.

## 어떻게

`engine/news_scrape.py` 의 `_one_page` 를 그대로 재사용하고 `QUERY` 만 바꾼다.
sort·sort_order·group_similar·language·limit 이 자동으로 같아지므로, 조건이
"맞췄다"가 아니라 **구조적으로 같다**. 재구현하면 그 보장이 사라진다.

답은 마지막 줄이다 — 기존 코퍼스에 없으면서 우리 F∧M 규칙을 통과하는 건수.

## 실행

    python scripts/probe_fomc_query.py --from 2026-08-01 --to 2026-09-01 \\
        --corpus data/news/fed_news.csv data/news/rejected_news.csv

코퍼스는 URL 컬럼이 있는 CSV 면 몇 개든 받는다. 백필 원본(37.9MB, gitignore)이
있는 쪽에서 돌려야 대조가 완전해진다.

`found` 가 10,000 을 넘으면 그 구간은 API 상한에 잘리므로 기간을 좁혀야 한다.
경고를 찍고 계속 진행한다 — 잘린 표본이라도 하한은 알려주기 때문이다.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import news_scrape as ns  # noqa: E402

CAP = 10_000          # Marketaux 결과셋 상한
PROBE_QUERY = "FOMC"  # F그룹에서 빠져 있던 항목만 단독으로


def load_corpus_urls(paths) -> set:
    """대조용 URL 집합. 컬럼이 없거나 빈 파일은 건너뛰되 무엇을 읽었는지 보고한다."""
    urls = set()
    for p in paths:
        f = Path(p)
        if not f.exists():
            print(f"  ! 없음: {f}")
            continue
        with open(f, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        got = {r["url"] for r in rows if r.get("url")}
        urls |= got
        print(f"  {f.name:34s} {len(rows):7,}행  URL {len(got):7,}개")
    return urls


def fetch(key, from_date, to_date, max_pages):
    """FOMC 단독 질의로 구간 전체를 훑는다. (기사 리스트, found) 반환."""
    articles, found, page = [], None, 1
    seen = set()
    while page <= max_pages:
        got, total = ns._one_page(key, from_date, page, to_date=to_date)
        if found is None:
            found = total
            print(f"  API found = {total:,}")
            if total > CAP:
                print(f"  ⚠ {CAP:,} 상한 초과 — 이 구간은 잘린다. 기간을 좁힐 것.")
        if not got:
            break
        new = [a for a in got if a.get("url") and a["url"] not in seen]
        seen.update(a["url"] for a in new)
        articles.extend(new)
        if len(got) < ns.PER_PAGE:
            break
        page += 1
    return articles, found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--corpus", nargs="+", required=True, help="URL 컬럼이 있는 CSV")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--out", default="outputs/fomc_query_gap.csv")
    a = ap.parse_args()

    # 백필(engine/news_backfill.py)과 같은 형식으로 맞춘다 — 날짜만 주면 API 가
    # 경계를 어떻게 해석하는지 보장이 없다.
    a.from_date = f"{a.from_date}T00:00"
    a.to_date = f"{a.to_date}T00:00"

    print(f"질의  : {PROBE_QUERY!r}  (평소: {ns.QUERY!r})")
    print(f"구간  : {a.from_date} ~ {a.to_date}")
    print(f"조건  : sort={ns.SORT} {ns.SORT_ORDER} · group_similar={ns.GROUP_SIMILAR} "
          f"· limit={ns.PER_PAGE}   ← news_scrape 와 같은 _one_page 를 쓴다")
    print()

    print("대조 코퍼스")
    corpus = load_corpus_urls(a.corpus)
    print(f"  합계 URL {len(corpus):,}개")
    print()

    ns.QUERY = PROBE_QUERY            # 이 한 줄이 유일한 차이다
    key = ns._api_key()

    print("질의")
    got, found = fetch(key, a.from_date, a.to_date, a.max_pages)
    print(f"  회수 {len(got):,}건 (URL 중복 제거 후)")
    print()

    new = [x for x in got if x.get("url") not in corpus]
    passes = [x for x in new if ns.relevant_of(x)]

    print("결과")
    print(f"  회수                 {len(got):6,}")
    print(f"  기존 코퍼스에 없음     {len(new):6,}")
    print(f"  └ F∧M 통과           {len(passes):6,}   ← 질의어 누락으로 놓치던 건수")
    print()

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["published_at", "title", "description", "source", "url"])
        for x in passes:
            w.writerow([x.get("published_at", ""), x.get("title", ""),
                        x.get("description", ""), x.get("source", ""), x.get("url", "")])
    print(f"통과분 {len(passes)}건 → {out}")

    if found and found > CAP:
        print("\n⚠ found 가 상한을 넘었다. 위 숫자는 **하한**이다.")


if __name__ == "__main__":
    main()
