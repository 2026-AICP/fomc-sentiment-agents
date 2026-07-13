"""presser 감성 라벨링 시트 생성 — 4의장 골고루 무작위 표본.

성명문 150개(labeling_ground_truth_150.csv)와 짝이 되는 presser 라벨셋 구축용.
의장 발언(data/pressers/*.txt)에서 대표 표본을 뽑아 **빈 라벨칸** 시트를 만든다.
라벨러 2명이 각자 label_A/label_B 에 0(중립)/1(긍정)/2(부정)을 채우고 → kappa → 합의.

★대표성: 쉬운 문장만 고르지 않도록 무작위 표본(보정은 애매한 문장에서 시험됨).
  너무 짧은 조각·인사·전환구만 제외. 재현성 위해 seed 고정.

실행: python3 analysis/make_labeling_sheet.py [N=150] [out.csv]
"""
import csv
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESSER_DIR = ROOT / "data" / "pressers"
DEFAULT_OUT = ROOT / "data" / "labeling" / "presser_labeling_sheet_150.csv"

# 의장 재임(대략 — 표본 층화용). presser는 2011-04~ 존재.
def chair_of(date: str) -> str:
    if date <= "2014-01-31":
        return "Bernanke"
    if date <= "2018-02-03":
        return "Yellen"
    if date <= "2026-05-31":
        return "Powell"
    return "Warsh"


# 의장별 목표 문장수(다양성 확보). 부족하면 가능한 만큼 + 부족분은 최대 풀에서 보충.
TARGET = {"Bernanke": 30, "Yellen": 40, "Powell": 60, "Warsh": 20}

# 라벨 부적합(너무 짧음/인사/전환구) 제외 — 실질 문장만
_GREETING = re.compile(
    r"^(thank you|thanks|good (after|mor|even|day)|let me|i'?ll (turn|take|start)|"
    r"with that|as (always|usual)|i'?m (happy|glad)|hi\b|hello)", re.I)


def eligible(sent: str) -> bool:
    s = sent.strip()
    return len(s.split()) >= 7 and not _GREETING.match(s)


def collect_pool():
    """의장별 (date, idx, sentence) 후보 풀."""
    pool = {c: [] for c in TARGET}
    for f in sorted(PRESSER_DIR.glob("FOMC_presconf_*.txt")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        if not m:
            continue
        date = m.group(1)
        c = chair_of(date)
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            if eligible(line):
                pool[c].append((date, i, line.strip()))
    return pool


def sample_sheet(n_total=150, seed=42):
    rng = random.Random(seed)
    pool = collect_pool()
    scale = n_total / sum(TARGET.values())
    picks, used = [], set()
    for c, items in pool.items():
        k = min(len(items), round(TARGET[c] * scale))
        for t in rng.sample(items, k):
            used.add((t[0], t[1]))
            picks.append((c,) + t)
    if len(picks) < n_total:                       # 부족분은 남은 풀(주로 Powell)에서 보충
        rest = [(chair_of(d), d, i, s) for c in pool for (d, i, s) in pool[c]
                if (d, i) not in used]
        picks += rng.sample(rest, min(n_total - len(picks), len(rest)))
    rng.shuffle(picks)
    return picks


def split_parts(picks, n_parts, seed=42):
    """의장 균형 유지하며 n_parts 로 분할(문장 안 겹침). 각 파트는 앵커링 방지로 섞음."""
    by_chair = {}
    for p in picks:
        by_chair.setdefault(p[0], []).append(p)
    parts = [[] for _ in range(n_parts)]
    for items in by_chair.values():              # 의장별 라운드로빈 → 각 파트에 골고루
        for i, it in enumerate(items):
            parts[i % n_parts].append(it)
    for k, pt in enumerate(parts):
        random.Random(seed + k).shuffle(pt)      # 의장 섞기(앵커링 방지)
    return parts


def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp)
        w.writerow(["id", "chair", "sentence", "label_A", "label_B", "notes"])
        for c, date, idx, s in rows:
            w.writerow([f"{date}_presconf#{idx}", c, s, "", "", ""])


def main():
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    n_parts = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    outdir = DEFAULT_OUT.parent
    picks = sample_sheet(n_total)
    if n_parts <= 1:
        _write(outdir / f"presser_labeling_sheet_{n_total}.csv", picks)
        print(f"라벨링 시트 {len(picks)}문장 → presser_labeling_sheet_{n_total}.csv")
        print("의장별:", dict(Counter(c for c, *_ in picks)))
        return
    for k, pt in enumerate(split_parts(picks, n_parts), 1):
        _write(outdir / f"presser_labeling_part{k}_{len(pt)}.csv", pt)
        print(f"파트 {k}: {len(pt)}문장 → presser_labeling_part{k}_{len(pt)}.csv "
              f"| 의장별 {dict(Counter(c for c, *_ in pt))}")
    print(f"→ {n_parts}조가 각 파트를 맡음. 조 안에서 2명이 label_A·label_B 독립 라벨.")
    print("  파트끼리 문장 안 겹침(합치면 전체). 0(중립)/1(긍정)/2(부정).")


if __name__ == "__main__":
    main()
