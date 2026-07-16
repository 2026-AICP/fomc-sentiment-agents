"""presser 불일치 51건 검토 워크시트 생성 (repo 파일만으로 재현 — 개인 PC 불일치파일 불필요).

각 조(2인)의 라벨러 파일에서 **라벨이 갈린 문장만** 뽑아, 문장·두 라벨·현재 확정값을
한 표로 만든다. 팀은 '확정'·'사유' 칸만 채우면 됨(애매→중립 규칙). FinBERT 점수는 보지 말 것.

출력: data/labeling/불일치_검토_presser.csv
실행: python analysis/make_presser_disagreement_sheet.py
"""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LBL = ROOT / "data" / "labeling"
GT = LBL / "ground_truth_presser_150.csv"
OUT = LBL / "불일치_검토_presser.csv"
NAME = {"0": "중립", "1": "긍정", "2": "부정", "": "(미기입)"}

# (범위, 라벨러A 파일, 라벨러B 파일)
PAIRS = [
    ("1-75", "배재원", "label_배재원 (1-75).csv", "최인영", "label_최인영 (1-75).csv"),
    ("76-150", "김형준", "label_김형준 (76-150).csv", "지현민", "label_지현민 (76-150).csv"),
]


def rd(f):
    return list(csv.DictReader(open(LBL / f, encoding="utf-8-sig")))


def lab(r):
    return (r.get("label") or "").strip()


def code_name(c):
    return f"{c}({NAME.get(c, '?')})"


def main():
    # 현재 확정값(정답지 resolved) 로드
    gt = {r["id"]: (r.get("label_code") or "").strip()
          for r in rd(GT.name) if (r.get("source") or "").strip() == "resolved"}

    rows, summary = [], []
    for rng, na, fa, nb, fb in PAIRS:
        ra = rd(fa)
        mb = {r["id"]: r for r in rd(fb)}
        dis = 0
        for r in ra:
            a, b = lab(r), lab(mb[r["id"]])
            if a == b:
                continue                          # 합의(agree) → 제외
            dis += 1
            fin = gt.get(r["id"], "")
            src = ("A일치" if fin == a else "B일치" if fin == b
                   else "제3값" if fin else "미기입")
            rows.append({
                "범위": rng, "id": r["id"], "chair": r.get("chair", ""),
                "sentence": r.get("sentence", ""),
                "조": f"{na}/{nb}",
                f"A_{na}": code_name(a), f"B_{nb}": code_name(b),
                "현재_final": code_name(fin), "final_출처": src,
                "확정": "", "사유": "",
            })
        summary.append((rng, na, nb, dis))

    # 열 순서 고정(조마다 라벨러명이 달라 A_/B_ 는 합쳐 표기)
    fields = ["범위", "id", "chair", "sentence", "조",
              "A_라벨", "B_라벨", "현재_final", "final_출처", "확정", "사유"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in rows:
            a_key = next(k for k in r if k.startswith("A_"))
            b_key = next(k for k in r if k.startswith("B_"))
            w.writerow([r["범위"], r["id"], r["chair"], r["sentence"], r["조"],
                        r[a_key], r[b_key], r["현재_final"], r["final_출처"],
                        r["확정"], r["사유"]])

    print(f"불일치 검토표 {len(rows)}건 → {OUT}")
    for rng, na, nb, dis in summary:
        print(f"  {rng} ({na}/{nb}): 불일치 {dis}건")
    print("현재_final 분포:", dict(Counter(r["현재_final"] for r in rows)))
    print("final_출처 분포:", dict(Counter(r["final_출처"] for r in rows)))
    # 애매 후보: 두 라벨이 긍(1)↔부(2)로 정면 충돌한 건(중립 아님) = 판단 갈린 핵심
    polar = sum(1 for r in rows
                if "1(" in r[next(k for k in r if k.startswith("A_"))]
                and "2(" in r[next(k for k in r if k.startswith("B_"))]
                or "2(" in r[next(k for k in r if k.startswith("A_"))]
                and "1(" in r[next(k for k in r if k.startswith("B_"))])
    print(f"긍↔부 정면충돌(우선검토): {polar}건")


if __name__ == "__main__":
    main()
