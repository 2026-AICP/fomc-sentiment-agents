"""Fed 축 내부(presser·minutes) z-파라미터 생성 → analysis/headline_norm.json 갱신.

build_headline_norm.py(News:Fed 50:50)와 같은 방식으로, presser·minutes 축의
(평균, 표준편차)를 커밋된 검증 CSV에서 계산해 headline_norm.json에 추가한다.
statement 축은 이미 "fed" 키로 존재(build_headline_norm.py 산출)해 재사용한다.

입력:
  - outputs/presser_tones.csv (analysis/presser_backfill.py 산출)
  - outputs/minutes_tones.csv (analysis/minutes_backfill.py 산출)

실행: python3 analysis/build_fed_axis_norm.py
출력: analysis/headline_norm.json 의 "presser"·"minutes" 키 갱신(git 커밋).
      headline.combine_fed_axes() 가 이 값으로 z 표준화(statement:presser:minutes=1:1:1).
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRESSER_CSV = ROOT / "outputs" / "presser_tones.csv"
MINUTES_CSV = ROOT / "outputs" / "minutes_tones.csv"
OUT = ROOT / "analysis" / "headline_norm.json"


def _stats(csv_path, col):
    df = pd.read_csv(csv_path)
    s = df[col].dropna()
    if len(s) < 2:
        raise SystemExit(f"{csv_path}::{col} 표본 부족(n={len(s)})")
    return len(s), round(float(s.mean()), 4), round(float(s.std()), 4)


def main():
    if not PRESSER_CSV.exists() or not MINUTES_CSV.exists():
        raise SystemExit("presser_tones.csv / minutes_tones.csv 없음 — 먼저 backfill 스크립트를 실행하세요.")
    n_p, mean_p, std_p = _stats(PRESSER_CSV, "presser")
    n_m, mean_m, std_m = _stats(MINUTES_CSV, "minutes")
    print(f"presser  n={n_p}  mean={mean_p:+.4f}  std={std_p:.4f}")
    print(f"minutes  n={n_m}  mean={mean_m:+.4f}  std={std_m:.4f}")

    params = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    params["presser"] = {"mean": mean_p, "std": std_p}
    params["minutes"] = {"mean": mean_m, "std": std_m}
    params["fed_axis_weights"] = {"statement": 1, "presser": 1, "minutes": 1}
    params.setdefault("fed_axis_validation", {})
    params["fed_axis_validation"].update({
        "note": "statement:presser:minutes=1:1:1 채택 근거 — docs/fed_weights.md §2",
        "n_meetings_presser": n_p, "n_meetings_minutes": n_m,
    })
    OUT.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
