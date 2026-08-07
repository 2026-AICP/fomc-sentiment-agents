# Econpilot 사이트 배포 (aicp-econpilot.github.io)

사이트 소스는 이 레포(`2026-AICP/fomc-sentiment-agents`)에 있고,
**배포 워크플로는 대표 페이지 레포(`aicp-econpilot/aicp-econpilot.github.io`)에 둔다.**

## 왜 이렇게 하나

다른 레포로 밀어 넣으려면 쓰기 토큰(PAT)을 시크릿으로 등록해야 하는데,
소스 레포에 시크릿을 만들 권한이 없을 수 있다. 반대로 **레포가 자기 자신의 Pages에
배포할 때는 GitHub이 워크플로에 자동으로 주는 권한(`GITHUB_TOKEN`)만으로 충분하다.**

이 레포가 **공개(public)** 라서, 대표 페이지 레포가 소스를 그냥 내려받아 빌드할 수 있다.
→ 토큰·시크릿이 전혀 필요 없다.

```
aicp-econpilot.github.io (워크플로 위치)
   │  ① 공개 소스 clone (deploy 브랜치 = 데이터 최신)
   │  ② npm run build
   └─ ③ 자기 Pages 로 배포        ← GITHUB_TOKEN
```

## 설치 방법 (1회)

`aicp-econpilot/aicp-econpilot.github.io` 레포에
`.github/workflows/publish.yml` 파일로 [`publish-site.yml`](publish-site.yml) 내용을 그대로 넣는다.

GitHub 웹에서: **Add file → Create new file** → 파일명에
`.github/workflows/publish.yml` 입력 → 내용 붙여넣기 → Commit.

그다음 그 레포 **Settings → Pages → Source: GitHub Actions** 로 지정.

## 갱신 주기

- 매일 **23:00 UTC(=08:00 KST)** 자동 실행 — 소스 레포의 데이터 수집(07:00 KST) 직후라
  그날 갱신된 지수가 사이트에 반영된다.
- **Actions 탭 → Publish site → Run workflow** 로 언제든 수동 실행.

소스 코드나 데이터를 고치면 다음 실행 때 자동 반영된다(사이트 주소는 그대로).
