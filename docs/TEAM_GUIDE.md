# 팀 작업 가이드

이 저장소는 **매일 자동으로 도는 파이프라인**과 **공개 사이트**를 함께 갖고 있다.
그래서 평범한 코드 저장소와 다른 주의점이 몇 가지 있다. 작업 전에 이 문서를 먼저 읽자.

## 1. 브랜치가 두 개다 — 이게 제일 중요

| 브랜치 | 역할 |
|---|---|
| `main` | **정본.** 코드·문서를 여기서 수정한다 |
| `deploy/streamlit-dashboard` | **실제로 실행되는 쪽.** 매일 07:00 KST 자동화가 이 브랜치의 코드를 돌리고, 결과 데이터를 여기에 커밋한다. 사이트도 여기서 빌드된다 |

**⚠️ main만 고치면 아무 일도 일어나지 않는다.** 자동화도 사이트도 `deploy`를 본다.

```
코드 수정 → main 커밋·푸시 → deploy 에도 반영 → 그때부터 실제 동작·사이트 반영
```

### deploy 반영하는 안전한 방법

브랜치를 직접 오가지 말고 **worktree**를 쓴다(이유는 §2):

```bash
git worktree add /tmp/deploy-sync deploy/streamlit-dashboard
cd /tmp/deploy-sync && git pull --ff-only origin deploy/streamlit-dashboard
git checkout main -- <바꾼 파일들>          # 예: engine/ analysis/ dashboard-web/
git commit -m "deploy 동기화: ..." && git push origin HEAD:deploy/streamlit-dashboard
cd - && git worktree remove --force /tmp/deploy-sync
```

## 2. ⚠️ 브랜치를 바꾸면 데이터가 사라진다

`data/fomc.db`, `data/news/fed_news.csv`, `outputs/*.csv` 는
**`deploy`에서만 git 추적**되고 `main`에서는 `.gitignore` 대상이다.

→ `git checkout deploy` 했다가 `main`으로 돌아오면 **git이 이 파일들을 지운다.**

**복구법:**
```bash
git show origin/deploy/streamlit-dashboard:data/fomc.db > data/fomc.db
git show origin/deploy/streamlit-dashboard:data/news/fed_news.csv > data/news/fed_news.csv
```

**예방법:** 위 §1처럼 worktree를 쓰면 작업 트리를 건드리지 않아 이 문제가 없다.

## 3. 자동화가 매일 커밋한다

`github-actions[bot]` 이 매일 07:00 KST에 `deploy`로 커밋한다(수집된 뉴스·회의록·지수·대시보드 JSON).
`deploy`에서 작업할 땐 **먼저 `git pull`** 하자. 봇 커밋과 충돌하기 쉽다.

## 4. 사이트

- 주소: **https://aicp-econpilot.github.io/** (고정)
- 소스: 이 저장소 `dashboard-web/` (React + Vite)
- 배포 워크플로는 **다른 저장소**(`aicp-econpilot/aicp-econpilot.github.io`)에 있다 — [deploy/README.md](../deploy/README.md) 참조
- 매일 08:00 KST 자동 재배포 + 수동 실행 가능

**로컬 확인:**
```bash
python3 analysis/export_dashboard.py dashboard-web/public/data   # JSON 생성
cd dashboard-web && npm install && npm run dev                   # localhost:5173
```
`dashboard-web/public/data/` 는 git에 없다(생성물) — 위 명령으로 만든다.

## 5. 커밋하면 안 되는 것

| 대상 | 이유 |
|---|---|
| API 키 (`.newsapi_key`, `.fredapi_key`, `.env`) | 유출 위험. gitignore돼 있지만 **채팅·이슈에도 붙여넣지 말 것** |
| FinBERT 모델 (419MB) | 용량. 드롭박스에서 받아 `models/finbert-finetuned/` 에 둔다 |
| `data/wsj/` | 용량. 별도 공유 |

커밋 전 습관:
```bash
git diff --cached --name-only | grep -iE "\.key$|\.env$|newsapi|fredapi"   # 아무것도 안 나와야 정상
```

## 6. 감성 엔진 규칙 (지도교수 피드백, 2026-07)

- **원본 FinBERT(T=1)** 를 쓴다. 자체 라벨링·온도보정(T=3.1)은 **제거됨** — 되살리지 말 것
- 세 축(**성명문·회의록·기자회견**)은 **각각 따로** 점수화하고 통합은 가중평균으로 — 하나로 뭉쳐 분석하지 않는다
- 뉴스 선정은 **F그룹 AND M그룹** 키워드(`engine/news_scrape.py`) — 지도교수 지정 세트다
- 시장 비교·VIX는 **보류** 중(삭제 아님)

## 7. 축은 시차를 두고 도착한다

| 축 | 공개 시점 |
|---|---|
| 성명문 | 회의 당일 |
| 기자회견 | 며칠 후 |
| 회의록 | **3주 후** |

그래서 자동화는 매일 **"아직 3축이 안 찬 최근 회의"를 다시 방문**한다(`analysis/axis_status.py`).
회의 직후 데이터가 비어 보이는 건 정상이며, 도착하면 자동으로 채워진다.
현황은 `outputs/axis_status.csv` 또는 사이트 홈의 "수집 n/3" 열에서 볼 수 있다.

## 8. 바꾸기 전에 돌려볼 것

```bash
python3 -m pytest tests/ -q            # 83개 통과가 기준
sh scripts/run_news_daily.sh           # 전체 파이프라인(모델·키 필요)
```
