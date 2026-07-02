# Phase 6 계획 — 규칙셋 + 백테스트 + 자동보고서

> 상태: 착수. 담당 이어받기. Phase 5(정합성 분석) 완료 위에서 진행.
> 근거 문서: `docs/signal_design.md`(신호 설계 초안), `docs/phase5_comparison.md`(정합성 결과).

---

## 0. 목표와 합격선

| 항목 | 내용 |
|---|---|
| 산출물 | ① 신호 규칙 엔진(A·B·C) ② 백테스트 하네스 ③ 자동보고서 |
| 합격선(가이드라인) | **신호 적중률 vs 단순보유(buy-and-hold)** — 벤치마크를 못 이기면 "신호 없음"이 정직한 결론 |
| 원칙 | 전부 **순수 함수**로 구현(에이전트화는 Phase 7). `signal_design.md`가 이미 신호 정의·검증법을 명세 → 코드로 실체화 |
| 철학(signal_design §1-A) | **예측 아님, 괴리·경향 알림.** 방향 예측 규칙 금지, 신뢰도·표본경고 동봉 필수 |

## 1. 데이터 준비 (백테스트 표본)

로컬 드롭박스 `AICP_EconPilot/`에서 확보 (2000–2021):
- 성명문 188건, 미닛츠 23건, WSJ 연도별 CSV, FinBERT 모델(`model/`).

배치 방침 — **"확인 후 공유"라 로컬 전용 유지**:
- 모델 → `models/finbert-finetuned/` (`.gitignore` 이미 제외).
- 성명문 대량본 → **gitignore되는 코퍼스 폴더**(예: `data/corpus/`)에 두고 파이프라인이 그곳을 읽게 함. 커밋되는 `tests/fixtures/` 6건은 오프라인 테스트용으로 유지.
- 실행: `SENTIMENT_ENGINE=finbert py pipeline.py` → 톤 산출 → `py analysis/collect_market.py` → `py analysis/analyze_alignment.py`.
- ⚠️ Phase 5 경고: `meetings`엔 `model_tag` 없음 → 더미 재실행 시 FinBERT 톤 덮어씀. 채운 뒤 `data/fomc_backup_finbertNN.db`로 백업.

## 2. 신호 규칙 엔진 — `analysis/signals.py` (신규)

`signal_design.md §3`의 3종을 **순수 함수**로. 임계값 θ는 `configs/settings.yaml`에서 주입(잠정값, 데이터로 보정).

```
signal_tone_shift(prev_tone, tone, theta=0.2)      # A: |Δ톤| ≥ θ → 🔼/🔽
signal_divergence(tone, reaction_ret, theta_t, theta_m)  # B ⭐: 부호불일치 + 크기조건
signal_tone_vs_vix(tone, vix_chg, ...)             # C: 톤-VIX 동행 이탈
grade(signals, confidence) -> Alert                # 종합 🟢정합·⚪중립·⚠️주의·🔴경고 + 신뢰도
```

- 조립부 `build_meeting_signals(conn, ...)`: `meetings`(톤·confidence)+`market`(반응·vix_chg) 회의별 join(`analyze_alignment.py`의 `get_meeting_tone`/`get_reaction` 재사용) → 회의별 Alert 리스트.
- 국면(regime) 고려(§1-A): 긴축/완화 태그(연도/금리 방향 기반)를 붙여 해석. 고정 예측규칙 금지. 표본 부족 → "경향"으로만.
- 신뢰도: 각 Alert에 회의 confidence + "과거 유사 N건 중 X건" + 표본경고 동봉(§5).

## 3. 백테스트 하네스 — `analysis/backtest.py` (신규) ★합격선 핵심

방향예측이 아니므로 "적중"을 **위험사건**으로 조작적 정의.

- **신호기간 N = 2거래일** (발표시각 반영, 이벤트 인과 유지).
- **위험사건 = 발표 후 N일 내 최대낙폭(max drawdown)이 전체 회의 상위 tertile**(주지표). `|누적수익률|`(방식 A)은 보조로 함께 산출. 상대순위라 시대별 변동성 자동보정.
- **적중률** = P(위험사건 | 신호발동), **Wilson 신뢰구간 + 표본 수** 병기.
- **벤치마크(§4)**:
  1. 단순보유(buy-and-hold) — 누적수익·최대낙폭·Sharpe 기준선 + 위험사건 기저율(≈33%).
  2. 금리결정만 — 톤 없이 인상/동결/인하만으로 낸 신호(톤이 금리 너머 정보 주나).
  3. 무작위 신호 — 같은 발동빈도 랜덤, 몬테카를로 다수 시행 → 적중률 분포.
- **간단 룰전략 vs 단순보유**: 🔴 괴리경고 시 N일 현금화 규칙의 {누적수익·최대낙폭·Sharpe}를 buy-and-hold·랜덤과 비교.
- **정직성 장치**: CI가 랜덤 분포와 겹치면 "신호 없음" 보고. 국면별(긴축/완화) 분리. 표본 N 항상 명시.

## 4. 자동보고서 — `reports/report.py` 확장

- 회의별 알림 카드(§6 형식): 톤·직전대비·시장·신호등급·참고(표본경고·면책).
- 백테스트 요약 섹션: 신호별 적중률+CI, 벤치마크 대비 표, 국면별 분리, 한계·면책(§7) 자동 삽입.
- "수치는 DB 직인용(환각 차단)" 원칙 유지.

## 5. 테스트 — `tests/test_signals.py`, `tests/test_backtest.py` (신규)

- 신호 함수: 경계값·부호·임계값 단위테스트(네트워크·모델 의존 0, 결정적).
- 백테스트: 합성 데이터로 적중률·벤치마크·CI 로직 검증.
- 기존 `test_pipeline.py`와 함께 `py -m pytest` 오프라인 통과.

## 6. 문서 — `docs/phase6_signals.md` (신규)

임계값 최종값, 백테스트 결과(표본 수·CI), 국면별 결과, 한계·면책. README "현재 상태" 갱신(Phase 6 ✅).

## 7. 확정 기본값

| 항목 | 값 | 비고 |
|---|---|---|
| 신호기간 N | 2거래일 | signal_design 잠정값과 일치 |
| 위험사건 주지표 | 최대낙폭(상위 tertile) | \|수익률\| 보조 병기 |
| θ_shift | 0.2 (잠정) | 데이터 분포로 보정 |
| θ_t, θ_m | 분포 확인 후 결정 | |
| 국면 태그 | 연도/금리 방향 기반 | 택1 확정 예정 |

## 8. 작업 순서

```
1) feat/phase6-signals 브랜치 생성        ✅
2) analysis/signals.py + tests/test_signals.py   (순수함수 — 데이터 불필요)
3) analysis/backtest.py + tests/test_backtest.py (합성데이터 검증)
4) 데이터 준비(드롭박스) → 실데이터 백테스트 수치 산출
5) reports/report.py 확장 (알림카드 + 백테스트 요약)
6) docs/phase6_signals.md + README 갱신
7) PR
```
