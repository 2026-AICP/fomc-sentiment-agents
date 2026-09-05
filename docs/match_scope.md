# 뉴스 판정 범위 확대 — snippet·keywords 반영 보고

> 2026-09-05 · 뉴스 API 고도화
> 코드: `engine/news_scrape.py` (`MATCH_FIELDS`) · 커밋 `6ecc645`

## 요약

수집 건수가 늘지 않던 원인이 **회수가 아니라 필터**임을 확인했습니다.
Marketaux가 이미 보내주는데 저희가 읽지 않던 텍스트가 두 개 있었고,
그것을 판정에 포함하니 통과 건수가 **+64%** 늘었습니다.

**지정해주신 키워드 세트(F∧M 27개)는 한 글자도 바꾸지 않았습니다.**
바꾼 것은 그 단어를 *어디서 찾을지*입니다.

되돌리기 쉽게 토글로 만들어 두었고, 이미 적용해 두었습니다.
정밀도와의 맞교환이 있어 **어느 수준으로 둘지 판단을 여쭙습니다**(9절).

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

## 9. 여쭙는 것

어느 수준으로 둘지 판단해 주시면 반영하겠습니다.

| 안 | 설정 | 증가 | 성격 |
|---|---|---|---|
| **A** | 제목+설명 (원복) | — | 가장 보수적. 기사 수 문제는 남습니다 |
| **B** | + snippet | +22% | 본문 성격 텍스트만 추가. 노이즈 적음 |
| **C** | + snippet + keywords | **+64%** | 현재 적용 상태. 시장 논평 유입 |

의견을 여쭙지 않고 먼저 적용한 점 양해 부탁드립니다.
되돌리기가 즉시 가능하도록 만든 뒤 진행했고, 어느 쪽으로 정하시든
설정 한 줄로 반영됩니다.

### 함께 계류 중인 별건 — M그룹 키워드

이것과 **별개 사안**입니다. M그룹 27개에 아래가 빠져 있습니다.

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
후보 키워드를 넣으면 8/24~9/2 구간에서 254건 → 339건(+33%)이 됩니다.

지정해주신 사항이라 **손대지 않았습니다.** 판단해 주시면 반영하겠습니다.

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

- 신규 9개 포함 **112개 테스트 통과**
  (`yfinance` 미설치로 수집 불가한 11개 모듈 제외 — 기존 문제, 이 변경과 무관)
- 실제 배포 데이터 1,338행으로 CSV 스키마 이관(6→8컬럼) 검증
  — 행 수·기존 값 보존, 컬럼 밀림 0
- 실수집 end-to-end 확인 (회수 339건 → 통과 63건)
- 되돌리기 3단계 동작 확인 (63 → 50 → 44)

재현:

```bash
python -m pytest tests/test_news_match_fields.py -q
```

관련 문서: `docs/scope_impact.md` (선정 범위 불일치) ·
`docs/filter_audit.md` (필터 감사) · `docs/news_fed_index.md` (뉴스축 정의)
