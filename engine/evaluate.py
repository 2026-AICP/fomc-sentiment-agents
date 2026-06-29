"""감성 엔진 평가 (Phase 3 합격선 측정).

사람 라벨(정답)과 모델 예측을 비교해:
  1. 라벨러 간 일치율 + Cohen's kappa (정답지 신뢰도)
  2. 불일치 문장 목록 (짝끼리 토론용) → disagreements.csv
  3. Macro-F1 / 정확도 / 혼동행렬          (모델 정확도, Phase 3 합격선)
  4. ECE (캘리브레이션)                     (모델 확신도가 정직한가)
  5. 엔트로피 오류 분석                      (틀린 문장이 고불확실성에 몰리나)

입력:
  --labels  사람 라벨 CSV들이 있는 폴더 (label_*.csv, 각 id,date,sentence,label)
  --key     모델 예측 CSV (id, model_pred, p_pos, p_neu, p_neg, entropy)
  --final   (선택) 토론으로 확정된 최종 라벨 CSV (id, label) — 있으면 이걸 정답으로 사용

사용:
  python3 engine/evaluate.py --labels ~/Downloads/labeling --key ~/Downloads/labeling_key_model_pred.csv
의존성: 표준 라이브러리만 (sklearn 불필요).
"""
import argparse
import csv
import glob
import math
import os
from collections import Counter, defaultdict

CLASSES = ["positive", "neutral", "negative"]
# 라벨 코드 매핑 — 이번 프로젝트 규약: 0=중립, 1=긍정, 2=부정 (모델 라벨 순서와 동일)
_ALIASES = {
    "positive": "positive", "pos": "positive", "p": "positive", "1": "positive", "긍정": "positive",
    "neutral": "neutral", "neu": "neutral", "n": "neutral", "0": "neutral", "중립": "neutral",
    "negative": "negative", "neg": "negative", "2": "negative", "부정": "negative",
}


def norm(label):
    if label is None:
        return None
    k = str(label).strip().lower()
    return _ALIASES.get(k)


def load_key(path):
    key = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        key[r["id"]] = {
            "model_pred": norm(r["model_pred"]),
            "p_pos": float(r["p_pos"]), "p_neu": float(r["p_neu"]),
            "p_neg": float(r["p_neg"]), "entropy": float(r["entropy"]),
        }
    return key


def load_human_labels(folder):
    """label_*.csv 들을 읽어 id -> [라벨, ...] (라벨러 여러 명)."""
    by_id = defaultdict(list)
    files = sorted(glob.glob(os.path.join(folder, "label_*.csv")))
    for fp in files:
        for r in csv.DictReader(open(fp, encoding="utf-8-sig")):
            lab = norm(r.get("label"))
            if lab:
                by_id[r["id"]].append(lab)
    return by_id, files


def cohen_kappa(a, b):
    """두 라벨러 리스트(같은 순서) 간 Cohen's kappa."""
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in CLASSES)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def macro_f1(truth, pred):
    f1s = {}
    for c in CLASSES:
        tp = sum(1 for t, p in zip(truth, pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(truth, pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(truth, pred) if t == c and p != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s[c] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return sum(f1s.values()) / len(CLASSES), f1s


def confusion(truth, pred):
    m = {t: Counter() for t in CLASSES}
    for t, p in zip(truth, pred):
        m[t][p] += 1
    return m


def ece(confs, corrects, n_bins=10):
    """Expected Calibration Error."""
    N = len(confs)
    if N == 0:
        return float("nan")
    bins = [[] for _ in range(n_bins)]
    for c, ok in zip(confs, corrects):
        idx = min(int(c * n_bins), n_bins - 1)
        bins[idx].append((c, ok))
    e = 0.0
    for b in bins:
        if not b:
            continue
        acc = sum(1 for _, ok in b if ok) / len(b)
        conf = sum(c for c, _ in b) / len(b)
        e += abs(acc - conf) * len(b) / N
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, help="label_*.csv 폴더")
    ap.add_argument("--key", required=True, help="모델 예측 CSV")
    ap.add_argument("--final", help="(선택) 확정 최종 라벨 CSV (id,label)")
    ap.add_argument("--out", default=".", help="결과 저장 폴더")
    args = ap.parse_args()

    key = load_key(args.key)
    by_id, files = load_human_labels(args.labels)
    print(f"모델 예측 {len(key)}건 | 라벨 파일 {len(files)}개 | 라벨된 문장 {len(by_id)}건\n")

    # ── 1. 라벨러 간 일치율 ──
    paired = {i: labs for i, labs in by_id.items() if len(labs) >= 2}
    if paired:
        a = [labs[0] for labs in paired.values()]
        b = [labs[1] for labs in paired.values()]
        agree = sum(1 for x, y in zip(a, b) if x == y) / len(a)
        print("【1】 라벨러 간 신뢰도 (2명 이상 매긴 문장 %d건)" % len(paired))
        print(f"  일치율: {agree*100:.1f}%   Cohen's kappa: {cohen_kappa(a,b):.3f}")
        print("  (kappa 0.6+ 양호, 0.8+ 우수)\n")

    # ── 2. 불일치 → 토론 목록 ──
    disagree = {i: labs for i, labs in paired.items() if len(set(labs)) > 1}
    dpath = os.path.join(args.out, "disagreements.csv")
    with open(dpath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["id", "labels", "final"])
        for i, labs in disagree.items():
            w.writerow([i, " / ".join(labs), ""])
    print(f"【2】 불일치 {len(disagree)}건 → {dpath} (짝끼리 토론해 final 채우기)\n")

    # ── 정답(ground truth) 결정 ──
    if args.final:
        truth = {r["id"]: norm(r["label"])
                 for r in csv.DictReader(open(args.final, encoding="utf-8-sig")) if norm(r.get("label"))}
        print(f"최종 라벨 {len(truth)}건 사용 (--final)\n")
    else:
        # 합의된 것만 사용 (불일치는 제외)
        truth = {i: labs[0] for i, labs in paired.items() if len(set(labs)) == 1}
        print(f"합의된 {len(truth)}건만 평가 (불일치 {len(disagree)}건 제외, 토론 후 --final 로 재실행 권장)\n")

    # 모델 예측과 매칭
    ids = [i for i in truth if i in key]
    t = [truth[i] for i in ids]
    p = [key[i]["model_pred"] for i in ids]
    if not ids:
        print("평가할 문장이 없습니다 (라벨이 비어있는 듯). 라벨 채운 뒤 다시 실행하세요.")
        return

    # ── 3. F1 / 정확도 / 혼동행렬 ──
    mf1, f1s = macro_f1(t, p)
    acc = sum(1 for x, y in zip(t, p) if x == y) / len(t)
    print(f"【3】 정확도 (정답 {len(t)}건)")
    print(f"  Macro-F1: {mf1:.3f}   정확도: {acc:.3f}")
    print("  클래스별 F1: " + ", ".join(f"{c} {f1s[c]:.2f}" for c in CLASSES))
    cm = confusion(t, p)
    print("  혼동행렬 (행=정답, 열=모델예측):")
    print("           " + "".join(f"{c[:3]:>8}" for c in CLASSES))
    for tr in CLASSES:
        print(f"    {tr[:3]:>5}  " + "".join(f"{cm[tr][pr]:>8}" for pr in CLASSES))
    print()

    # ── 4. ECE ──
    confs = [max(key[i]["p_pos"], key[i]["p_neu"], key[i]["p_neg"]) for i in ids]
    corrects = [x == y for x, y in zip(t, p)]
    print(f"【4】 캘리브레이션")
    print(f"  ECE: {ece(confs, corrects):.3f}  (0에 가까울수록 확신도가 정직, 0.1 미만 양호)\n")

    # ── 5. 엔트로피 오류 분석 ──
    ents = [(i, key[i]["entropy"], ok) for i, ok in zip(ids, corrects)]
    med = sorted(e for _, e, _ in ents)[len(ents) // 2]
    lo = [ok for _, e, ok in ents if e <= med]
    hi = [ok for _, e, ok in ents if e > med]
    print("【5】 엔트로피(불확실성) 오류 분석")
    if lo:
        print(f"  저불확실성(엔트로피≤{med:.2f}) 정확도: {sum(lo)/len(lo):.3f} ({len(lo)}건)")
    if hi:
        print(f"  고불확실성(엔트로피>{med:.2f}) 정확도: {sum(hi)/len(hi):.3f} ({len(hi)}건)")
    print("  → 고불확실성에서 정확도가 낮으면, 엔트로피가 '모델이 헷갈린 곳'을 잘 잡는다는 뜻")

    # 결과 저장
    rpath = os.path.join(args.out, "eval_per_sentence.csv")
    with open(rpath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["id", "truth", "model_pred", "correct", "confidence", "entropy"])
        for i in ids:
            w.writerow([i, truth[i], key[i]["model_pred"], truth[i] == key[i]["model_pred"],
                        round(max(key[i]["p_pos"], key[i]["p_neu"], key[i]["p_neg"]), 3),
                        round(key[i]["entropy"], 3)])
    print(f"\n문장별 결과: {rpath}")


if __name__ == "__main__":
    main()
