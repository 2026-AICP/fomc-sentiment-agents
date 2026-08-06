"""축별 톤 CSV 저장소 — 에이전트가 회의를 처리할 때 그 자리에서 갱신(upsert).

배경: 대시보드 JSON(export_dashboard)은 outputs/{minutes,presser}_tones.csv 를 읽는다.
이 파일들은 원래 배치 스크립트(*_backfill.py)로만 만들어져서, 새 회의가 열려도
누군가 배치를 다시 돌리기 전까지 갱신되지 않았다. 회의록은 3주 뒤에 도착하므로
"나중에 배치를 또 돌린다"는 전제 자체가 자동화와 맞지 않는다.

→ 에이전트가 한 회의의 축 톤을 계산한 그 순간 해당 행을 upsert 한다.
   배치는 전량 재계산(과거 백필)용으로 남기고, 일상 갱신은 이 경로가 담당한다.

  upsert_tone(path, row, fields) — date 키로 갱신/추가 후 날짜순 정렬 저장
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"

PRESSER_CSV = OUTPUTS / "presser_tones.csv"
MINUTES_CSV = OUTPUTS / "minutes_tones.csv"
PRESSER_FIELDS = ["date", "statement", "presser", "gap", "n_sentences"]
MINUTES_SECTIONS = ["DFMOMO", "SRES", "SRFS", "SEO", "PVCCEO", "CPA"]
MINUTES_FIELDS = ["date", "statement", "minutes", "gap", "confidence",
                  "n_sentences"] + MINUTES_SECTIONS


def upsert_tone(path: Path, row: dict, fields: list):
    """date 를 키로 한 행을 갱신/추가. 기존 파일의 다른 컬럼은 보존한다.

    파일이 없으면 새로 만든다. 헤더가 달라도(과거 스키마) fields 기준으로 통일.
    """
    path = Path(path)
    rows = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("date"):
                    rows[r["date"]] = r
    cur = rows.get(row["date"], {})
    cur.update({k: v for k, v in row.items() if v is not None})
    rows[row["date"]] = cur

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for d in sorted(rows):
            w.writerow({k: rows[d].get(k, "") for k in fields})
    return path


def _r(v, nd=4):
    return round(v, nd) if isinstance(v, (int, float)) else v


def save_presser(date: str, presser: dict):
    """graph.State['presser'] → presser_tones.csv 한 행."""
    return upsert_tone(PRESSER_CSV, {
        "date": date, "statement": _r(presser.get("statement_tone")),
        "presser": _r(presser.get("tone")), "gap": _r(presser.get("gap")),
        "n_sentences": presser.get("n_sentences"),
    }, PRESSER_FIELDS)


def save_minutes(date: str, minutes: dict):
    """graph.State['minutes'] → minutes_tones.csv 한 행 (섹션별 톤 포함)."""
    row = {"date": date, "statement": _r(minutes.get("statement_tone")),
           "minutes": _r(minutes.get("tone")), "gap": _r(minutes.get("gap")),
           "n_sentences": minutes.get("n_sentences")}
    for code, tone in (minutes.get("sections") or {}).items():
        if code in MINUTES_SECTIONS:
            row[code] = _r(tone)
    return upsert_tone(MINUTES_CSV, row, MINUTES_FIELDS)
