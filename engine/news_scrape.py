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
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.marketaux.com/v1/news/all"
# Marketaux 검색문법: | = OR, "구절" = 정확구절.
# ★2026-08: 예전 질의문은 M그룹 단어까지 OR 로 이어붙여 "interest rates" 하나만 걸린
#   기사 — 즉 **연준 언급이 아예 없는 기사** — 까지 받아왔다. 그런데 아래 is_relevant 는
#   F그룹(연준)을 필수로 요구하므로 그런 기사는 100% 탈락이 확정돼 있다. 받는 순간 낭비다.
#   실측(3일 창): 매칭 570건 중 189건만 회수되고 그중 13%만 통과.
#   F 를 질의문에서도 필수로 걸면 풀이 292건으로 줄어 80쪽(240건) 안에 대부분 회수된다.
#   M 까지 질의문에 넣지 않는 이유: M그룹 27개를 다 못 넣으면 빠진 단어(discount window,
#   bernanke, ECB 등)만 가진 기사를 놓친다. F 만 거는 건 필터의 필수조건과 같아서 손실이 없다.
#   정밀 규칙(F그룹 AND M그룹)은 그대로 is_relevant 가 적용한다 (지도교수 세트, 2026-07).
QUERY = '"federal reserve" | fed'
PER_PAGE = 3            # 무료 티어 상한(요청당 3건). 유료면 상향 가능.
OUT = ROOT / "data" / "news" / "fed_news.csv"

# ── 뉴스 선정 = 지도교수 키워드 세트(2026-07): F그룹 AND M그룹 (각 1개 이상 언급) ──
# data/wsj/(2000~2021) 수집 때 쓴 search_term 과 동일 세트 → 과거·라이브 일관.
# F: 연준 자체 — "federal reserve" 또는 fed(=the Fed 포함). 단어경계로 오인 축소.
_F_RE = re.compile(r"\bfederal reserve\b|\bfed\b", re.IGNORECASE)
# M(27): 정책·도구 + 의장 성 + 국내외 중앙은행/직위. Volcker 는 교수 표기(Volker)도 함께 매치.
_M_RE = re.compile(
    r"money supply|open market operation|quantitative easing|monetary polic|"
    r"fed funds rate|overnight lending rate|interest rate|"
    r"lender of last resort|discount window|central bank|fed chair(?:man)?|"
    r"bernanke|vol[ck]+er|greenspan|yellen|powell|\bwarsh\b|"
    r"european central bank|\becb\b|bank of england|bank of japan|\bboj\b|"
    r"bank of china|bundesbank|bank of france|bank of italy",
    re.IGNORECASE,
)


def is_relevant(title, description=""):
    """지도교수 규칙(2026-07): 제목+설명에 F그룹 최소1 AND M그룹 최소1 이면 True."""
    text = f"{title or ''} {description or ''}"
    return bool(_F_RE.search(text) and _M_RE.search(text))


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


MAX_FAIL_STREAK = 3     # 연속 실패가 이만큼이면 API 이상으로 보고 중단


def discover_news(days_back=3, pages=5, retries=2):
    """최근 days_back 일의 Fed 관련 기사 → ([{date,title,description,source,url,published_at}, ...], found).

    무료 티어(요청당 3건)라 pages 쪽까지 이어받아 모은다(최대 pages*3건).

    견고화 — 실패한 페이지는 **건너뛰고 다음 페이지로 간다**:
    ★2026-08: 예전엔 한 페이지가 재시도까지 실패하면 그 자리에서 전체를 중단했다.
      40쪽일 땐 손해가 작았지만 80쪽으로 늘린 뒤, 64쪽에서 ReadTimeout 한 번이 나
      남은 17쪽(=51건)을 통째로 버렸다(실측: 240건 요청 → 189건 수신).
      결과가 바닥난 것과 일시 오류는 다르므로 구분해서 처리한다.
        · 빈 페이지        → 결과 소진. 정상 종료.
        · 한 페이지 실패    → 건너뛰고 계속. 그 3건만 포기.
        · 연속 3쪽 실패     → API 이상(쿼터 소진·장애)으로 보고 중단.
          누적이 아니라 '연속'인 이유: 간헐적 타임아웃은 계속 진행해야 손해가 없고,
          진짜로 죽었을 때만 남은 요청을 아껴야 한다.
    """
    key = _api_key()
    from_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
    from_date = from_dt.strftime("%Y-%m-%dT%H:%M")
    out, found, skipped, streak = [], None, 0, 0
    for p in range(1, pages + 1):
        arts, last = None, ""
        for attempt in range(retries + 1):
            try:
                arts, found = _one_page(key, from_date, p)
                break
            except RuntimeError as e:
                last = str(e)[:45]
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))          # 지수 backoff 후 재시도
        if arts is None:                                     # 재시도 소진 → 이 페이지만 포기
            skipped += 1
            streak += 1
            if streak >= MAX_FAIL_STREAK:
                print(f"  ⚠ {streak}쪽 연속 실패({last}) — API 이상으로 보고 중단"
                      f" (지금까지 {len(out)}건 유지)")
                break
            print(f"  ⚠ page {p} 건너뜀({last})")
            continue
        streak = 0
        if not arts:                                         # 빈 페이지 = 결과 소진 → 정상 종료
            break
        out.extend(arts)
        time.sleep(0.4)                                      # 폴라이트(무료 티어 속도제한 여유)
    if skipped:
        print(f"  ⚠ 건너뛴 페이지 {skipped}쪽 — 최대 {skipped * PER_PAGE}건 놓침")
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
    """뉴스 수집 → CSV 저장 (관련성 필터 + url 중복 제거, 멱등). WSJ와 동일 컬럼."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _ensure_published_at_column(out)                    # 구 스키마 자동 이관
    raw, found = discover_news(days_back, pages)
    if not raw:                                         # CI 가시성: 0건이면 조용히 넘어가지 말 것
        print("  ⚠ 수집 0건 — API 키/네트워크/쿼터 확인 필요 (뉴스 갱신 안 됨)")
    articles = [a for a in raw if is_relevant(a["title"], a["description"])]   # 2a 관련성 필터

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
    n_rej = _log_rejected(raw, articles)
    # 수집 진단 — 기사가 어느 단계에서 줄어드는지 로그에 남긴다.
    # 2026-08 에 일별 기사가 급감했을 때 "필터가 문제냐 / 수집량이 문제냐 / API 실패냐"를
    # 구분할 수치가 없어 커밋 diff 를 역추적해야 했다. 네 숫자면 다음엔 로그만 보면 된다.
    #   API 매칭(found) ≫ 받음(raw) 이면 → pages 를 못 채운 것(상한·조기중단)
    #   받음 ≫ 통과      이면 → F∧M 필터가 좁은 것
    #   통과 ≫ 신규      이면 → 이미 가진 기사(중복) — 창이 겹쳐 새 기사가 적은 것
    rate = f"{len(articles) / len(raw):.0%}" if raw else "-"
    print(f"  [수집 진단] API 매칭 {found if found is not None else '?'}건 → 받음 {len(raw)}건 "
          f"→ F∧M 통과 {len(articles)}건({rate}, 탈락기록 {n_rej}건) "
          f"→ 신규 저장 {len(new)}건(중복 {len(articles) - len(new)}건)")
    return articles, new, found


# 필터가 걸러낸 기사 — 감사(놓친 기사 점검)용 보관. 지수에는 쓰지 않는다.
REJECTED = ROOT / "data" / "news" / "rejected_news.csv"


def _log_rejected(raw, kept, out=REJECTED):
    """탈락 기사 기록 — "필터가 중요한 기사를 얼마나 놓치는가"를 나중에 점검하려면
    버리지 말고 남겨야 한다. url 중복은 건너뛰어 같은 기사가 쌓이지 않게 한다."""
    kept_urls = {a["url"] for a in kept}
    rejected = [a for a in raw if a.get("url") and a["url"] not in kept_urls]
    if not rejected:
        return 0
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if out.exists():
        with open(out, encoding="utf-8-sig") as f:
            seen = {r.get("url", "") for r in csv.DictReader(f)}
    fresh = [a for a in rejected if a["url"] not in seen]
    if not fresh:
        return 0
    write_header = not out.exists()
    with open(out, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "title", "description", "source", "url", "published_at"])
        for a in fresh:
            w.writerow([a["date"], a["title"], a["description"], a["source"],
                        a["url"], a["published_at"]])
    return len(fresh)


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"최근 {days}일 Fed·경제 뉴스 수집 (Marketaux, 최대 {pages * PER_PAGE}건)...")
    got, new, found = collect(days, pages)
    extra = f" | 전체 매칭 {found:,}건" if isinstance(found, int) else ""
    print(f"  관련 기사: {len(got)}건 | 신규 저장: {len(new)}건{extra} → {OUT}")
    if got:
        print("\n  샘플:")
        for a in got[:3]:
            print(f"   [{a['date']}] ({a['source']}) {a['title'][:70]}")
