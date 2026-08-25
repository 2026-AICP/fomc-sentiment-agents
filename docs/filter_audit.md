# 뉴스 필터 감사 — 놓친 기사 점검 (1차)

> TA 피드백: *"탈락시킨 기사에서 무작위 표본을 뽑아, 실제로 Fed 관련 중요한 기사를
> 얼마나 놓치고 있는지 확인"*
> 표본: 2026-08-18~24 수집분 중 탈락 33건 전수 · 도구: `analysis/filter_audit.py`

## 판정 기준 (표본을 보기 **전에** 확정)

키워드 유무가 아니라 **기사 내용**으로 판단한다. 필터를 만든 쪽이 키워드를 보고
판정하면 "걸러진 건 원래 안 중요했다"는 결론으로 흐르기 쉽다.

| 코드 | 기준 |
|---|---|
| **2 중요** | 연준의 정책 결정·기조·인사, 또는 통화정책을 정면으로 다룬 기사. 지수에 들어갔어야 함 |
| **1 주변** | 금리·물가 등 거시 기사인데 연준 정책과의 연결이 간접적. 들어가도 빠져도 되는 경계 |
| **0 무관** | 개별 종목·원자재·지정학 등 연준 정책과 무관 |

## 결과

| 구분 | 건수 | 비율 |
|---|---|---|
| 무관 (0) | 12 | 36.4% |
| 주변 (1) | 12 | 36.4% |
| **중요 (2)** | **9** | **27.3%** |

**놓침률 27.3%** — 탈락 기사 4건 중 1건 이상이 지수에 들어갔어야 할 기사였다.

특히 **FOMC 회의록 보도 4건이 전부 탈락**했다. 회의록은 이 프로젝트의 핵심 자료인데,
그것을 다룬 뉴스가 뉴스 지수에서 빠지고 있다.

### 놓친 중요 기사

| 기사 | 성격 |
|---|---|
| Fed officials saw need for rate hike…, minutes show | FOMC 회의록 |
| US Fed Minutes signal rate hike debate… | FOMC 회의록 |
| FOMC Minutes Tilt Hawkish… | FOMC 회의록 |
| Treasury rushes into bond market as Fed minutes show… | FOMC 회의록 |
| Kevin Warsh's Jackson Hole Speech… | 의장 연설 |
| Top Economist Shares One Way Kevin Warsh Could… | 의장 정책 행보 |
| To fire Cook from the Fed, Trump looks to channel Taft | 연준 인사·독립성 |
| The bond market is daring the Fed to hike | 인상 기대 |
| The Fed Must Be Held Tight To a Market-Price Stability Rule | 정책 준칙 논평 |

## 왜 탈락했나

| 원인 | 건수 |
|---|---|
| F는 있는데 **M이 없음** | 6 |
| M은 있는데 **F가 없음** | 2 |
| 둘 다 없음 | 1 |

M그룹에 없어서 놓친 표현 — 중요 기사에 실제로 등장한 단어들:

| 표현 | 등장 |
|---|---|
| `minutes` | 4건 |
| `inflation` | 4건 |
| `rate hike` | 3건 |
| `FOMC` | 2건 |
| `bond yield` | 2건 |
| `hawkish`, `Jackson Hole` | 각 1건 |

**F가 없어 탈락한 2건은 의장 이름만 나온 기사다** (`Kevin Warsh` 는 M그룹 소속이라
F 조건을 못 채움). 의장 이름은 연준을 가리키는 가장 확실한 신호인데, 현재 규칙에서는
M에만 있어서 "연준 언급 없음"으로 처리된다.

## 한계

- 표본이 **33건·7일치**로 작다. 계절성·이벤트 편중(이번 주에 FOMC 회의록 공개가 있었음)
  가능성이 있어, 기간을 늘려 재확인이 필요하다.
- 판정은 제목·요약만 보고 했다(본문 미확인). 실제 필터도 같은 범위를 보므로 조건은 같다.
- 판정자가 1명이라 경계 사례(주변 12건)의 일관성은 검증되지 않았다.

## 조치 (제안 — 지도교수 확인 필요)

키워드 세트는 지도교수 지정 사항이므로 **임의로 바꾸지 않는다.** 아래를 보고드리고 결정을 받는다.

1. **의장 이름을 F그룹에도 인정** — 의장 이름은 연준을 특정하는 표현이다. 규칙 변경 없이
   "F = 연준을 가리키는 표현"이라는 원래 취지에 부합한다. (놓침 2건 해소)
2. **M그룹에 `FOMC`·`minutes`·`rate hike`·`rate cut` 추가 검토** — 통화정책 자체를 가리키는
   표현인데 현재 빠져 있다. (놓침 6건 중 상당수 해소)
3. **`inflation` 추가 여부는 신중** — 물가 기사 전반이 들어와 정밀도가 크게 떨어질 수 있다.

## 재현

```bash
python3 analysis/filter_audit.py sample 40   # 무작위 표본 → outputs/filter_audit_sample.csv
python3 analysis/filter_audit.py report      # 판정 집계
```

탈락 기사는 `data/news/rejected_news.csv` 에 자동으로 쌓인다(2026-08 부터).
기간이 쌓이면 표본을 늘려 재감사할 것.
