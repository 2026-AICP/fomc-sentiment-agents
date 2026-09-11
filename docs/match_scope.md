# 뉴스 판정 범위 확대 — snippet·keywords 반영 보고

> 2026-09-05 작성 · 2026-09-08 갱신 · 뉴스 API 고도화
> 코드: `engine/news_scrape.py` (`MATCH_FIELDS`) · 커밋 `6ecc645`(main) `b7ecf08`(deploy)

## 요약

수집 건수가 늘지 않던 원인이 **회수가 아니라 필터**임을 확인했습니다.
기사 수를 늘리는 길이 둘 있습니다.

| 방안 | 최근 3일 통과 | 상태 |
|---|---|---|
| 9/8 이전 | 23건 | — |
| **①** 판정 텍스트 확대 | 42건 (+83%) | 적용 (9/8) |
| **②** M그룹 키워드 확장 | 39건 (+70%) | 적용 (9/10, 조교 승인) |
| **①+② (현재)** | **62건 (+170%)** | — |

**①은 지정해주신 키워드 세트를 한 글자도 바꾸지 않았습니다.** 그 단어를
*어디서 찾을지*만 넓혔습니다(Marketaux 가 주는데 안 읽던 텍스트). 되돌리기가
설정 한 줄이라 먼저 적용했습니다.

**②는 조교님 승인을 받아 2026-09-10 에 반영했습니다**(9절).
넓은 표현(tightening·easing·dovish·hawkish)은 이번에 제외했습니다.

근거는 기사 수가 아니라 **재현율**입니다 — 정책 기사가 헤드라인 표현 차이만으로
탈락하고 있었고(예: `Fed's Williams` 통과 대 `NY Fed's Williams` 탈락),
그것을 고친 결과로 기사 수가 따라 늘었습니다.

| 날짜 | 9/8 이전 | 현재 |
|---|---|---|
| 09-05 | 9 | 17 |
| 09-06 | **4** | 17 |
| 09-07 | 10 | 28 |

---

## 1. 배경 — 기사 수가 왜 안 늘었나

전수조사(Standard 티어) 전환 이후에도 대시보드 기사 수가 적은 날이 있었습니다.
2026-09-02(수)에는 9건이었습니다.

추적해보니 **수집은 정상**이었습니다.

| 날짜 | 회수 | 통과 | 탈락 | 통과율 |
|---|---|---|---|---|
| 08-28 (금) | 125 | 67 | 58 | 53.6% |
| 08-31 (월) | 229 | 56 | 173 | 24.5% |
| 09-01 (화) | 164 | 24 | 140 | 14.6% |
| **09-02 (수)** | **126** | **9** | **117** | **7.1%** |

그날 126건을 받아왔고 117건이 필터에서 탈락했습니다.
탈락분의 **77%**는 제목·설명에 F그룹도 M그룹도 없었습니다.
백필 5.5년치(탈락 279,018건)에서도 같은 비율(**79.4%**)이 나옵니다.

---

## 2. 발견 — 받고도 안 읽던 텍스트

Marketaux 응답에는 텍스트 필드가 셋 있는데, 저희는 하나만 쓰고 있었습니다.

| 필드 | 평균 길이 | 결측 | 기존 사용 |
|---|---|---|---|
| description | 203자 | 1% | 사용 |
| snippet | 162자 | **0%** | **미사용** |
| keywords | 82자 | 49% | **미사용** |

`snippet`은 코드상 폴백이었습니다.

```python
desc = a.get("description") or a.get("snippet") or ""
```

`description`이 없을 때만 쓰도록 되어 있는데 결측이 0%라
**한 번도 도달하지 않았습니다.** `keywords`는 아예 참조하지 않았습니다.

`snippet`은 `description`의 복사본이 아닙니다 —
표본 141건 중 **115건(82%)**이 앞 60자부터 내용이 다릅니다.

---

## 3. 실측 결과

2026-08-30 · 09-01 · 09-03 · 09-04 나흘, 회수 620건 기준입니다.

| 판정 범위 | 통과 | 증가 |
|---|---|---|
| 제목 + 설명 (기존) | 78 | — |
| + snippet | 95 | +17 |
| + keywords | 114 | +36 |
| **+ 둘 다 (현재)** | **128** | **+50 (+64%)** |

날짜별로도 일관됩니다.

| 날짜 | 회수 | 기존 | 확대 후 |
|---|---|---|---|
| 08-30 | 76 | 9 | 20 |
| 09-01 | 164 | 23 | 39 |
| 09-03 | 180 | 22 | 33 |
| 09-04 | 200 | 24 | 36 |

---

## 4. 무엇이 새로 들어오나 — 정밀도 맞교환

새로 통과한 50건을 모두 눈으로 확인했습니다. **절반은 명확한 정책 기사입니다.**

```
· What Warsh Referred to with "the Relatively Low Turnover in Today's Labor Market…"
· Stocks Rally, Yields Retreat after Waller Signals a September Hold
· U.S. Dollar Ticks Higher Amid Fed Rate Hike Expectations Following Nonfarm Payrolls
· Gold approaches two-week low on rising yields, Fed hike bets
· Europe's central bankers fear more turbulence in testy U.S. relations
```

**나머지 절반은 연준을 스치듯 언급하는 시장 논평입니다.**

```
· The 1-Minute Market Report, August 29, 2026 (NYSEARCA:VOO)
· Round number skirmishes
· Morning Bid: Bonds' reality check
· Mortgage rates hit highest level in over a year
· GDP data, crude oil prices, US jobs report to dictate market trends
```

증가분의 대부분(+36)을 만드는 **`keywords`가 더 느슨합니다.**
Marketaux가 자동 생성한 태그이기 때문입니다.
보수적으로 가려면 `snippet`만 넣는 선택지(+22%)가 있습니다.

---

## 5. 키워드 변경이 아닌 이유

지정해주신 F그룹·M그룹 27개 단어는 그대로입니다. 규칙도 F∧M 그대로입니다.
바뀐 것은 **탐색 범위**뿐입니다.

```
기존   제목 + 설명            에서 F∧M 을 찾는다
현재   제목 + 설명 + snippet + keywords 에서 F∧M 을 찾는다
```

## 6. 오히려 백본과의 불일치를 줄입니다

별도로 보고드린 **선정 범위 불일치**(`docs/scope_impact.md`)와 관련이 있습니다.

| | WSJ 백본 (2000~2021) | Marketaux 라이브 |
|---|---|---|
| 매칭 대상 | ProQuest가 **본문 전체** | 제목+설명 (기존) |
| 재필터 | 없음 | F∧M 재요구 |

백본은 **본문 전체**에서 F∧M을 찾았습니다.
라이브가 제목+설명만 본 것은 백본보다 **훨씬 좁은** 기준이었습니다.
`snippet`·`keywords`를 더하면 백본 쪽으로 가까워집니다.

같은 WSJ 자료에 라이브 규칙을 적용했을 때 17.4%만 남고
두 계열 지수의 상관이 r=0.43에 그쳤던 문제가 이 방향에서 조금 완화됩니다.
다만 **얼마나 완화되는지는 측정하지 않았습니다** — Marketaux에는 본문이 없어
백본과 완전히 같은 기준을 만들 수는 없습니다.

---

## 7. 바꾸지 않은 것 — 채점 경로

**FinBERT가 읽는 텍스트는 예전 그대로입니다.**

```
채점 텍스트 = description (20자 이하면 title)
```

`snippet`·`keywords`는 **관련성 판정에만** 쓰고 채점에는 넘기지 않습니다.
`analysis/news_index_live.load_live_news`가 두 필드를 참조하지 않음을
코드로 확인했고, 해당 파일은 이번 변경에서 수정하지 않았습니다.

교수님께서 학습·검증·평가를 마치신 모델과 파라미터에 영향이 없습니다.
지수 산출 방식(확신도 가중, 부트스트랩 CI)도 그대로입니다.

---

## 8. 되돌리기

코드 수정 없이 환경변수만으로 됩니다.

```bash
NEWS_MATCH_FIELDS="title,description"           # 예전 동작으로 복귀
NEWS_MATCH_FIELDS="title,description,snippet"   # 보수안
```

같은 63건 표본에서 단계별 복귀를 검증했습니다.

| 설정 | 통과 |
|---|---|
| 제목+설명 | 44 |
| +snippet | 50 |
| 현재 기본값 | 63 |

저장된 CSV는 손댈 필요가 없습니다. 되돌리면 그날부터 예전 규칙으로 판정하고,
이미 수집된 기사는 그대로 남습니다.

---

## 9. 여쭙는 것 — 두 방안

기사 수를 늘리는 길이 둘 있고, **서로 독립적**이라 따로 판단하실 수 있습니다.

최근 3일(2026-09-05~07, 회수 220건) 실측입니다.

| 방안 | 통과 | 증가 | 상태 |
|---|---|---|---|
| 현행 | 23 | — | — |
| **①** 판정 텍스트 확대 (snippet·keywords) | 42 | **+19 (+83%)** | 적용함 |
| **②** M그룹 키워드 확장 | 38 | +15 (+65%) | **손대지 않음** |
| ①+② 둘 다 | **59** | +36 (+157%) | — |

날짜별로는 이렇습니다.

| 날짜 | 현행 | ① 적용 |
|---|---|---|
| 09-05 | 9 | 13 |
| 09-06 | **4** | 11 |
| 09-07 | 10 | 18 |

9/6 은 사이트에 **4건**으로 표시돼 신뢰도가 '낮음'이었습니다.

### ① 판정 텍스트 확대 — 적용했습니다

지정해주신 **키워드 세트는 그대로**고, 그 단어를 찾는 위치만 넓혔습니다
(제목+설명 → 제목+설명+snippet+keywords). Marketaux 가 이미 보내주는데
저희가 읽지 않던 텍스트입니다(2절).

되돌리기가 설정 한 줄이라 먼저 적용했습니다. 강도는 세 단계로 조절됩니다.

| 설정 | 증가 |
|---|---|
| 제목+설명 (원복) | — |
| + snippet | +22% |
| + snippet + keywords (현재) | +64% |

> **경위 정정**: 이 변경은 9/5 에 코드에 반영했으나 배포 브랜치 동기화를
> 빠뜨려 9/8 까지 실제로는 적용되지 않았습니다. 위 "현행" 수치가 그 기간의
> 실제 상태입니다. 9/8 에 동기화했고 다음 일일 수집부터 반영됩니다.

### ② M그룹 키워드 확장 — 판단을 여쭙니다

M그룹 27개에 아래가 빠져 있습니다.

```
FOMC · rate hike/cut · Fed meeting · Beige Book · 지역 연은 총재 이름
```

이 때문에 다음과 같은 기사가 탈락합니다.

```
탈락 · US Fed Beige Book Reveals Data Center Boom Fueling Regional Growth
탈락 · NY Fed's Williams attributes a strong economy for driving bond yields higher
통과 · Fed's Williams ties rising bond yields to strong economy, CNBC reports
```

마지막 두 줄은 **거의 같은 기사**인데 헤드라인 표현 차이로 갈립니다.
Williams 는 뉴욕 연은 총재인데 M그룹에는 의장 이름(Powell·Yellen 등)만 있습니다.

후보별 회복량입니다(8/24~9/2, F 는 있으나 M 이 없어 탈락한 162건 기준).

| 후보 | 회복 |
|---|---|
| rate hike/cut/decision | 47건 |
| tightening/easing/dovish/hawkish | 31건 |
| 지역 연은 총재 이름 | 10건 |
| Beige Book | 5건 |
| Fed meeting | 2건 |
| FOMC | 0건 (이미 다른 M단어와 함께 쓰임) |

### ② 반영 내역 (2026-09-10, 조교 승인)

지도교수 지정 원본 27개(`_M_BASE`)는 **그대로 두고** `_M_EXT` 로만 넓혔습니다.
`NEWS_M_EXTENDED=0` 으로 끄면 패턴이 원본과 문자 그대로 같아집니다(테스트로 고정).

**넣은 것**: FOMC · rate hike/cut/decision · Fed meeting · Beige Book ·
minutes(좁힌 형태) · FOMC 위원 성 15명

**뺀 것**: tightening · easing · dovish · hawkish — 범위가 넓어 무관 기사가
다수 들어온다는 조교 의견. 추가 표본 검토 후 별도 결정합니다(회수 가능량 4,028건).

`minutes` 는 형태를 좁혔습니다. 단독 `minutes` 는 "30 minutes" 류에도 걸립니다.

| 형태 | 회수 | 시간표현 오탐 |
|---|---|---|
| 단독 | 1,854 | 29 |
| 연준 문맥 0~1단어 | 1,656 | 2 |
| **연준 문맥 0~3단어 (채택)** | **1,670** | **2** |

0~3단어를 택한 이유는 오탐이 같으면서 `Federal Reserve releases June minutes`,
`Fed officials await June minutes` 를 더 잡기 때문입니다.

**남는 한계**: FOMC 위원 성은 F(연준)가 함께 요구돼 조합 정밀도가 높지만
`Thomas Cook (India)` 같은 오탐이 소수 남습니다. 다음 필터 감사에서 수치화합니다.

### 공통 — 정밀도 맞교환

둘 다 재현율을 올리는 대신 정밀도를 내줍니다. ① 로 새로 들어온 50건을
전수 확인한 결과는 4절에 적었습니다 — 절반은 명확한 정책 기사,
절반은 연준을 스치듯 언급하는 시장 논평이었습니다.

기사 수가 하루 4~10건이면 신뢰도 게이트(15건)를 넘지 못해 신호를 낼 수
없으므로, 어느 정도의 정밀도 손실은 감수할 만하다고 보았습니다.

---

## 10. 검토했으나 효과가 없던 방법

| 방법 | 결과 |
|---|---|
| 수집 창 확대·재수집 | **이미 한계** — 나중에 재조회해도 0~2건 |
| `similar` 필드 활용 | 빈 배열 (`group_similar` 이미 해제) |
| 중복 제거 개선 | 통과분에 중복 0건 |
| `pages` 상한 상향 | 걸리지 않음 (회수 200건 / 상한 2,000건) |

3일 수집 창은 제 역할을 다하고 있습니다. 병목은 판정 텍스트 범위였습니다.

---

## 부록 — 검증 내역

- 신규 9개 포함 **149개 테스트 통과** (main·deploy 양쪽)
- 실제 배포 데이터 1,338행으로 CSV 스키마 이관(6→8컬럼) 검증
  — 행 수·기존 값 보존, 컬럼 밀림 0
- 실수집 end-to-end 확인 (회수 339건 → 통과 63건)
- 되돌리기 3단계 동작 확인 (63 → 50 → 44)

재현:

```bash
python -m pytest tests/test_news_match_fields.py -q
```

---

## F그룹 질의어 누락 규모 (2026-09-11 실측)

HRS(2017) (iii) 에 따라 `FOMC`·`Federal Open Market Committee` 를 F그룹에
넣었지만, **API 질의어에는 안 들어가 있습니다.**

```
QUERY = '"federal reserve" | fed'
```

따라서 FOMC 만 있고 fed 가 없는 기사는 회수된 적이 없습니다. 통과분에도
탈락분에도 없으므로 기존 데이터로는 잴 수 없고, 질의를 새로 던져야 합니다
(`scripts/probe_fomc_query.py`). 316,745개 URL 과 대조한 결과입니다.

| 구간 | 회수 | 코퍼스에 없음 | F∧M 통과 | 그 달 통과분 대비 |
|---|---|---|---|---|
| 2026-07 (7/29 회의) | 411 | 48 | **5** | 5 / 841 = **0.6%** |
| 2026-08 (회의 없음) | 327 | 48 | **2** | 2 / 427 = **0.5%** |

두 달 모두 `found` 가 10,000 상한 아래라 잘리지 않았습니다.

### 어디에 몰리나

FOMC 회의 전후에 몰립니다 — 7월 5건 중 3건이 7/28~7/31 입니다. 다만 그
구간도 통과분이 194건이라 비중은 1.5% 입니다.

비중이 커 보이는 날은 전부 **얇은 날**입니다. 7/06(11건 중 1), 8/03(9건 중 1),
8/19(10건 중 1) 이 8~10% 인데 분모가 작아서 그렇습니다. 그리고 이 날들은
이미 신뢰도 게이트(15건) 미달이라 한 건 늘어도 게이트를 넘지 못합니다.

### 놓친 기사의 성격

절반 남짓은 실제 정책 기사입니다.

```
놓치면 아까운 것 · July FOMC Meeting: A Cautious Hold With Credibility Implications
                · Treasury yields edge lower as investors look ahead to FOMC minutes
있어도 그만인 것 · Peso touches P61.995:$1   (FOMC 를 스치듯 언급하는 환율 기사)
```

### 판단

**재수집(4시간)할 규모가 아닙니다.** 0.5% 이고 게이트 문제도 못 풉니다.

앞으로의 수집에만 `FOMC` 를 질의어에 넣는 것은 비용이 0 이지만 권하지
않습니다 — 그 시점부터 라이브의 회수 범위가 백필보다 넓어져 **모집단 이음매가
새로 생깁니다.** 0.5% 를 얻으려고 `docs/scope_impact.md` 에서 다룬 것과 같은
종류의 불일치를 만드는 셈입니다. 질의어를 바꾼다면 백필도 함께 다시 받아
양쪽을 맞추는 편이 맞고, 그때는 4시간을 쓸 이유가 따로 있어야 합니다.

재현:

```bash
python scripts/probe_fomc_query.py --from 2026-07-01 --to 2026-08-01 \
  --corpus data/news/fed_news_backfill.csv data/news/rejected_backfill.csv \
           data/news/fed_news.csv data/news/rejected_news.csv
```

라이브 코퍼스(`fed_news.csv`)는 deploy 브랜치에만 있습니다. main 에서 돌리면
`git show origin/deploy/streamlit-dashboard:data/news/fed_news.csv` 로 꺼내
넘겨야 대조가 완전해집니다. 결과는 `outputs/fomc_query_gap*.csv` 입니다.

---

관련 문서: `docs/scope_impact.md` (선정 범위 불일치) ·
`docs/filter_audit.md` (필터 감사) · `docs/news_fed_index.md` (뉴스축 정의)
