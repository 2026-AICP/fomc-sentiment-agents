# presser 감성 라벨링 가이드

> `presser_labeling_sheet_150.csv` 의 150문장을 **긍정/부정/중립**으로 라벨링.
> 목적: FinBERT 온도보정(T)을 presser에서 재검증 → reliability diagram. (성명문 150개와 짝)

## 라벨 코드

| 코드 | 라벨 | 기준 (경제·전망에 대한 **톤**) |
|---|---|---|
| **1** | 긍정 | 낙관·자신·개선·강함 |
| **2** | 부정 | 우려·위험·약화·불확실 |
| **0** | 중립 | 사실·절차·균형·무색 |

**핵심 원칙:** 감성 = **낙관/비관**이지 **정책방향(인상/인하)이 아님.**
"금리 인하" 자체는 긍/부가 아니라, 그 문장의 **감정 톤**으로만 판단.

## 예시

- 🟢 **긍정(1)**: "The labor market remains strong." · "We've made good progress on inflation."
- 🔴 **부정(2)**: "Inflation remains elevated." · "There are downside risks to growth." · "The labor market has shown signs of softening."
- ⚪ **중립(0)**: "Policy is not on a preset course." · "The Committee decided to maintain the target range." · "We will continue to monitor the data."

## 애매할 때 규칙

1. **헤지**("some signs of softening") → 지배적 톤으로 (여기선 부정)
2. **조건문**("if inflation persists, we will act") → 대개 **중립**
3. **긍·부 혼재** → 더 강한 쪽. 진짜 반반이면 **중립**
4. 문장만 보고 애매하면 **중립**으로 (억지로 긍/부 만들지 말 것)

## 작성 방법

1. **라벨러 2명이 각자 독립적으로** `label_A`, `label_B` 칸에 0/1/2 기입
   - (혼자 하면 "주관"이 됨 — 최소 2명이어야 신뢰도 방어 가능)
2. 헷갈린 근거는 `notes` 에 메모 (선택)
3. 다 채우면 → 담당(재원)에게 전달 → **일치도(Cohen's kappa) 계산 + 불일치 문장 합의**
   - `agree`(둘 다 같음) / `resolved`(달라서 합의) 로 최종 확정
   - 기대 kappa 0.6+ (3-class 감성 기준 양호)

## 라벨링 후 (자동 처리)

성명문 150 + presser 150 → **T 재보정(2-fold CV)** → **reliability diagram**(성명문·presser 각각) → 포스터.

## 참고

- 시트 재생성: `python3 analysis/make_labeling_sheet.py` (seed 고정, 재현 가능)
- 문장은 `data/pressers/FOMC_presconf_{날짜}.txt` 의 의장 발언(기자 질문 제외됨)에서 표본
- id 형식: `{날짜}_presconf#{문장번호}` (성명문 `_statement#N` 과 대칭)
