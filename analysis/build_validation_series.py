"""검증 시리즈 생성 — 통합(z) vs VIX 월별 256개월 → analysis/validation_series.json (커밋).

-0.534 상관의 '원본 시계열'을 웹 대시보드가 겹쳐 그릴 수 있게 저장한다.
validate_robustness.aligned()/combined() 재사용(동일 데이터·동일 z) — 수치 불일치 방지.
yfinance 네트워크가 필요하므로 export_dashboard 와 분리(한 번 생성해 커밋, export는 복사만).

실행: python3 analysis/build_validation_series.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.validate_robustness import aligned, combined

OUT = ROOT / "analysis" / "validation_series.json"


def main():
    df = aligned()
    comb = combined(df, df)
    r = float(comb.corr(df.vix))
    rows = [{"month": idx.strftime("%Y-%m"), "combined": round(float(c), 3),
             "vix": round(float(v), 2)}
            for idx, c, v in zip(df.index, comb, df.vix)]
    payload = {"r": round(r, 3), "n_months": len(rows),
               "period": f"{rows[0]['month']}~{rows[-1]['month']}", "series": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"검증 시리즈 {len(rows)}개월 (r={r:+.3f}) → {OUT}")


if __name__ == "__main__":
    main()
