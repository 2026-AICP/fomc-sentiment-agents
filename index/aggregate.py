"""문장 감성 → 회의 인덱스 집계.

두 방식을 동시에 산출해 meetings 표에 저장 (Phase 4 비교의 전제):
  - label_avg     : argmax 라벨(-1/0/1) 평균 (작년 방식)
  - conf_weighted : score를 확신도(1 - 정규화 엔트로피)로 가중 평균 (새 방식)
"""
import math
from typing import List, Tuple

LN3 = math.log(3)  # 3클래스 최대 엔트로피 (정규화용)


def aggregate_meeting(conn, date: str, model_tag: str) -> List[Tuple]:
    rows = conn.execute(
        "SELECT score, entropy, p_pos, p_neu, p_neg "
        "FROM sentences WHERE date = ? AND model_tag = ?",
        (date, model_tag),
    ).fetchall()
    if not rows:
        return []

    # label_avg
    labels = []
    for _score, _ent, p_pos, p_neu, p_neg in rows:
        m = max(p_pos, p_neu, p_neg)
        labels.append(1 if m == p_pos else (-1 if m == p_neg else 0))
    label_avg = sum(labels) / len(labels)

    # conf_weighted
    scores = [r[0] for r in rows]
    weights = [max(0.0, 1.0 - r[1] / LN3) for r in rows]
    wsum = sum(weights) or 1.0
    conf_weighted = sum(s * w for s, w in zip(scores, weights)) / wsum
    confidence = wsum / len(weights)

    return [
        (date, "label_avg", "meeting", label_avg, confidence),
        (date, "conf_weighted", "meeting", conf_weighted, confidence),
    ]
