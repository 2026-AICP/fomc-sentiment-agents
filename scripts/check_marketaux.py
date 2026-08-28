"""Marketaux 진단 — 유료 전환 판단용. 요청 8개만 쓴다.

두 가지를 확인한다 (약 26요청, 무료 한도 100/일):
  ① 과거 기사 접근 가능 여부 — 무료 키로 2022~2026 구간이 조회되는가?
     (백필이 가능한지, 아니면 플랜 제약인지 판별)
  ② group_similar 기본값(true)이 표본을 얼마나 줄이는가?

키는 .newsapi_key 또는 환경변수 NEWS_API_KEY 에서 읽고 **화면에 절대 출력하지 않는다.**
Marketaux 대시보드(로그인 → API key)에서 받아 저장소 루트에 .newsapi_key 로 두면 된다.
(.newsapi_key 는 gitignore 대상)

실행:  python scripts/check_marketaux.py
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
        return None, None, f"{e.get('code', '?')} — {str(e.get('message', ''))[:70]}"
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
    urls, n_req = [], 0
    for p in range(1, pages + 1):
        _, arts, err = _page(key, after, None, group_similar, page=p, limit=limit)
        n_req += 1
        if err or not arts:
            break
        urls += [a.get("url", "") for a in arts if a.get("url")]
    return urls, n_req


def main():
    key = api_key()

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
    if hist_ok >= 3:
        print("과거 접근 **가능**. 백필은 요청 수 문제이므로 유료 전환으로 해결된다.")
    elif hist_ok == 0 and found_now:
        print("과거 **조회 불가**(최근은 됨) — 플랜 제약일 가능성.")
        print("        유료로 열리는지 Marketaux 지원팀에 문의 후 결제하세요.")
    else:
        print("판별 실패 — 키·네트워크를 확인하세요.")

    print("\n" + "=" * 66)
    print("② group_similar 기본값(true)이 표본을 얼마나 줄이나")
    print("=" * 66)
    on_f, _ = probe(key, recent, group_similar=True)
    off_f, _ = probe(key, recent, group_similar=False)
    print(f"  meta.found   true {str(on_f):>6}건  /  false {str(off_f):>6}건", end="")
    print("   ← 같으면 found 는 그룹화 이전 개수라는 뜻" if on_f == off_f else "")

    # found 로는 판별이 안 되므로 실제 반환분을 센다
    PAGES = 10
    u_on, r1 = collect_urls(key, recent, True, pages=PAGES)
    u_off, r2 = collect_urls(key, recent, False, pages=PAGES)
    s_on, s_off = set(u_on), set(u_off)
    print(f"\n  실제 반환 ({PAGES}쪽까지 회수)")
    print(f"    true  : {len(u_on):>4}건 (고유 {len(s_on)})")
    print(f"    false : {len(u_off):>4}건 (고유 {len(s_off)})")
    only_off = s_off - s_on
    print(f"    false 에서만 나온 기사: {len(only_off)}건")
    if len(s_off) > len(s_on) or only_off:
        print("  → 묶임이 실제로 기사를 걸러내고 있다. 전수 회수 시 표본이 늘어난다.")
    else:
        print("  → 같은 기사들이 돌아왔다. 이 구간에선 묶임 효과가 없다"
              " (다른 시기·이벤트일엔 다를 수 있음).")

    print(f"\n※ 총 {6 + r1 + r2}요청 사용 (무료 한도 100/일).")


if __name__ == "__main__":
    main()
