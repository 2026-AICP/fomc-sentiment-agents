-- FOMC 감성분석 멀티에이전트 — 데이터 스키마 (단일 진실 소스)
-- 모든 단계는 이 4개 표만 읽고 쓴다.

-- ① 수집한 원문 장부 (출처 추적)
CREATE TABLE IF NOT EXISTS documents (
    doc_id     TEXT PRIMARY KEY,   -- 문서 고유번호 (예: 2025-01-29_statement)
    date       TEXT NOT NULL,      -- 회의/발표 날짜 (YYYY-MM-DD)
    doc_type   TEXT NOT NULL,      -- statement | minutes
    source_url TEXT,               -- 원본 주소
    sha        TEXT,               -- 내용 해시 (중복 판별)
    fetched_at TEXT                -- 수집 시각 (ISO)
);

-- ② 문장별 감성 점수 (핵심)
CREATE TABLE IF NOT EXISTS sentences (
    id           TEXT PRIMARY KEY,  -- 문장 고유번호 (doc_id#idx#model_tag) → 재실행 멱등
    date         TEXT NOT NULL,
    doc_id       TEXT NOT NULL REFERENCES documents(doc_id),
    doc_type     TEXT,
    section      TEXT,
    sentence_idx INTEGER,           -- 문서 내 문장 순번
    sentence     TEXT NOT NULL,
    p_pos        REAL,              -- 긍정 확률
    p_neu        REAL,              -- 중립 확률
    p_neg        REAL,              -- 부정 확률 (합 = 1)
    score        REAL,              -- p_pos - p_neg
    entropy      REAL,              -- 불확실성 (>= 0)
    model_tag    TEXT NOT NULL      -- 어느 모델 결과인지 (dummy / finbert-base ...)
);

-- ③ 회의별 최종 인덱스 (방식·단위별로 동시 보관)
CREATE TABLE IF NOT EXISTS meetings (
    date        TEXT NOT NULL,
    method      TEXT NOT NULL,      -- label_avg | conf_weighted
    granularity TEXT NOT NULL,      -- meeting | month | quarter
    index_value REAL,
    confidence  REAL,
    PRIMARY KEY (date, method, granularity)
);

-- ④ 시장 데이터 (ET 거래일 기준)
CREATE TABLE IF NOT EXISTS market (
    date       TEXT PRIMARY KEY,    -- ET 거래일
    spx_close  REAL,
    spx_ret_cc REAL,                -- 종가-종가 수익률
    vix        REAL,
    vix_chg    REAL,
    ust2y      REAL,
    ust10y     REAL
);
