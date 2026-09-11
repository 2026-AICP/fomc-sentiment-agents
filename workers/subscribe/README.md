# econpilot-subscribe

FOMC 통화정책 알림 구독 접수 창구. Cloudflare Worker 하나로 구독·해지·명단
수출을 처리한다. 설계 근거: `docs/superpowers/specs/2026-09-10-subscription-worker-design.md`

## 엔드포인트

| 경로 | 메서드 | 용도 |
|---|---|---|
| `/api/subscribe` | POST | 이메일 구독 접수. IP 당 분당 5회 제한, 확인 메일 성공 시에만 KV 기록 |
| `/api/unsubscribe` | GET | 해지 확인 페이지만 보여준다 (삭제 안 함) |
| `/api/unsubscribe` | POST | 실제 해지 — 토큰으로 레코드·역인덱스 삭제 |
| `/api/export` | GET | GitHub Actions 가 발송 대상을 읽는 경로. `Authorization: Bearer <SUBSCRIBERS_TOKEN>` 필요 |

## 로컬 테스트

Worker 런타임 없이 Node 만으로 돈다 (Node 24, 전역 `Request`/`Response` 사용).

```bash
cd workers/subscribe && npm test
# 또는
node --test workers/subscribe/test/handlers.test.js
node --test workers/subscribe/test/index.test.js
```

## 배포

```bash
cd workers/subscribe
npx wrangler kv namespace create SUBSCRIBERS   # 나온 id 를 wrangler.toml 에 채운다
npx wrangler secret put SUBSCRIBERS_TOKEN      # /api/export 인증 토큰
npx wrangler secret put RESEND_API_KEY         # Resend 발송 키
npx wrangler deploy
```

## 시크릿 두 가지

- `SUBSCRIBERS_TOKEN` — `/api/export` 인증용 랜덤 토큰. 미설정 시 어떤 값으로도 통과 못 한다.
- `RESEND_API_KEY` — 환영 메일 발송용 Resend API 키.

둘 다 `wrangler secret put` 으로만 넣는다. `.env`·`wrangler.toml` 에 평문으로 적지 않는다.

## 절대 바꾸면 안 되는 것 세 가지

1. **구독자 이메일을 커밋하지 않는다.** 이 저장소는 PUBLIC 이고 히스토리가
   영구히 남는다. 테스트·문서·커밋 메시지 어디에도 실제 주소를 넣지 않는다.
2. **GET `/api/unsubscribe` 는 절대 삭제하지 않는다.** 메일 앱이 링크를 미리
   열어보므로, 클릭 없이 해지될 수 있다. 삭제는 POST 에서만 한다.
3. **CORS 출처를 `'*'` 로 설정하지 않는다.** `index.js` 의 `ALLOWED_ORIGIN` 은
   GitHub Pages 프런트엔드 도메인 하나로 고정돼야 한다.

## 프로젝트 종료 시 정리

```bash
npx wrangler kv namespace delete --namespace-id <NAMESPACE_ID>
npx wrangler secret delete SUBSCRIBERS_TOKEN
npx wrangler secret delete RESEND_API_KEY
npx wrangler delete
```
