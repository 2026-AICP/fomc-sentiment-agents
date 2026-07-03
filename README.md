# FOMC 감성분석 멀티에이전트

FOMC 성명문(Fed 축)과 경제·통화정책 뉴스(News 축)를 감성 분석해
News & Fed Sentiment Index를 산출하고, S&P500·VIX 등 시장 지표와 비교해
위험·기회 신호와 보고서를 자동 생성하는 멀티에이전트 시스템. (2026-AICP 팀 연구)

## 출처
작년 프로젝트 [`Qsdg812/fomc---index`](https://github.com/Qsdg812/fomc---index)의
아이디어를 이어받아 새로 구축. 일부 전처리 로직을 참고함.

## 현재 상태
- **Phase 0~2** ✅ 스캐폴딩 + 더미 엔진 end-to-end
- **Phase 3** ✅ FinBERT 엔진 통합·검증·캘리브레이션 (`docs/phase3_evaluation.md`)
- **Phase 4** ✅ 인덱스 집계 방식 비교 + 보정 효과 (`docs/phase4_index.md`)
- **Phase 5** ✅ 시장 비교(S&P500·VIX) + 톤-반응 정합성 (`docs/phase5_comparison.md`)
- **Phase 6** ✅ 신호 규칙셋(A·B·C) + 백테스트 + 자동보고서 (`docs/phase6_signals.md`)
- **Phase 7** ✅ 멀티에이전트(LangGraph) — Collector→Fed·News분석→통합(headline)→Market→신호→보고서, 무인 batch 9/9 검증 (`docs/phase7_design.md`)
  - News 축: Marketaux 실시간 뉴스 스크래퍼 + 일별 News 지수(95% CI) + Fed와 통합(headline)

설계 문서는 `docs/` 참조: `phase7_design.md`(멀티에이전트), `news_fed_index.md`(News+Fed 통합), `signal_design.md`(신호 설계), `phase6_signals.md`, `phase3_evaluation.md`, `phase4_index.md`, `phase5_comparison.md`, `gpu_server.md`(GPU 서버).

## 구조
```
engine/    수집·전처리·감성엔진
  ├ sentiment.py      진짜 FinBERT 엔진 (확률·엔트로피·온도보정)
  ├ dummy_sentiment.py 더미 엔진 (테스트용)
  ├ scrape.py         FOMC 성명문 스크래퍼
  ├ news_scrape.py    Fed 뉴스 스크래퍼 (Marketaux)
  └ evaluate.py       감성 엔진 평가 (F1·ECE·혼동·엔트로피)
index/     인덱스 집계 (label_avg / conf_weighted 두 방식)
analysis/  시장 비교·신호·News 지수 (Phase 5·6·7)
  ├ collect_market.py, analyze_alignment.py  시장 수집·톤반응 정합
  ├ signals.py, backtest.py                  신호 A·B·C + 백테스트
  └ news_index_live.py, headline.py          라이브 News 지수(CI)·Fed 통합
reports/   보고서 생성 (감성분해·신호·News/통합)
agents/    멀티에이전트 (Phase 7) — graph.py: LangGraph 파이프라인 + Orchestrator
pipeline.py  함수 직선 연결 (에이전트 전 단계)
schema.sql   데이터 스키마 (단일 진실 소스)
docs/      설계·평가 문서
tests/     검증 + 고정 픽스처
```

## 셋업

**1. 의존성 설치**
```bash
pip install -r requirements.txt    # 감성엔진엔 transformers, torch 필요
```

**2. 모델 배치 (★중요 — git 에 없음)**
파인튜닝 FinBERT 모델(419MB)은 용량 때문에 git 에 포함하지 않는다.
**드롭박스에서 받아** 아래 경로에 둔다:
```
models/finbert-finetuned/
  ├ config.json
  ├ pytorch_model.bin
  ├ vocab.txt
  └ tokenizer*.json, special_tokens_map.json
```
(다른 위치에 두려면 환경변수 `FINBERT_MODEL_DIR` 로 경로 지정)

## 실행
```bash
# 더미 엔진 (기본, 모델 불필요 — 배관 테스트용)
python3 pipeline.py

# 진짜 FinBERT 엔진 (모델 필요)
SENTIMENT_ENGINE=finbert python3 pipeline.py

# 멀티에이전트 (Phase 7) — 단건 / 무인 다건
SENTIMENT_ENGINE=finbert python3 agents/graph.py 2026-06-17
SENTIMENT_ENGINE=finbert python3 agents/graph.py --batch

# News 축 — 뉴스 수집(.newsapi_key 필요) / 일별 News 지수(+CI)
python3 engine/news_scrape.py
python3 analysis/news_index_live.py

# 테스트 (오프라인, 더미 기준)
python3 -m pytest
```
※ Windows 는 `python3` 대신 `py` 사용.

## 엔진 설정 (환경변수)
| 변수 | 기본값 | 설명 |
|---|---|---|
| `SENTIMENT_ENGINE` | `dummy` | `finbert` 면 진짜 엔진 |
| `FINBERT_MODEL_DIR` | `models/finbert-finetuned` | 모델 경로 |
| `FINBERT_TEMPERATURE` | `3.1` | 온도 보정(캘리브레이션). `1.0` 이면 베이스라인 |
| `NEWS_API_KEY` | (`.newsapi_key` 파일) | Marketaux 키. 코드·git 에 넣지 말 것(각자 발급) |
| `NEWS_WINDOW_BEFORE`/`AFTER` | `3`/`1` | 발표일 전후 뉴스 창(일) |

라벨 규약: **0=중립, 1=긍정, 2=부정** (모델·평가 전체 공통).

## 데이터 스키마
`schema.sql` 참조. 표 4종: `documents`, `sentences`, `meetings`, `market`.
모든 모듈은 이 4개 표만 읽고 쓴다. 스키마 변경은 팀 합의 필요.

## 협업
- 작은 변경(문서·독립 파일·핫픽스)은 `main` 직접 커밋 OK. **공유 모듈·스키마·큰 리팩터는 브랜치(`feat/...`) → PR → 리뷰 후 머지.**
- 커밋 전 `git pull` 로 최신화. 동시 작업이 많아지면 브랜치/PR 을 기본으로 전환.
- 모델 가중치·DB·생성물·API 키(`.newsapi_key`)는 git 에 올리지 않음 (`.gitignore` 참조).

## 라이선스
MIT (`LICENSE` 참조).
