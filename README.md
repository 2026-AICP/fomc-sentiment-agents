# FOMC 감성분석 멀티에이전트

FOMC 성명문·의사록을 문장 단위로 감성 분석하여 News & Fed Sentiment Index를 산출하고,
S&P500·VIX 등 시장 지표와 비교해 위험·기회 신호와 보고서를 자동 생성하는
멀티에이전트 시스템. (2026-AICP 팀 연구)

## 출처
작년 프로젝트 [`Qsdg812/fomc---index`](https://github.com/Qsdg812/fomc---index)의
아이디어를 이어받아 새로 구축. 일부 전처리 로직을 참고함.

## 현재 상태: Phase 0~2 (Thin-Slice)
더미 감성 엔진으로 파이프라인을 끝까지 1회 관통시켜 배관(경로·DB·I/O)을 검증하는 단계.
진짜 FinBERT·시장 비교·멀티에이전트는 이후 Phase에서 추가.

## 구조
```
engine/    수집·전처리·감성엔진 (지금은 더미 + 스텁)
index/     인덱스 집계
analysis/  시장 비교 (Phase 5, 스텁)
reports/   보고서 생성
agents/    멀티에이전트 (Phase 7, 스텁)
pipeline.py  함수 직선 연결 (에이전트 전 단계)
schema.sql   데이터 스키마 (단일 진실 소스)
tests/     검증 + 고정 픽스처
```

## 실행 (Windows, py 런처)
```powershell
# 파이프라인 1회 실행 → reports/out/ 에 보고서 생성
py pipeline.py

# 테스트
py -m pytest
```

## 데이터 스키마
`schema.sql` 참조. 표 4종: `documents`, `sentences`, `meetings`, `market`.

## 라이선스
MIT (`LICENSE` 참조).
