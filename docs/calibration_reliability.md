# FinBERT 온도보정(T=3.1) 방어 — reliability diagram + 엔트로피 분포

> 확신도 가중(conf_weighted) 지수가 정직하려면, 모델 확신도가 실제 정확도와 맞아야 한다.
> 온도 스케일링(T=3.1)이 과신을 교정함을 **라벨 300문장(성명문 150 + presser 150)**으로 시각·정량 입증.
> 코드: `analysis/reliability_diagram.py` · 그림: `docs/figures/calibration/`

## 1. 방법 (정직한 계산)

- **라벨 (총 300문장 · 4인 독립 2조 + 합의)** — `data/labeling/ground_truth_{statement,presser}_150.csv`
  - **성명문 150** (DB 텍스트 매칭 **143**): Cohen's κ = **0.43** (1–75) · **0.65** (76–150) — 문어체, 보통~양호. 독립 재라벨이 이전 정답지와 150/150 일치 → 재현성 확인.
  - **presser 150** (기자회견 의장 발언): Cohen's κ = **0.24** (1–75) · **0.54** (76–150) — 구어체 Q&A라 성명문보다 라벨러 합의가 낮음(헤지·애매 多). 병합 = agree 99 / resolved 51. 라벨 분포 **중립 112 / 긍정 24 / 부정 14**(중립 다수).
  - 합의 규칙: 2인 일치→그 라벨(agree), 불일치→확정(resolved). 성명문 resolved는 팀 토론, **presser resolved 51건은 규칙기반 AI 제안을 팀이 문장별 검토·확정**(전 과정 repo 공개: `data/labeling/불일치_검토_presser.csv` — AI제안·사유·확정). `analysis/merge_labels.py` · `analysis/merge_presser_labels.py`.
- **모델 통과 → raw logits → T=1·T=3.1 softmax 직접 산출** (양쪽 일관, 한 번의 추론)
- 확신도 = max(prob), 정확도 = (argmax == 사람 라벨). ECE = 확신도 구간별 |정확도−확신도| 가중평균

## 2. 결과

| 지표 | 성명문 raw(T=1) | 성명문 보정(T=3.1) | presser raw(T=1) | presser 보정(T=3.1) |
|---|---|---|---|---|
| **ECE** (0=정직) | **0.294** | **0.112** | **0.130** | **0.116** |
| 엔트로피 평균 | 0.24 (거짓 확신) | 0.79 (정직) | 0.24 | 0.81 |
| 정확도(argmax) | 63.6% | 63.6% | 78.0% | 78.0% |

(엔트로피 최대 = ln3 ≈ 1.10. 정확도는 보정에 불변 — 온도는 확신도만 바꾸고 argmax는 그대로.)
그림: `reliability_diagram_{statement,presser}.png` · `entropy_distribution_{statement,presser}.png`.

## 3. 해석 (포스터 문장)

**① 성명문 — 과신을 T=3.1이 교정.** raw 모델은 **확신 99%인데 실제 정확도 ~67%**(대각선 한참 아래 = 과신).
T=3.1 보정 후 곡선이 **대각선에 근접**해 "확신도 = 실제 맞을 확률"이 정직해짐 (ECE 0.294 → 0.112, **62% 감소**).
엔트로피도 0 근처 peaky(거짓 확신) → 넓게 퍼짐(정직, 0.24 → 0.79).

**② presser — 구어체에서도 T=3.1이 정직성을 유지.** 기자회견 문장은 **raw부터 이미 정직**(ECE 0.130, 성명문 0.294보다 훨씬 낮음 = 모델이 구어체엔 애초에 과신을 덜 함).
T=3.1 적용 시 **0.116으로 유지·소폭 개선**(안 깨짐) → 성명문에서 고른 **한 온도값이 문어체·구어체 두 문체 모두에서 정직**함을 확인(일반화). 엔트로피도 0.24 → 0.81로 성명문과 같은 방향.

**③ 왜 중요한가.** 이 엔트로피가 conf_weighted 지수의 가중치라, **보정 없이는 불확실한 문장도 과대 가중**되어 지수가 왜곡됨 → **T=3.1이 지수 정직성의 전제**. 두 텍스트 유형 모두에서 성립하므로 통합 지수(Fed·News·presser)에 **동일 온도로 일관 적용** 가능.

## 4. 한계 · 다음

- **presser 정확도(78.0%)는 중립 다수(112/150) 영향** — 다수클래스만 찍어도 높게 나올 수 있어, presser는 정확도보다 **ECE·엔트로피(캘리브레이션)** 로 해석. 1–75 조는 κ=0.24로 낮아(구어체 애매), 개별 라벨보다 **집계·보정 관점**이 안전.
- **presser resolved 51건은 확정 완료** — 규칙기반 AI 제안 → 팀 문장별 검토·확정(`불일치_검토_presser.csv`에 AI제안·사유·확정 전부 공개, 재현 가능). AI 제안은 **FinBERT 점수 미참조**(문장 뜻만)로 평가 대상 모델과 독립.
- ECE는 각 150개 **in-sample** 값. 성명문 2-fold CV(0.07~0.10) 같은 홀드아웃 검증이 다음 개선 방향.
- 재현: `python3 analysis/reliability_diagram.py statement` · `python3 analysis/reliability_diagram.py presser`
  (κ 재계산: `python3 analysis/merge_labels.py` · `python3 analysis/merge_presser_labels.py`)
