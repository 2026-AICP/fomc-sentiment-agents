"""과거 뉴스 백필 — WSJ 백본(~2021-05)과 라이브(2026-07~) 사이의 공백을 메운다.

공백은 **2021-06 ~ 2026-06, 약 61개월**이다. WSJ 수집이 2021-05 에서 멈췄고
Marketaux 라이브는 2026-07 에 시작해서, 그 사이가 비어 있다. 어떤 소스로도 수집을
시도한 적이 없는 구간이다(무료 티어로는 분량상 불가능했다 — 하루 300건 상한에
약 20만 건이라 500일이 걸린다).

Standard 전환(요청당 50건 · 하루 10,000요청)으로 가능해졌다.

★일상 수집과 다른 점 세 가지
  1. **월 단위로 끊는다.** Marketaux 는 한 질의의 결과셋이 20,000건을 넘을 수 없다
     (문서: limit=50 이면 최대 page=400). 월별이면 실측 밀도(하루 55~191건) 기준
     1,700~5,900건이라 여유가 있다. 그래도 넘치면 자동으로 주 단위로 쪼갠다.
  2. **별도 파일에 쌓는다.** data/news/fed_news.csv 에 섞지 않는다 — 수집 시점과
     경위가 다르고, 라이브분은 한동안 group_similar=true 로 모은 것이라 성격이 같지
     않다. 합칠지는 분석 단계에서 판단할 문제라 원본을 갈라 둔다.
  3. **중단·재개된다.** 61개월 × 수십 요청이라 한 번에 끝나지 않을 수 있다. 끝낸 달을
     상태 파일에 남겨, 다시 실행하면 남은 달부터 이어서 한다.

필터·정렬·오류 처리는 news_scrape 의 것을 그대로 쓴다. 백필이 자체 로직을 갖게 하면
두 경로의 표본 성격이 달라져 나중에 비교가 불가능해진다.

★모집단 주의: 2021년 경계에서 소스가 WSJ(단일 매체 초록)에서 Marketaux(다매체
제목+설명)로 바뀐다. 이어 붙여 하나의 연속 시계열로 쓰면 안 된다 —
구간별로 나눠 분석해야 한다(지도교수 확정: 예측이 아니라 설명 방향).

실행:
  python3 engine/news_backfill.py --dry-run        # 월별 분량·요청 수만 추정 (61요청)
  python3 engine/news_backfill.py                  # 2021-06 ~ 2026-06 전체
  python3 engine/news_backfill.py 2022-01 2022-12  # 구간 지정
  python3 engine/news_backfill.py --reset          # 진행 상태 초기화 후 처음부터
"""
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.news_scrape import (                      # noqa: E402
    ApiError, BASE_DELAY, DELAY_STEP, MAX_DELAY, MAX_FAIL_STREAK, PER_PAGE,
    RATE_LIMIT_WAIT, _api_key, _log_rejected, _one_page, relevant_of,
    _ensure_columns, _row, COLUMNS,
)

OUT = ROOT / "data" / "news" / "fed_news_backfill.csv"
REJECTED = ROOT / "data" / "news" / "rejected_backfill.csv"
STATE = ROOT / "data" / "news" / "backfill_state.json"

DEFAULT_FROM, DEFAULT_TO = "2021-06", "2026-06"
MAX_RESULT_SET = 20000      # Marketaux 하드 상한 — 넘으면 구간을 더 쪼갠다
MAX_PAGES = 400             # 20,000 / PER_PAGE(50). 안전 상한
# 컬럼은 news_scrape.COLUMNS 를 그대로 쓴다 — 두 곳에 적어두면 어긋난다
# (2026-09 snippet·keywords 추가 때 실제로 갈릴 뻔했다).


# ── 기간 유틸 ────────────────────────────────────────────────────────────
def month_range(a: str, b: str):
    """'2021-06','2026-06' → [(월초, 다음월초), ...] ISO 문자열 쌍."""
    y, m = map(int, a.split("-"))
    ey, em = map(int, b.split("-"))
    out = []
    while (y, m) <= (ey, em):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((f"{y:04d}-{m:02d}", f"{y:04d}-{m:02d}-01T00:00",
                    f"{ny:04d}-{nm:02d}-01T00:00"))
        y, m = ny, nm
    return out


def split_weeks(after: str, before: str):
    """월 하나가 결과셋 상한을 넘을 때 주 단위로 쪼갠다."""
    a = datetime.fromisoformat(after).replace(tzinfo=timezone.utc)
    b = datetime.fromisoformat(before).replace(tzinfo=timezone.utc)
    out, cur = [], a
    while cur < b:
        nxt = min(cur + timedelta(days=7), b)
        out.append((cur.strftime("%Y-%m-%dT%H:%M"), nxt.strftime("%Y-%m-%dT%H:%M")))
        cur = nxt
    return out


# ── 상태(중단·재개) ──────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            print("  [경고] 상태 파일이 손상됐습니다 — 처음부터 시작합니다.", file=sys.stderr)
    return {"done": {}, "started_at": datetime.now(timezone.utc).isoformat()}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 수집 ────────────────────────────────────────────────────────────────
def fetch_window(key, after, before, delay_box) -> tuple[list, int, int]:
    """한 구간 전체를 페이지 넘겨 회수 → (기사, 매칭 풀, 요청 수).

    delay_box 는 [현재 간격] 한 칸짜리 리스트다 — 429 를 만나면 이 실행 전체의
    간격을 올려야 해서 호출 간에 값을 이어 나른다.
    """
    got, found, n_req, streak = [], None, 0, 0
    for page in range(1, MAX_PAGES + 1):
        arts = None
        for attempt in range(3):
            try:
                arts, found = _one_page(key, after, page, to_date=before)
                n_req += 1
                break
            except RuntimeError as e:
                n_req += 1
                if getattr(e, "terminal", False):
                    raise
                if getattr(e, "status", None) == 429:
                    delay_box[0] = min(delay_box[0] + DELAY_STEP, MAX_DELAY)
                    time.sleep(getattr(e, "retry_after", None) or RATE_LIMIT_WAIT)
                elif attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        if arts is None:                      # 이 페이지 포기
            streak += 1
            if streak >= MAX_FAIL_STREAK:
                print(f"    ⚠ {streak}쪽 연속 실패 — 이 구간 중단 (지금까지 {len(got)}건)")
                break
            continue
        streak = 0
        if not arts:                          # 빈 페이지 = 소진
            break
        got.extend(arts)
        time.sleep(delay_box[0])
    return got, (found or 0), n_req


def append_rows(rows, path=None) -> int:
    """URL 중복을 걸러 append. 재실행해도 같은 기사가 쌓이지 않는다(멱등).

    ★기본값을 path=OUT 으로 두지 않는 이유: 기본 인자는 **함수 정의 시점**에 한 번
      평가돼 그때의 OUT 을 붙들고 있는다. 테스트가 모듈의 OUT 을 임시 경로로 바꿔도
      이 함수만 원래 경로에 쓴다 — 실제로 검증 중에 가짜 기사 600행이 진짜
      데이터 파일에 들어갔다. 호출 시점에 모듈 전역을 보도록 None 으로 둔다.
    """
    path = Path(path or OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_columns(path)                       # 구 스키마 자동 이관
    seen = set()
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            seen = {r.get("url", "") for r in csv.DictReader(f)}
    fresh = [a for a in rows if a.get("url") and a["url"] not in seen]
    if not fresh:
        return 0
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(COLUMNS)
        for a in fresh:
            w.writerow(_row(a))
    return len(fresh)


def dry_run(key, months):
    """월별 매칭 풀만 확인 — 월당 1요청. 실제 수집 전 규모를 가늠한다."""
    print(f"{'월':<10}{'매칭 풀':>10}{'예상 요청':>10}   비고")
    print("-" * 52)
    total_found = total_req = 0
    for label, after, before in months:
        try:
            _, found = _one_page(key, after, 1, to_date=before)
        except RuntimeError as e:
            print(f"{label:<10}{'오류':>10}   {str(e)[:40]}")
            continue
        found = found or 0
        req = -(-found // PER_PAGE) + 1
        note = "★상한 초과 — 주 단위 분할" if found > MAX_RESULT_SET else ""
        print(f"{label:<10}{found:>10,}{req:>10,}   {note}")
        total_found += found
        total_req += req
        time.sleep(BASE_DELAY)
    print("-" * 52)
    print(f"{'합계':<10}{total_found:>10,}{total_req:>10,}")
    print(f"\n예상 소요: 약 {total_req * BASE_DELAY / 60:.0f}분 "
          f"(간격 {BASE_DELAY}초 기준) · 하루 한도 10,000요청")


def main():
    argv = sys.argv[1:]
    if "--reset" in argv:
        STATE.unlink(missing_ok=True)
        print("진행 상태를 초기화했습니다.")
        argv = [a for a in argv if a != "--reset"]
    dry = "--dry-run" in argv
    argv = [a for a in argv if not a.startswith("--")]
    a, b = (argv + [DEFAULT_FROM, DEFAULT_TO])[:2] if len(argv) < 2 else argv[:2]

    key = _api_key()
    months = month_range(a, b)
    print(f"백필 구간 {a} ~ {b} ({len(months)}개월)\n")

    if dry:
        dry_run(key, months)
        return

    st = load_state()
    done = st.get("done", {})
    delay_box = [BASE_DELAY]
    tot_new = tot_req = 0

    for label, after, before in months:
        if label in done:
            print(f"[{label}] 완료됨 — 건너뜀 (신규 {done[label]['new']}건)")
            continue
        # 상한을 넘는 달은 주 단위로 쪼갠다
        try:
            _, probe_found = _one_page(key, after, 1, to_date=before)
        except RuntimeError as e:
            if getattr(e, "terminal", False):
                print(f"[{label}] 중단: {e}")
                break
            probe_found = 0
        windows = (split_weeks(after, before)
                   if (probe_found or 0) > MAX_RESULT_SET else [(after, before)])

        raw = []
        for w_after, w_before in windows:
            try:
                got, found, n_req = fetch_window(key, w_after, w_before, delay_box)
            except RuntimeError as e:          # terminal — 쿼터·키
                print(f"[{label}] 중단: {e}")
                save_state(st)
                print(f"\n여기까지 저장했습니다. 다시 실행하면 {label} 부터 이어서 합니다.")
                return
            raw.extend(got)
            tot_req += n_req

        kept = [x for x in raw if relevant_of(x)]
        n_new = append_rows(kept)
        n_rej = _log_rejected(raw, kept, out=REJECTED)
        rate = f"{len(kept) / len(raw):.0%}" if raw else "-"
        print(f"[{label}] 회수 {len(raw):>5}건 → F∧M 통과 {len(kept):>4}건({rate}) "
              f"→ 신규 저장 {n_new:>4}건 (탈락기록 {n_rej})")

        done[label] = {"raw": len(raw), "kept": len(kept), "new": n_new,
                       "at": datetime.now(timezone.utc).isoformat()}
        st["done"] = done
        save_state(st)                          # 달마다 저장 — 중단돼도 여기까지는 남는다
        tot_new += n_new

    print(f"\n완료: 신규 {tot_new:,}건 저장 · 요청 {tot_req:,}회")
    print(f"→ {OUT}")
    print(f"→ 탈락 기록 {REJECTED}")
    print("\n※ 이 파일은 fed_news.csv 와 별도입니다. 2021년 경계에서 소스가"
          " WSJ→Marketaux 로 바뀌므로\n   하나의 연속 시계열로 이어 붙이지 마세요.")


if __name__ == "__main__":
    main()
