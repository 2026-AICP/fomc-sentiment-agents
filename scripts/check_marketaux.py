"""Marketaux 진단 — 유료 전환 판단용. 부분 실행 가능.

두 가지를 확인한다 (전체 약 36요청, 무료 한도 100/일):
  ① 과거 기사 접근 가능 여부 — 무료 키로 2022~2026 구간이 조회되는가?
     (백필이 가능한지, 아니면 플랜 제약인지 판별)
  ② group_similar 기본값(true)이 표본을 얼마나 줄이는가?

키는 .newsapi_key 또는 환경변수 NEWS_API_KEY 에서 읽고 **화면에 절대 출력하지 않는다.**
Marketaux 대시보드(로그인 → API key)에서 받아 저장소 루트에 .newsapi_key 로 두면 된다.
(.newsapi_key 는 gitignore 대상)

실행:  python scripts/check_marketaux.py           # 전체 (약 36요청)
       python scripts/check_marketaux.py history   # ① 만 (6요청)
       python scripts/check_marketaux.py group     # ② 만 (약 30요청)
       python scripts/check_marketaux.py plan      # 플랜 등급만 (1요청)

★매일 07:00 KST 자동화가 최대 80요청을 쓴다. 남는 여유가 20 남짓이라 전체 실행이
  안 들어갈 수 있다. 한도는 UTC 자정에 초기화된다.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENDPOINT = "https://api.marketaux.com/v1/news/all"
QUERY = '"federal reserve" | fed'


def api_key():
    key = os.getenv("NEWS_API_KEY")
    if not key:
        p = Path(__file__).resolve().parents[1] / ".newsapi_key"
        if p.exists():
            # utf-8-sig: 메모장·PowerShell 로 만든 파일은 앞에 BOM(﻿)이 붙는데
            # 그냥 utf-8 로 읽으면 BOM 이 키 앞에 남아 인증이 실패한다(.strip() 으로도
            # 안 지워진다). 따옴표를 같이 붙여넣는 실수도 흔해 함께 제거한다.
            key = p.read_text(encoding="utf-8-sig").strip().strip('"').strip("'")
    if not key:
        sys.exit("키가 없습니다.\n"
                 "  Marketaux 대시보드에서 API key 를 받아 저장소 루트에 .newsapi_key "
                 "파일로 두거나,\n  환경변수 NEWS_API_KEY 를 설정하세요.")
    return key


def _get(params):
    """requests 우선, 막히면 curl 폴백. 키가 에러 메시지에 노출되지 않게 한다."""
    try:
        import requests
        r = requests.get(ENDPOINT, params=params, timeout=30)
        return r.json() if r.content else {}
    except Exception:
        pass
    args = ["curl", "-sS", "--max-time", "40", "-G"]
    for k, v in params.items():
        args += ["--data-urlencode", f"{k}={v}"]
    args.append(ENDPOINT)
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        sys.exit(f"요청 실패 (curl exit {p.returncode}) — 네트워크를 확인하세요.")
    return json.loads(p.stdout) if p.stdout.strip() else {}


def _page(key, after, before=None, group_similar=None, page=1, limit=3):
    params = {"api_token": key, "search": QUERY, "language": "en",
              "published_after": after, "limit": limit, "page": page,
              "sort": "published_on", "sort_order": "desc"}
    if before:
        params["published_before"] = before
    if group_similar is not None:
        params["group_similar"] = "true" if group_similar else "false"
    d = _get(params)
    if "error" in d:
        e = d["error"]
        code = str(e.get("code", "?"))
        # 쿼터 소진은 더 물어봐야 소용없다. 빈 데이터로 결론을 내는 것이 가장 나쁘므로
        # 즉시 중단시킨다 — 실제로 한 번 "요청 0건 성공"인데 판정문이 찍힌 적이 있다.
        if "usage_limit" in code or "quota" in code.lower():
            sys.exit(
                "\n[중단] 오늘 API 요청 한도를 다 썼습니다 (무료 100/일).\n"
                "  매일 07:00 KST 자동화가 최대 80요청을 쓰므로, 진단에 쓸 수 있는 여유는\n"
                "  20요청 남짓입니다. 한도는 UTC 자정에 초기화됩니다.\n"
                "  · 이미 확인된 것: 과거 기사 접근 가능(①)\n"
                "  · 남은 것: group_similar 대조 측정(②) — `python scripts/check_marketaux.py group`\n"
                "    (②만 돌리면 30요청. 그래도 부족하면 유료 전환 후 확인해도 됩니다)")
        return None, None, f"{code} — {str(e.get('message', ''))[:70]}"
    return (d.get("meta") or {}).get("found"), d.get("data", []), None


def probe(key, after, before=None, group_similar=None):
    """1요청 → meta.found. 실패 시 (None, 사유)."""
    found, _, err = _page(key, after, before, group_similar)
    return found, err


def collect_urls(key, after, group_similar, pages=10, limit=3):
    """페이지를 실제로 넘겨 받은 기사 URL 집합을 만든다.

    ★meta.found 로는 group_similar 효과를 잴 수 없다 — found 는 그룹화 **이전**
      개수일 가능성이 크고, 실제로 두 설정에서 같은 값이 나왔다. 파라미터가 바꾸는
      것은 '반환되는 기사'이므로 반환분을 직접 세야 한다.
    """
    urls, times, n_req = [], [], 0
    for p in range(1, pages + 1):
        _, arts, err = _page(key, after, None, group_similar, page=p, limit=limit)
        n_req += 1
        if err or not arts:
            break
        urls += [a.get("url", "") for a in arts if a.get("url")]
        times += [a.get("published_at", "") for a in arts if a.get("published_at")]
    return urls, times, n_req


def section_plan(key):
    """현재 플랜 등급 판별 — 요청 1개.

    Marketaux 는 플랜을 알려주는 엔드포인트가 없다. 대신 **요청당 기사 수 상한**이
    플랜마다 달라서(Free 3 · Basic 20 · Standard 50 · 그 이상 100), 크게 요청해
    실제로 몇 건이 오는지 세면 등급이 나온다.
    """
    TIERS = {3: "Free ($0 · 100요청/일)", 20: "Basic ($24~29 · 2,500요청/일)",
             50: "Standard ($41~49 · 10,000요청/일)", 100: "Premium 이상 (25,000+요청/일)"}
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    print("=" * 66)
    print("플랜 등급 확인")
    print("=" * 66)
    found, arts, err = _page(key, recent, limit=100)
    if err:
        print(f"  오류: {err}")
        return
    n = len(arts)
    tier = TIERS.get(n)
    print(f"  limit=100 요청 → 실제 반환 {n}건")
    if tier:
        print(f"  → 현재 플랜: {tier}")
    else:
        print(f"  → 알려진 등급과 일치하지 않습니다(Free 3 / Basic 20 / Standard 50 / 100).")
        print("     플랜 변경 직후면 반영에 시간이 걸릴 수 있습니다.")
    print(f"  (매칭 풀 {found}건)")

    if n >= 20:
        need = -(-(found or 0) // n) if found else 0
        print(f"\n  전수 회수 시 필요 요청: 약 {need}개  (3일 창 {found}건 기준)")
        print(f"  → engine/news_scrape.py 의 PER_PAGE 를 {n} 으로 올리면 됩니다.")
    elif n == 3:
        print("\n  ※ 아직 무료 등급입니다. 결제가 반영되지 않았거나,")
        print("     결제한 계정과 이 키의 계정이 다를 수 있습니다.")
    print("\n※ 총 1요청 사용.")


def section_group(key):
    """② group_similar 대조 측정만 — 약 30요청."""
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    print("\n" + "=" * 66)
    print("② group_similar 기본값(true)이 표본을 얼마나 줄이나")
    print("=" * 66)
    on_f, _ = probe(key, recent, group_similar=True)
    off_f, _ = probe(key, recent, group_similar=False)
    print(f"  meta.found   true {str(on_f):>6}건  /  false {str(off_f):>6}건", end="")
    print("   ← 같으면 found 는 그룹화 이전 개수라는 뜻" if on_f == off_f else "")

    # found 로는 판별이 안 되므로 실제 반환분을 센다
    PAGES = 10
    # ★대조군이 핵심이다. 설정을 바꿔 호출하면 결과가 조금 달라지는데, 그것이
    #   group_similar 효과인지 단순한 호출 간 흔들림(같은 시각대 기사의 타이 정렬,
    #   그 사이 도착한 새 기사)인지 구분할 기준이 없으면 판별이 불가능하다.
    #   **같은 설정으로 두 번** 부른 결과의 차이를 노이즈 수준으로 삼는다.
    u_on, t_on, r1 = collect_urls(key, recent, True, pages=PAGES)
    u_ctl, t_ctl, r0 = collect_urls(key, recent, True, pages=PAGES)      # 대조군
    u_off, t_off, r2 = collect_urls(key, recent, False, pages=PAGES)
    s_on, s_ctl, s_off = set(u_on), set(u_ctl), set(u_off)

    print(f"\n  실제 반환 ({PAGES}쪽까지 회수)")
    for lbl, u, t in (("true  ", u_on, t_on), ("true(대조)", u_ctl, t_ctl),
                      ("false ", u_off, t_off)):
        print(f"    {lbl:<10}{len(u):>4}건 (고유 {len(set(u))})  "
              f"가장 오래된 {min(t) if t else '-'}")

    noise = len(s_ctl - s_on)                 # 같은 설정끼리의 차이 = 노이즈
    effect = len(s_off - s_on)                # 설정을 바꿨을 때의 차이
    print(f"\n    노이즈 (true vs true)  : {noise}건")
    print(f"    효과   (true vs false) : {effect}건")

    # 같은 건수를 받았는데 false 가 '덜 과거까지' 왔다면 최근 구간이 더 촘촘했다는 뜻
    denser = bool(t_on and t_off and min(t_off) > min(t_on))
    if denser:
        print("    회수 범위: false 가 더 짧은 기간을 채웠다 → 묶임의 방증")

    print()
    if not (u_on and u_ctl and u_off):
        # 세 호출 중 하나라도 비면 비교가 성립하지 않는다. 결론을 내지 않는다.
        print("  → 판별 불가 — 회수된 기사가 없습니다(요청 한도·네트워크 확인).")
    elif effect > noise * 2 and effect >= 5 or denser:
        print("  → 묶임 효과 있음. 전수 회수 시 표본이 늘어난다.")
        for u in sorted(s_off - s_on)[:5]:
            print(f"      예: {u[:88]}")
    elif effect <= max(noise, 2):
        print("  → 설정을 바꾼 차이가 노이즈 수준이다. 이 구간에선 묶임 효과가 없다.")
        print("     (조용한 시기일 수 있으니 FOMC·잭슨홀 같은 기사 폭증일에 재확인)")
    else:
        print("  → 판별 애매. 노이즈보다 크지만 결정적이지 않다. 기사 폭증일에 재확인.")



def main():
    key = api_key()
    # 부분 실행 — 무료 한도(100/일)에서 매일 자동화가 최대 80을 쓰므로 전체(36요청)가
    # 안 들어갈 때가 있다. 필요한 절만 돌릴 수 있게 한다.
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    if part not in ("all", "history", "group", "plan"):
        sys.exit("사용법: python scripts/check_marketaux.py [all|history|group|plan]")

    if part == "plan":
        section_plan(key)
        return
    if part == "group":
        section_group(key)
        return

    print("=" * 66)
    print("① 과거 기사 접근 — 무료 키로 어디까지 조회되나")
    print("=" * 66)
    print("  각 구간 7일치의 매칭 건수(meta.found)를 본다.\n")
    windows = [("2022-06-01", "2022-06-08"), ("2023-06-01", "2023-06-08"),
               ("2024-06-01", "2024-06-08"), ("2025-06-01", "2025-06-08"),
               ("2026-01-06", "2026-01-13")]
    hist_ok = 0
    for a, b in windows:
        found, err = probe(key, f"{a}T00:00", f"{b}T00:00")
        if err:
            print(f"  {a} ~ {b}   오류: {err}")
        else:
            mark = "접근 가능" if found else "0건 — 데이터 없음/차단"
            print(f"  {a} ~ {b}   {str(found):>6}건   {mark}")
            if found:
                hist_ok += 1

    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    found_now, _ = probe(key, recent)
    print(f"\n  (대조) 최근 3일           {str(found_now):>6}건")

    print("\n  판정:", end=" ")
    n_tested = sum(1 for _ in windows)
    if hist_ok >= 3:
        print("과거 접근 **가능**. 백필은 요청 수 문제이므로 유료 전환으로 해결된다.")
    elif hist_ok == 0 and found_now:
        print("과거 **조회 불가**(최근은 됨) — 플랜 제약일 가능성.")
        print("        유료로 열리는지 Marketaux 지원팀에 문의 후 결제하세요.")
    else:
        # 데이터가 모자라면 결론을 내지 않는다 — 빈 결과로 판정문을 찍는 것이 최악이다
        print(f"판별 불가 — {n_tested}개 구간 중 {hist_ok}개만 확인됐습니다.")
        print("        키·네트워크·요청 한도를 확인한 뒤 다시 실행하세요.")

    section_group(key)


    print(f"\n※ 총 {6 + r0 + r1 + r2}요청 사용 (무료 한도 100/일).")


if __name__ == "__main__":
    main()
