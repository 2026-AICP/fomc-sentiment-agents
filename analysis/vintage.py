"""시점 기록(vintage) — "그때 우리가 알고 있던 값"을 지우지 않고 남긴다.

★왜 필요한가
FOMC 자료는 시차를 두고 도착한다(성명문 당일 · 기자회견 며칠 후 · 회의록 3주 후).
에이전트는 매일 미완성 회의를 재방문해 새로 도착한 자료를 반영하는데, 이때 값을
**덮어쓰면** 그 회의의 과거 기록에 나중에야 알 수 있었던 정보가 섞인다(look-ahead).
그 상태의 시계열로 설명력·예측력을 분석하면 실제보다 좋은 결과가 나온다.

그래서 값을 갱신할 때 기존 행을 고치지 않고 **새 행을 덧붙인다**:

    as_of        기록한 날 (그날 시스템이 알고 있던 상태)
    key          대상 (회의일 등)
    ...payload   그 시점의 값들

읽는 방법 두 가지:
    latest(...)      키별 **가장 최근** 값 → 사이트·리포트에 쓰는 현재 최선값
    as_of_view(...)  특정 날짜 기준 값  → 분석에 쓰는 "그때 알던 값"
    first_known(...) 키별 **최초** 기록 → 실시간 시계열(그날 즉시 알 수 있던 값)

같은 값이 반복 기록되면 로그만 커지므로, **직전 기록과 달라졌을 때만** 덧붙인다.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"

# 회의별 축 톤·신호의 시점 기록
MEETING_VINTAGE = OUTPUTS / "vintage_meetings.csv"
MEETING_FIELDS = ["as_of", "date", "statement", "minutes", "presser",
                  "combined", "grade", "fired", "n_axes"]


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _norm(v):
    """비교·저장 공통 표기. CSV 는 문자열로 읽히므로 숫자도 같은 문자열로 맞춘다
    (안 맞추면 float 0.3971 != str '0.3971' 이 되어 매번 '변경'으로 잡힌다)."""
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def _payload(row, fields, key_field):
    """비교용 — as_of 와 키를 뺀 값 부분만(표기 정규화)."""
    return {k: _norm(row.get(k)) for k in fields if k not in ("as_of", key_field)}


def record(path, key, payload, fields, key_field="date", as_of=None):
    """시점 기록 1건 덧붙이기. 직전 기록과 같으면 아무것도 하지 않는다.

    반환: 실제로 기록했으면 True.
    """
    path = Path(path)
    rows = _read(path)
    new = {k: "" for k in fields}
    new["as_of"] = as_of or _today()
    new[key_field] = key
    for k, v in payload.items():
        if k in fields:
            new[k] = _norm(v)

    prev = [r for r in rows if r.get(key_field) == key]
    if prev and _payload(prev[-1], fields, key_field) == _payload(new, fields, key_field):
        return False                       # 달라진 게 없으면 기록하지 않음

    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow(new)
    return True


def latest(path, key_field="date"):
    """키별 가장 최근 기록 → {key: row}. 현재 최선값(사이트·리포트용)."""
    out = {}
    for r in _read(path):                  # 파일이 시간순이므로 뒤가 최신
        if r.get(key_field):
            out[r[key_field]] = r
    return out


def first_known(path, key_field="date"):
    """키별 **최초** 기록 → {key: row}. 그날 즉시 알 수 있던 실시간 값."""
    out = {}
    for r in _read(path):
        k = r.get(key_field)
        if k and k not in out:
            out[k] = r
    return out


def as_of_view(path, on_date, key_field="date"):
    """`on_date` 시점에 알고 있던 값 → {key: row}. 그 이후 기록은 무시한다.

    설명력·예측력 분석은 반드시 이 뷰를 써야 미래 정보가 섞이지 않는다.
    """
    out = {}
    for r in _read(path):
        if r.get("as_of", "") <= on_date and r.get(key_field):
            out[r[key_field]] = r
    return out


def record_meeting(date, *, statement=None, minutes=None, presser=None,
                   combined=None, grade=None, fired=None, n_axes=None, as_of=None):
    """회의 1건의 현재 상태를 시점 기록에 남긴다(변화가 있을 때만)."""
    return record(MEETING_VINTAGE, date, {
        "statement": statement, "minutes": minutes, "presser": presser,
        "combined": combined, "grade": grade,
        "fired": ";".join(fired) if isinstance(fired, (list, tuple)) else fired,
        "n_axes": n_axes,
    }, MEETING_FIELDS, as_of=as_of)


def main():
    """현황 요약 — 기록 수, 사후 변경이 있었던 회의."""
    rows = _read(MEETING_VINTAGE)
    if not rows:
        print(f"기록 없음: {MEETING_VINTAGE}")
        return
    keys = {r["date"] for r in rows}
    revised = {k for k in keys if sum(1 for r in rows if r["date"] == k) > 1}
    print(f"시점 기록 {len(rows)}행 · 회의 {len(keys)}건 · 사후 갱신된 회의 {len(revised)}건")
    for k in sorted(revised)[-5:]:
        hist = [r for r in rows if r["date"] == k]
        print(f"  {k}: " + " → ".join(
            f"{r['as_of']}({r['n_axes']}축)" for r in hist))


if __name__ == "__main__":
    main()
