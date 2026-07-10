"""경제·통화정책 뉴스 자동 수집 도구 (Marketaux).

FOMC 성명문(engine/scrape.py)과 짝을 이루는 "News 축" 수집 도구.
매일 나오는 Fed·경제 관련 뉴스를 받아 News Sentiment Index의 재료로 쓴다.

★API 키 (코드에 넣지 않음 — git 유출 방지):
  · 환경변수 NEWS_API_KEY, 또는
  · 저장소 루트의 .newsapi_key 파일 (gitignore됨)

Marketaux 무료 티어: 하루 100요청 · 요청당 3건 · 최근 기사 위주(실시간용).
  → 한 번 실행에 pages*3건 수집 (기본 5쪽=15건). 과거·대량은 유료 전환.
검증(과거 대량)은 WSJ, 운영(실시간)은 이 도구 — 소스 분리 원칙.
Marketaux 자체 감성점수는 쓰지 않는다 → 우리 보정 FinBERT로 직접 산출.

사용:  python3 engine/news_scrape.py           # 최근 3일 Fed 뉴스(5쪽)
       python3 engine/news_scrape.py 7         # 최근 7일
       python3 engine/news_scrape.py 7 10      # 최근 7일 · 10쪽(≈30건)
"""
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.marketaux.com/v1/news/all"
# Fed·통화정책·거시 관련만 (Marketaux 검색문법: | = OR, "구절" = 정확구절)
QUERY = '"Federal Reserve" | FOMC | "monetary policy" | "interest rates" | Powell | inflation'
PER_PAGE = 3            # 무료 티어 상한(요청당 3건). 유료면 상향 가능.
OUT = ROOT / "data" / "news" / "fed_news.csv"


def _api_key():
    key = os.getenv("NEWS_API_KEY")
    if not key:
        kf = ROOT / ".newsapi_key"
        if kf.exists():
            key = kf.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(
            "뉴스 API 키가 없습니다. 환경변수 NEWS_API_KEY 를 설정하거나 "
            "저장소 루트에 .newsapi_key 파일로 두세요 (gitignore됨)."
        )
    return key


def _one_page(key, from_date, page):
    """Marketaux 한 페이지 요청 → (articles, found). 키는 에러메시지/트레이스에 노출 안 함."""
    import requests
    params = {
        "api_token": key,          # Marketaux는 쿼리파라미터 방식(헤더 미지원)
        "search": QUERY,
        "language": "en",
        "published_after": from_date,   # ISO (YYYY-MM-DDTHH:MM)
        "limit": PER_PAGE,
        "page": page,
    }
    try:
        r = requests.get(ENDPOINT, params=params, timeout=20)
    except requests.RequestException as e:
        # 예외 메시지에 URL(=토큰) 노출 방지 → 유형만 보고 (from None 로 원인 체인 차단)
        raise RuntimeError(f"네트워크 오류: {type(e).__name__}") from None
    data = r.json() if r.content else {}
    if r.status_code != 200 or (isinstance(data, dict) and "error" in data):
        err = data.get("error", {}) if isinstance(data, dict) else {}
        # 키(api_token)를 노출하지 않는 안전한 에러 메시지 (URL 미출력)
        raise RuntimeError(
            f"Marketaux 실패 (HTTP {r.status_code}): "
            f"{err.get('code', '?')} — {err.get('message', '')}"
        )
    arts = []
    for a in data.get("data", []):
        desc = a.get("description") or a.get("snippet") or ""
        pub = a.get("published_at") or ""                 # ISO 전체 타임스탬프(UTC, 시각 포함)
        arts.append({
            "date": pub[:10],                             # YYYY-MM-DD (하위호환)
            "title": a.get("title") or "",
            "description": desc,
            "source": a.get("source") or "",              # 도메인 문자열
            "url": a.get("url") or "",
            "published_at": pub,                           # 시간대 정밀화(2d): 시각 보존
        })
    found = (data.get("meta") or {}).get("found")
    return arts, found


def discover_news(days_back=3, pages=5):
    """최근 days_back 일의 Fed 관련 기사 → ([{date,title,description,source,url}, ...], found).

    무료 티어(요청당 3건)라 pages 쪽까지 이어받아 모은다(최대 pages*3건).
    """
    key = _api_key()
    from_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
    from_date = from_dt.strftime("%Y-%m-%dT%H:%M")
    out, found = [], None
    for p in range(1, pages + 1):
        arts, found = _one_page(key, from_date, p)
        if not arts:
            break
        out.extend(arts)
        time.sleep(0.4)            # 폴라이트(무료 티어 속도제한 여유)
    return out, found


def _ensure_published_at_column(out):
    """구 5컬럼 CSV(published_at 없음) → 6컬럼으로 이관. 신행 append 전 정합성 보장.

    이미 있는 fed_news.csv(구 스키마)에 6필드 행을 붙이면 헤더/데이터 컬럼수가 어긋나
    깨지므로, append 전에 헤더에 published_at 을 더하고 구 행엔 빈값을 채운다(멱등)."""
    out = Path(out)
    if not out.exists():
        return
    with open(out, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows or "published_at" in rows[0]:
        return                                          # 이미 최신 스키마 → no-op
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(rows[0] + ["published_at"])          # 헤더 + 새 컬럼
        for r in rows[1:]:
            w.writerow(r + [""])                        # 구 행 → 빈 시각(로드 시 date 폴백)


def collect(days_back=3, pages=5, out=OUT):
    """뉴스 수집 → CSV 저장 (url 기준 중복 제거, 멱등). WSJ와 동일 컬럼."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _ensure_published_at_column(out)                    # 구 스키마 자동 이관
    articles, found = discover_news(days_back, pages)

    seen = set()
    if out.exists():                                  # 기존 url 로드 (중복 방지)
        with open(out, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                seen.add(row.get("url", ""))

    new = [a for a in articles if a["url"] and a["url"] not in seen]
    write_header = not out.exists()
    with open(out, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "title", "description", "source", "url", "published_at"])
        for a in new:
            w.writerow([a["date"], a["title"], a["description"], a["source"],
                        a["url"], a["published_at"]])
    return articles, new, found


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"최근 {days}일 Fed·경제 뉴스 수집 (Marketaux, 최대 {pages * PER_PAGE}건)...")
    got, new, found = collect(days, pages)
    extra = f" | 전체 매칭 {found:,}건" if isinstance(found, int) else ""
    print(f"  받아온 기사: {len(got)}건 | 신규 저장: {len(new)}건{extra} → {OUT}")
    if got:
        print("\n  샘플:")
        for a in got[:3]:
            print(f"   [{a['date']}] ({a['source']}) {a['title'][:70]}")
