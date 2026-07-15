"""presser 4인 라벨 병합 → 정답지 (합의 + 불일치 final) + kappa 보고.

성명문 merge_labels 와 동일 로직, presser 파일용. 일치=그 라벨(agree),
불일치=불일치파일 final(resolved). 불일치 final은 팀 확정 or 잠정(제안).
출력: data/labeling/ground_truth_presser_150.csv (id,label_code,label,source).

실행: python3 analysis/merge_presser_labels.py
"""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LBL = ROOT / "data" / "labeling"                     # 팀 presser 라벨(repo)
DIS = Path("/Users/jaewon/Desktop/'26 UNIST/활동/AICP/Agent/labeling/presser")  # 불일치(final 채움)
OUT = ROOT / "data" / "labeling" / "ground_truth_presser_150.csv"
NAME = {"0": "neutral", "1": "positive", "2": "negative"}

PAIRS = [
    ("1-75", "label_배재원 (1-75).csv", "label_최인영 (1-75).csv", "불일치_1-75_배재원_최인영.csv"),
    ("76-150", "label_김형준 (76-150).csv", "label_지현민 (76-150).csv", "불일치_76-150_김형준_지현민.csv"),
]


def rd(base, f):
    return list(csv.DictReader(open(base / f, encoding="utf-8-sig")))


def lab(r):
    return (r.get("label") or "").strip()


def kappa(a, b):
    """Cohen's kappa (성명문 merge_labels.kappa 와 동일 식). 두 라벨러 리스트 → (원일치율, κ)."""
    n, cats = len(a), ["0", "1", "2"]
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    final = []
    for rng, fa, fb, fd in PAIRS:
        ra = rd(LBL, fa)
        mb = {r["id"]: lab(r) for r in rd(LBL, fb)}
        resolve = {r["id"]: (r.get("final") or "").strip() for r in rd(DIS, fd)}
        la = [lab(r) for r in ra]           # 라벨러 A·B 원라벨(κ용, repo 내 파일만 사용)
        lb = [mb[r["id"]] for r in ra]
        po, k = kappa(la, lb)
        agree = resolved = 0
        for r in ra:
            a, b = lab(r), mb[r["id"]]
            if a == b:
                code, src = a, "agree"
                agree += 1
            else:
                code, src = resolve.get(r["id"], ""), "resolved"
                resolved += 1
            final.append({"id": r["id"], "label_code": code,
                          "label": NAME.get(code, "?"), "source": src})
        print(f"{rng}: 원일치 {po:.0%} · κ={k:.3f} · agree {agree} / resolved {resolved}")

    missing = [r["id"] for r in final if r["label_code"] not in NAME]
    if missing:
        print(f"⚠️ 라벨 누락 {len(missing)}건 (불일치 final 미기입?): {missing[:5]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "label_code", "label", "source"])
        w.writeheader()
        w.writerows(final)
    print(f"\npresser 정답지 {len(final)}개 → {OUT}")
    print("분포:", dict(Counter(r["label"] for r in final)),
          "· source:", dict(Counter(r["source"] for r in final)))


if __name__ == "__main__":
    main()
