"""신뢰도 곡선(reliability diagram) + 엔트로피 분포 — FinBERT 온도보정(T) 방어.

라벨된 문장에서 모델 **확신도(max prob) vs 실제 정확도**를 비교:
  · raw(T=1)  → 과신(곡선이 대각선 아래, ECE 큼)
  · 보정(T=3.1) → 대각선 근접(ECE 작음) = 확신도가 정직
엔트로피 분포도 raw는 0 근처 peaky(과신), 보정은 퍼짐(정직한 불확실성).

정직한 계산: 라벨 문장을 모델에 통과 → **raw logits** → T=1·T=3.1 softmax 직접 산출(양쪽 일관).
성명문 라벨 150개로 baseline. presser 라벨 완성 후 같은 스크립트 재실행(LABELS만 교체).

실행: python3 analysis/reliability_diagram.py
산출: reliability_diagram.png, entropy_distribution.png (FIGDIR)
"""
import csv
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "fomc.db"
# 성명문 정답지 — 팀 4인 독립 라벨 + 합의(merge_labels.py, κ=0.43/0.65, 원본 100% 재현)
LABELS = ROOT / "data" / "labeling" / "ground_truth_statement_150.csv"
FIGDIR = ROOT / "docs" / "figures" / "calibration"     # 레포 내 (팀 공유·포스터용)
T_RAW, T_CAL = 1.0, 3.1
NBINS = 10
# label_code = softmax 인덱스와 동일: 0=neutral, 1=positive, 2=negative (engine.sentiment 매핑)


def _presser_line(date, idx):
    """presser 문장 텍스트 — data/pressers/FOMC_presconf_{date}.txt 의 idx 번째 줄."""
    p = ROOT / "data" / "pressers" / f"FOMC_presconf_{date}.txt"
    if not p.exists():
        return None
    lines = p.read_text(encoding="utf-8").splitlines()
    return lines[idx] if 0 <= idx < len(lines) else None


def load_labeled(labels_path=None):
    """[(sentence, human_label_code), ...] — id 형식으로 소스 분기:
       _statement#N → DB(fomc.db) · _presconf#N → data/pressers/*.txt."""
    labels_path = labels_path or LABELS
    con = sqlite3.connect(DB)
    out = []
    for r in csv.DictReader(open(labels_path, encoding="utf-8-sig")):
        code = (r.get("label_code") or "").strip()
        if code not in ("0", "1", "2"):
            continue
        ms = re.match(r"(\d{4}-\d{2}-\d{2})_statement#(\d+)", r["id"])
        mp = re.match(r"(\d{4}-\d{2}-\d{2})_presconf#(\d+)", r["id"])
        sent = None
        if ms:
            row = con.execute("SELECT sentence FROM sentences WHERE date=? AND sentence_idx=? LIMIT 1",
                              (ms.group(1), int(ms.group(2)))).fetchone()
            sent = row[0] if row else None
        elif mp:
            sent = _presser_line(mp.group(1), int(mp.group(2)))
        if sent:
            out.append((sent, int(code)))
    con.close()
    return out


def model_logits(sentences):
    """문장들 → raw logits 행렬 (온도 적용 전)."""
    from engine.sentiment import _load
    tok, model, torch, device = _load()
    rows = []
    for s in sentences:
        inp = tok(s, return_tensors="pt", truncation=True, max_length=256).to(device)
        with torch.no_grad():
            rows.append(model(**inp).logits[0].cpu().numpy())
    return np.array(rows)


def softmax(logits, T):
    z = logits / T
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def reliability(probs, labels, nbins=NBINS):
    """확신도 구간별 (평균확신도, 정확도, 표본수) + ECE."""
    pred, conf = probs.argmax(1), probs.max(1)
    correct = (pred == labels).astype(float)
    bin_id = np.clip((conf * nbins).astype(int), 0, nbins - 1)
    xs, ys, cnts, ece, n = [], [], [], 0.0, len(labels)
    for i in range(nbins):
        m = bin_id == i
        if m.sum():
            acc, cf = correct[m].mean(), conf[m].mean()
            xs.append(cf)
            ys.append(acc)
            cnts.append(int(m.sum()))
            ece += (m.sum() / n) * abs(acc - cf)
    return np.array(xs), np.array(ys), np.array(cnts), ece


def entropy(probs):
    return -(probs * np.log(probs + 1e-12)).sum(1)


def make_figures(labels, p_raw, p_cal, tag="statement"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x1, y1, c1, e1 = reliability(p_raw, labels)
    x3, y3, c3, e3 = reliability(p_cal, labels)
    FIGDIR.mkdir(parents=True, exist_ok=True)

    # ── Fig 1: reliability diagram (마커 크기 ∝ 표본수) ──
    from matplotlib.lines import Line2D
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "--", color="#888", lw=1.3)
    ax.plot(x1, y1, "-", color="#ef4d4d", lw=1, alpha=0.35)
    ax.scatter(x1, y1, s=c1 * 14 + 15, color="#ef4d4d", alpha=0.85, zorder=3,
               edgecolor="white", linewidth=0.6)
    ax.plot(x3, y3, "-", color="#2dd4a0", lw=1, alpha=0.35)
    ax.scatter(x3, y3, s=c3 * 14 + 15, color="#2dd4a0", marker="s", alpha=0.85, zorder=3,
               edgecolor="white", linewidth=0.6)
    ax.set_xlabel("Predicted confidence (max prob)")
    ax.set_ylabel("Actual accuracy")
    ax.set_title(f"Reliability Diagram — {tag} ({len(labels)} sentences)")
    ax.text(0.98, 0.03, "marker size ∝ #sentences in bin\nbelow diagonal = overconfident",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#555",
            bbox=dict(boxstyle="round", fc="white", ec="#ccc", alpha=0.8))
    ax.set_xlim(0.3, 1.0)
    ax.set_ylim(0, 1.0)
    handles = [Line2D([0], [0], ls="--", color="#888", label="Perfect calibration"),
               Line2D([0], [0], marker="o", color="#ef4d4d", ls="", ms=9,
                      label=f"Raw (T=1)  ECE={e1:.3f}"),
               Line2D([0], [0], marker="s", color="#2dd4a0", ls="", ms=9,
                      label=f"Calibrated (T=3.1)  ECE={e3:.3f}")]
    ax.legend(handles=handles, loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    f1 = FIGDIR / f"reliability_diagram_{tag}.png"
    fig.savefig(f1, dpi=150)
    plt.close(fig)

    # ── Fig 2: entropy distribution ──
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    bins = np.linspace(0, np.log(3), 26)
    ax.hist(entropy(p_raw), bins=bins, alpha=0.6, color="#ef4d4d",
            label=f"Raw (T=1), mean={entropy(p_raw).mean():.2f}")
    ax.hist(entropy(p_cal), bins=bins, alpha=0.6, color="#4a90e2",
            label=f"Calibrated (T=3.1), mean={entropy(p_cal).mean():.2f}")
    ax.axvline(np.log(3), color="#888", ls=":", lw=1, label="Max entropy (ln3)")
    ax.set_xlabel("Prediction entropy (uncertainty)")
    ax.set_ylabel("Sentence count")
    ax.set_title(f"Entropy Distribution — {tag}")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    f2 = FIGDIR / f"entropy_distribution_{tag}.png"
    fig.savefig(f2, dpi=150)
    plt.close(fig)
    return e1, e3, f1, f2


GT = {"statement": ROOT / "data" / "labeling" / "ground_truth_statement_150.csv",
      "presser": ROOT / "data" / "labeling" / "ground_truth_presser_150.csv"}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "statement"
    data = load_labeled(GT.get(tag, LABELS))
    print(f"[{tag}] 라벨 문장 {len(data)}개 로드")
    sents = [s for s, _ in data]
    labels = np.array([l for _, l in data])
    logits = model_logits(sents)
    p_raw, p_cal = softmax(logits, T_RAW), softmax(logits, T_CAL)

    acc = (p_cal.argmax(1) == labels).mean()
    e1, e3, f1, f2 = make_figures(labels, p_raw, p_cal, tag)
    print(f"\n── 결과 ({tag}) ──")
    print(f"  정확도(argmax vs 사람): {acc:.1%}")
    print(f"  ECE:  raw(T=1) {e1:.3f}  →  보정(T=3.1) {e3:.3f}   (0에 가까울수록 정직)")
    print(f"  엔트로피 평균:  raw {entropy(p_raw).mean():.2f}  →  보정 {entropy(p_cal).mean():.2f} (최대 {np.log(3):.2f})")
    print(f"  그림: {f1.name}, {f2.name}\n  → {FIGDIR}")


if __name__ == "__main__":
    main()
