# 구독 접수 창구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 구독자 이메일을 접수·보관·해지하고, GitHub Actions 가 그 명단을 읽을 수 있는 Cloudflare Worker 를 만든다.

**Architecture:** 핸들러를 KV·메일발송에 의존하지 않는 순수 함수(`src/handlers.js`)로 분리하고, Worker 진입점(`src/index.js`)이 라우팅·CORS·바인딩만 맡는다. 테스트는 가짜 KV(`Map` 기반)를 주입해 Node 내장 러너로 돌린다 — 새 런타임 의존성이 0 이다.

**Tech Stack:** Cloudflare Workers (ES modules) · Workers KV · Resend HTTP API · Node 24 내장 `node:test` · wrangler CLI

**Spec:** `docs/superpowers/specs/2026-09-10-subscription-worker-design.md`

## Global Constraints

- **구독자 이메일을 리포에 절대 커밋하지 않는다.** 리포가 PUBLIC 이고 히스토리는 되돌려도 남는다 (spec §6).
- **시크릿을 코드·`wrangler.toml`·커밋 메시지 어디에도 넣지 않는다.** Worker 쪽은 `wrangler secret put`, Actions 쪽은 GitHub Secret.
- **`agents/notifier.py` 와 `tests/test_notifier_node.py` 를 수정하지 않는다.** 드라이런과 "발송 모듈 import 금지" 잠금은 그대로 둔다 (spec §2).
- 허용 출처는 `https://aicp-econpilot.github.io` 하나. `*` 금지 (spec §5-3).
- 커밋 메시지는 한국어. 끝에 다음 두 줄을 붙인다:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TLox9uPxzbxiL9nHrsejdd
  ```

## File Structure

| 파일 | 책임 |
|---|---|
| `workers/subscribe/src/handlers.js` | 순수 함수. KV·메일발송을 **인자로** 받는다. 여기에 `fetch`·전역 `env` 접근이 없어야 한다 |
| `workers/subscribe/src/index.js` | 라우팅 · CORS · HTML 응답 · Resend 호출. 비즈니스 로직 없음 |
| `workers/subscribe/test/fake-kv.js` | 테스트용 가짜 KV |
| `workers/subscribe/test/handlers.test.js` | 핸들러 테스트 |
| `workers/subscribe/wrangler.toml` | KV 바인딩 · 라우트 |
| `workers/subscribe/package.json` | wrangler 핀 고정 (런타임 의존성 아님) |
| `workers/subscribe/README.md` | 배포 · 시크릿 설정 절차 |

---

### Task 1: 스캐폴딩과 순수 유틸

**Files:**
- Create: `workers/subscribe/package.json`
- Create: `workers/subscribe/src/handlers.js`
- Create: `workers/subscribe/test/handlers.test.js`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 없음
- Produces: `isValidEmail(email) -> boolean` · `normalizeEmail(email) -> string` · `sha256Hex(text) -> Promise<string>` · `randomToken() -> string` · `LEVELS: string[]`

- [ ] **Step 1: 디렉터리와 package.json 생성**

`workers/subscribe/package.json`:

```json
{
  "name": "econpilot-subscribe",
  "private": true,
  "type": "module",
  "devDependencies": {
    "wrangler": "4.42.0"
  }
}
```

`"type": "module"` 이 있어야 `import`/`export` 가 Node 에서 그대로 돈다. `wrangler` 는 배포 전용이고 Worker 런타임에는 들어가지 않는다.

- [ ] **Step 2: .gitignore 에 node_modules 추가**

`.gitignore` 끝에 다음을 추가한다 (이미 있으면 건너뛴다):

```
node_modules/
```

- [ ] **Step 3: 실패하는 테스트 작성**

`workers/subscribe/test/handlers.test.js`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isValidEmail, normalizeEmail, sha256Hex, randomToken, LEVELS,
} from '../src/handlers.js';

test('isValidEmail: 명백한 쓰레기를 거른다', () => {
  assert.equal(isValidEmail('a@b.com'), true);
  assert.equal(isValidEmail('a@b'), false);      // TLD 없음
  assert.equal(isValidEmail('a b@c.com'), false); // 공백
  assert.equal(isValidEmail('@c.com'), false);
  assert.equal(isValidEmail(''), false);
  assert.equal(isValidEmail(null), false);
  assert.equal(isValidEmail('a'.repeat(250) + '@b.com'), false); // 254자 초과
});

test('normalizeEmail: 앞뒤 공백 제거 + 소문자', () => {
  assert.equal(normalizeEmail('  A@X.COM '), 'a@x.com');
});

test('sha256Hex: 64자 16진수, 같은 입력은 같은 값', async () => {
  const h = await sha256Hex('a@x.com');
  assert.match(h, /^[0-9a-f]{64}$/);
  assert.equal(h, await sha256Hex('a@x.com'));
  assert.notEqual(h, await sha256Hex('b@x.com'));
});

test('randomToken: 64자 16진수, 매번 다름', () => {
  const a = randomToken();
  assert.match(a, /^[0-9a-f]{64}$/);
  assert.notEqual(a, randomToken());
});

test('LEVELS: alert 과 caution 둘뿐', () => {
  assert.deepEqual(LEVELS, ['alert', 'caution']);
});
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

Run: `node --test workers/subscribe/test/`
Expected: FAIL — `Cannot find module '../src/handlers.js'`

- [ ] **Step 5: 최소 구현**

`workers/subscribe/src/handlers.js`:

```js
// 구독 접수 창구의 순수 로직.
//
// 이 파일은 KV 도 fetch 도 직접 만지지 않는다 — 전부 인자로 받는다.
// 그래야 Worker 런타임 없이 node:test 로 그대로 돌릴 수 있다.
// 설계: docs/superpowers/specs/2026-09-10-subscription-worker-design.md

export const LEVELS = ['alert', 'caution'];

// 완전한 RFC 5322 검증은 하지 않는다. 정규식으로 이메일을 엄밀히 검증하려는
// 시도는 거의 항상 실패하고, 진짜 검증은 어차피 "그 주소로 메일이 가느냐"다.
// 여기서는 명백한 쓰레기만 거른다. 254자는 RFC 5321 의 주소 길이 상한.
export function isValidEmail(email) {
  return typeof email === 'string'
    && email.length <= 254
    && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// 대소문자만 다른 주소가 두 건으로 쌓이는 것을 막는다. 로컬파트는 RFC 상
// 대소문자를 구분하지만 주요 메일 서비스는 전부 구분하지 않는다.
export function normalizeEmail(email) {
  return email.trim().toLowerCase();
}

export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function randomToken() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

`crypto.subtle` 과 `crypto.getRandomValues` 는 Workers 와 Node 18+ 양쪽에서 전역이다. 목킹이 필요 없다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `node --test workers/subscribe/test/`
Expected: PASS (5 tests)

- [ ] **Step 7: 커밋**

```bash
git add workers/subscribe/package.json workers/subscribe/src/handlers.js \
        workers/subscribe/test/handlers.test.js .gitignore
git commit -m "feat(worker): 구독 창구 스캐폴딩과 순수 유틸"
```

---

### Task 2: 가짜 KV 와 subscribe 핸들러

**Files:**
- Create: `workers/subscribe/test/fake-kv.js`
- Modify: `workers/subscribe/src/handlers.js`
- Modify: `workers/subscribe/test/handlers.test.js`

**Interfaces:**
- Consumes: `isValidEmail` · `normalizeEmail` · `sha256Hex` · `randomToken` · `LEVELS` (Task 1)
- Produces: `subscribe(kv, sendMail, { email, level }) -> Promise<{status, body}>`
  - `kv` 는 `get(key, type?)` · `put(key, value, opts?)` · `delete(key)` · `list({prefix, cursor})` 를 갖는 객체
  - `sendMail(record) -> Promise<void>`
  - 구독 레코드 형태: `{id, channel, email, level, fed_events, overnight, created_at, unsub_token}`

- [ ] **Step 1: 가짜 KV 작성**

`workers/subscribe/test/fake-kv.js`:

```js
// 테스트용 가짜 KV.
//
// 실제 Workers KV 와 다른 점 두 가지를 알고 쓴다.
//   - expirationTtl 을 무시한다. 만료 동작은 테스트하지 않는다
//     (Cloudflare 가 지우는 것이고 우리 코드의 책임이 아니다).
//   - list() 가 항상 한 번에 전부 준다. 실제 KV 는 1000건씩 끊어 주므로
//     핸들러는 cursor 루프를 돌아야 한다 — 그 루프는 여기서 1회로 끝난다.
export class FakeKV {
  constructor() {
    this.store = new Map();
  }

  async get(key, type) {
    const v = this.store.get(key);
    if (v === undefined) return null;
    return type === 'json' ? JSON.parse(v) : v;
  }

  async put(key, value) {
    this.store.set(key, value);
  }

  async delete(key) {
    this.store.delete(key);
  }

  async list({ prefix = '' } = {}) {
    const keys = [...this.store.keys()]
      .filter((k) => k.startsWith(prefix))
      .map((name) => ({ name }));
    return { keys, list_complete: true, cursor: undefined };
  }
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`workers/subscribe/test/handlers.test.js` 의 import 줄을 다음으로 교체한다:

```js
import {
  isValidEmail, normalizeEmail, sha256Hex, randomToken, LEVELS, subscribe,
} from '../src/handlers.js';
import { FakeKV } from './fake-kv.js';
```

파일 끝에 다음을 추가한다:

```js
function collectMail() {
  const sent = [];
  return { sent, sendMail: async (record) => { sent.push(record); } };
}

test('subscribe: 레코드와 역인덱스를 저장하고 환영 메일을 보낸다', async () => {
  const kv = new FakeKV();
  const { sent, sendMail } = collectMail();

  const res = await subscribe(kv, sendMail, { email: 'a@x.com', level: 'alert' });

  assert.equal(res.status, 200);
  const hash = await sha256Hex('a@x.com');
  const rec = await kv.get(`sub:${hash}`, 'json');
  assert.equal(rec.email, 'a@x.com');
  assert.equal(rec.level, 'alert');
  assert.equal(rec.channel, 'email');
  assert.equal(await kv.get(`tok:${rec.unsub_token}`), hash);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].unsub_token, rec.unsub_token);
});

test('subscribe: 잘못된 주소는 400 이고 아무것도 저장하지 않는다', async () => {
  const kv = new FakeKV();
  const { sent, sendMail } = collectMail();

  const res = await subscribe(kv, sendMail, { email: 'nope', level: 'alert' });

  assert.equal(res.status, 400);
  assert.equal(kv.store.size, 0);
  assert.equal(sent.length, 0);
});

test('subscribe: 대소문자·공백이 달라도 같은 사람으로 본다', async () => {
  const kv = new FakeKV();
  const { sendMail } = collectMail();

  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'alert' });
  await subscribe(kv, sendMail, { email: '  A@X.COM ', level: 'caution' });

  const subKeys = (await kv.list({ prefix: 'sub:' })).keys;
  assert.equal(subKeys.length, 1);
  const rec = await kv.get(subKeys[0].name, 'json');
  assert.equal(rec.level, 'caution');   // 나중 값으로 덮어써진다
});

test('subscribe: 재가입 시 옛 해지 토큰의 역인덱스를 지운다', async () => {
  const kv = new FakeKV();
  const { sendMail } = collectMail();

  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'alert' });
  const first = await kv.get(`sub:${await sha256Hex('a@x.com')}`, 'json');

  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'caution' });

  assert.equal(await kv.get(`tok:${first.unsub_token}`), null);
  const tokKeys = (await kv.list({ prefix: 'tok:' })).keys;
  assert.equal(tokKeys.length, 1);
});

test('subscribe: 모르는 level 은 alert 으로 떨어뜨린다', async () => {
  const kv = new FakeKV();
  const { sendMail } = collectMail();

  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'everything' });

  const rec = await kv.get(`sub:${await sha256Hex('a@x.com')}`, 'json');
  assert.equal(rec.level, 'alert');
});
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `node --test workers/subscribe/test/`
Expected: FAIL — `subscribe is not a function`

- [ ] **Step 4: 최소 구현**

`workers/subscribe/src/handlers.js` 끝에 추가한다:

```js
// 구독 접수. 확인 메일 단계는 없다 — 넣는 즉시 명단에 들어간다(spec §3).
// 그래서 환영 메일이 선택이 아니다: 오등록된 사람이 자기가 등록됐음을 아는
// 유일한 통로다.
export async function subscribe(kv, sendMail, { email, level }) {
  if (!isValidEmail(email)) {
    return { status: 400, body: { error: 'invalid_email' } };
  }

  const normalized = normalizeEmail(email);
  const hash = await sha256Hex(normalized);

  // 재가입이면 옛 해지 토큰의 역인덱스를 먼저 지운다. 안 지우면 tok: 키가
  // 영원히 쌓이고, 옛 링크로도 해지가 된다.
  const prev = await kv.get(`sub:${hash}`, 'json');
  if (prev && prev.unsub_token) {
    await kv.delete(`tok:${prev.unsub_token}`);
  }

  const record = {
    id: crypto.randomUUID(),
    channel: 'email',
    email: normalized,
    level: LEVELS.includes(level) ? level : 'alert',
    fed_events: true,
    overnight: true,
    created_at: new Date().toISOString(),
    unsub_token: randomToken(),
  };

  await kv.put(`sub:${hash}`, JSON.stringify(record));
  await kv.put(`tok:${record.unsub_token}`, hash);
  await sendMail(record);

  // 이미 가입된 주소인지를 응답으로 알리지 않는다. 알리면 주소를 하나씩
  // 넣어보며 "이 사람이 구독자인가"를 확인할 수 있다.
  return { status: 200, body: { ok: true } };
}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `node --test workers/subscribe/test/`
Expected: PASS (10 tests)

- [ ] **Step 6: 커밋**

```bash
git add workers/subscribe/src/handlers.js workers/subscribe/test/
git commit -m "feat(worker): subscribe 핸들러 — 즉시 등록 + 환영 메일"
```

---

### Task 3: unsubscribe 와 export 핸들러

**Files:**
- Modify: `workers/subscribe/src/handlers.js`
- Modify: `workers/subscribe/test/handlers.test.js`

**Interfaces:**
- Consumes: Task 2 의 `subscribe`, `FakeKV`
- Produces: `unsubscribe(kv, token) -> Promise<{status, body}>` · `exportSubscribers(kv) -> Promise<{status, body:{subscribers, count}}>`

- [ ] **Step 1: 실패하는 테스트 작성**

import 줄에 `unsubscribe, exportSubscribers` 를 추가하고, 파일 끝에 추가한다:

```js
test('unsubscribe: 레코드와 역인덱스를 모두 지운다', async () => {
  const kv = new FakeKV();
  const { sendMail } = collectMail();
  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'alert' });
  const rec = await kv.get(`sub:${await sha256Hex('a@x.com')}`, 'json');

  const res = await unsubscribe(kv, rec.unsub_token);

  assert.equal(res.status, 200);
  assert.equal(kv.store.size, 0);   // 보관하지 않는다
});

test('unsubscribe: 모르는 토큰은 404', async () => {
  const kv = new FakeKV();
  const res = await unsubscribe(kv, 'deadbeef');
  assert.equal(res.status, 404);
});

test('unsubscribe: 두 번 눌러도 터지지 않는다', async () => {
  const kv = new FakeKV();
  const { sendMail } = collectMail();
  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'alert' });
  const rec = await kv.get(`sub:${await sha256Hex('a@x.com')}`, 'json');

  await unsubscribe(kv, rec.unsub_token);
  const second = await unsubscribe(kv, rec.unsub_token);

  assert.equal(second.status, 404);
});

test('exportSubscribers: sub: 키만 모아 반환한다', async () => {
  const kv = new FakeKV();
  const { sendMail } = collectMail();
  await subscribe(kv, sendMail, { email: 'a@x.com', level: 'alert' });
  await subscribe(kv, sendMail, { email: 'b@x.com', level: 'caution' });

  const res = await exportSubscribers(kv);

  assert.equal(res.status, 200);
  assert.equal(res.body.count, 2);
  const emails = res.body.subscribers.map((s) => s.email).sort();
  assert.deepEqual(emails, ['a@x.com', 'b@x.com']);
});

test('exportSubscribers: 아무도 없으면 빈 배열', async () => {
  const res = await exportSubscribers(new FakeKV());
  assert.equal(res.body.count, 0);
  assert.deepEqual(res.body.subscribers, []);
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `node --test workers/subscribe/test/`
Expected: FAIL — `unsubscribe is not a function`

- [ ] **Step 3: 최소 구현**

`workers/subscribe/src/handlers.js` 끝에 추가한다:

```js
// 해지. 즉시 삭제하고 보관하지 않는다 (notification_design.md §6-3).
export async function unsubscribe(kv, token) {
  const hash = await kv.get(`tok:${token}`);
  if (!hash) {
    // 이미 해지했거나 토큰이 틀렸다. 둘을 구분해 알리지 않는다.
    return { status: 404, body: { error: 'not_found' } };
  }
  await kv.delete(`sub:${hash}`);
  await kv.delete(`tok:${token}`);
  return { status: 200, body: { ok: true } };
}

// GitHub Actions 가 발송 대상을 읽는 경로.
// 실제 KV 의 list() 는 1000건씩 끊어 주므로 cursor 를 따라 끝까지 돈다.
export async function exportSubscribers(kv) {
  const subscribers = [];
  let cursor;
  do {
    const page = await kv.list({ prefix: 'sub:', cursor });
    for (const key of page.keys) {
      const record = await kv.get(key.name, 'json');
      if (record) subscribers.push(record);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return { status: 200, body: { subscribers, count: subscribers.length } };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test workers/subscribe/test/`
Expected: PASS (15 tests)

- [ ] **Step 5: 커밋**

```bash
git add workers/subscribe/src/handlers.js workers/subscribe/test/handlers.test.js
git commit -m "feat(worker): unsubscribe · export 핸들러"
```

---

### Task 4: 요청 제한

**Files:**
- Modify: `workers/subscribe/src/handlers.js`
- Modify: `workers/subscribe/test/handlers.test.js`

**Interfaces:**
- Consumes: `FakeKV` (Task 2)
- Produces: `checkRate(kv, ip, limit = 5) -> Promise<boolean>` — 통과면 `true`, 초과면 `false`

더블 옵트인을 하지 않으므로(spec §3) 이것이 **유일한 사전 방어선**이다.

- [ ] **Step 1: 실패하는 테스트 작성**

import 줄에 `checkRate` 를 추가하고, 파일 끝에 추가한다:

```js
test('checkRate: 한도까지는 통과, 넘으면 막는다', async () => {
  const kv = new FakeKV();
  for (let i = 0; i < 5; i += 1) {
    assert.equal(await checkRate(kv, '1.2.3.4'), true, `${i + 1}번째는 통과해야 한다`);
  }
  assert.equal(await checkRate(kv, '1.2.3.4'), false);
});

test('checkRate: IP 마다 따로 센다', async () => {
  const kv = new FakeKV();
  for (let i = 0; i < 5; i += 1) await checkRate(kv, '1.2.3.4');

  assert.equal(await checkRate(kv, '1.2.3.4'), false);
  assert.equal(await checkRate(kv, '5.6.7.8'), true);
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `node --test workers/subscribe/test/`
Expected: FAIL — `checkRate is not a function`

- [ ] **Step 3: 최소 구현**

`workers/subscribe/src/handlers.js` 끝에 추가한다:

```js
// 같은 IP 의 분당 요청 수를 센다.
//
// KV 는 원자적 증가를 지원하지 않으므로, 동시 요청이 같은 값을 읽어 둘 다
// 통과할 수 있다. 정확한 차단이 아니라 대량 유입을 늦추는 것이 목적이므로
// 그 오차를 받아들인다. 정확성이 필요해지면 Durable Object 로 옮긴다.
//
// expirationTtl 최소값이 60초라 창(window)이 1분으로 고정된다.
export async function checkRate(kv, ip, limit = 5) {
  const key = `rate:${ip}`;
  const count = Number(await kv.get(key)) || 0;
  if (count >= limit) return false;
  await kv.put(key, String(count + 1), { expirationTtl: 60 });
  return true;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test workers/subscribe/test/`
Expected: PASS (17 tests)

- [ ] **Step 5: 커밋**

```bash
git add workers/subscribe/src/handlers.js workers/subscribe/test/handlers.test.js
git commit -m "feat(worker): IP 분당 요청 제한"
```

---

### Task 5: Worker 진입점 — 라우팅 · CORS · 메일 발송

**Files:**
- Create: `workers/subscribe/src/index.js`
- Create: `workers/subscribe/wrangler.toml`

**Interfaces:**
- Consumes: `subscribe` · `unsubscribe` · `exportSubscribers` · `checkRate` (Task 2~4)
- Produces: 배포 가능한 Worker. 바인딩 이름 `SUBSCRIBERS`(KV), 시크릿 `RESEND_API_KEY` · `SUBSCRIBERS_TOKEN`

- [ ] **Step 1: wrangler.toml 작성**

`workers/subscribe/wrangler.toml`:

```toml
name = "econpilot-subscribe"
main = "src/index.js"
compatibility_date = "2026-09-10"

# 라우트는 econpilot.org 아래에 둔다. 수신거부 링크가 메일 발신 도메인과
# 같아야 스팸 필터가 피싱 패턴으로 보지 않는다 (spec §5).
routes = [
  { pattern = "econpilot.org/api/*", zone_name = "econpilot.org" }
]

# id 는 `npx wrangler kv namespace create SUBSCRIBERS` 실행 후 채운다.
[[kv_namespaces]]
binding = "SUBSCRIBERS"
id = "PLACEHOLDER_네임스페이스_생성후_채울것"
```

> `id` 는 Step 3 에서 실제 값으로 바꾼다. 그 전에는 배포가 실패한다.

- [ ] **Step 2: index.js 작성**

`workers/subscribe/src/index.js`:

```js
// 구독 접수 창구 Worker — 라우팅 · CORS · 메일 발송만 한다.
// 판단 로직은 전부 handlers.js 에 있다.
// 설계: docs/superpowers/specs/2026-09-10-subscription-worker-design.md
import {
  subscribe, unsubscribe, exportSubscribers, checkRate,
} from './handlers.js';

const ALLOWED_ORIGIN = 'https://aicp-econpilot.github.io';
const FROM = 'EconPilot <noreply@econpilot.org>';

function corsHeaders(origin) {
  // 허용 출처일 때만 헤더를 단다. '*' 는 쓰지 않는다 — 남의 사이트가 우리
  // 창구를 자기 폼처럼 쓰게 된다. (CORS 는 브라우저 규칙일 뿐이라 스크립트
  // 요청은 그대로 통과한다. 실제 방어선은 checkRate 다.)
  return origin === ALLOWED_ORIGIN
    ? { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin' }
    : {};
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders(origin) },
  });
}

function page(title, message, buttonHtml = '') {
  return new Response(
    `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;
padding:0 1rem;line-height:1.6;color:#1a1a1a}button{font:inherit;padding:.6rem 1.2rem;
border:0;border-radius:.4rem;background:#c00000;color:#fff;cursor:pointer}</style>
</head><body><h1>${title}</h1><p>${message}</p>${buttonHtml}</body></html>`,
    { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } },
  );
}

async function sendWelcome(apiKey, record) {
  const unsubUrl = `https://econpilot.org/api/unsubscribe?t=${record.unsub_token}`;
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: FROM,
      to: [record.email],
      subject: 'EconPilot 알림 구독이 시작되었습니다',
      // 메일 앱 상단에 해지 버튼을 띄우게 한다. 스팸 신고 버튼 옆에 해지
      // 버튼이 있으면 사람들은 해지를 누른다 (spec §3).
      headers: {
        'List-Unsubscribe': `<${unsubUrl}>`,
        'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
      },
      html: `<p>EconPilot 알림 구독이 시작되었습니다.</p>
<p>FOMC 통화정책 관련 뉴스 감성과 시장 지표가 어긋나는 날에 메일을 보냅니다.
참고용이며 투자조언이 아닙니다.</p>
<p>신청하지 않으셨다면 <a href="${unsubUrl}">여기서 해지</a>해 주세요.</p>`,
    }),
  });
  if (!res.ok) throw new Error(`resend ${res.status}: ${await res.text()}`);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin');
    const path = url.pathname;

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          ...corsHeaders(origin),
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    if (path === '/api/subscribe' && request.method === 'POST') {
      const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
      if (!await checkRate(env.SUBSCRIBERS, ip)) {
        return json({ error: 'rate_limited' }, 429, origin);
      }
      let payload;
      try {
        payload = await request.json();
      } catch {
        return json({ error: 'invalid_json' }, 400, origin);
      }
      const result = await subscribe(
        env.SUBSCRIBERS,
        (record) => sendWelcome(env.RESEND_API_KEY, record),
        { email: payload.email, level: payload.level },
      );
      return json(result.body, result.status, origin);
    }

    if (path === '/api/unsubscribe' && request.method === 'GET') {
      // GET 에서는 절대 지우지 않는다. Gmail·Outlook 이 메일 속 링크를 미리
      // 열어보면 구독자가 클릭하지도 않았는데 해지된다 (spec §5-2).
      // 토큰을 HTML 에 보간하지 않는다. ?t= 는 공격자가 마음대로 넣을 수
      // 있어서, 속성 안에 박으면 따옴표 하나로 빠져나와 스크립트를 심을 수
      // 있다. 브라우저가 자기 주소창에서 직접 읽게 한다.
      return page(
        '알림 해지',
        '아래 버튼을 누르면 구독이 취소되고 주소가 즉시 삭제됩니다.',
        `<button id="go">해지하기</button>
<script>
document.getElementById('go').addEventListener('click', function () {
  var t = new URLSearchParams(location.search).get('t') || '';
  fetch('/api/unsubscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: t }),
  }).then(function (r) {
    document.body.textContent = r.ok
      ? '해지되었습니다. 주소를 삭제했습니다.'
      : '해지하지 못했습니다. 이미 해지되었거나 링크가 올바르지 않습니다.';
  });
});
</script>`,
      );
    }

    if (path === '/api/unsubscribe' && request.method === 'POST') {
      let token = url.searchParams.get('t');
      if (!token) {
        // 메일 앱의 원클릭 해지(RFC 8058)는 본문 없이 POST 만 보내기도 한다.
        try {
          token = (await request.json()).token;
        } catch {
          token = null;
        }
      }
      const result = await unsubscribe(env.SUBSCRIBERS, token || '');
      return json(result.body, result.status, origin);
    }

    if (path === '/api/export' && request.method === 'GET') {
      const auth = request.headers.get('Authorization') || '';
      if (auth !== `Bearer ${env.SUBSCRIBERS_TOKEN}`) {
        return json({ error: 'unauthorized' }, 401, origin);
      }
      const result = await exportSubscribers(env.SUBSCRIBERS);
      return json(result.body, result.status, origin);
    }

    return json({ error: 'not_found' }, 404, origin);
  },
};
```

- [ ] **Step 3: KV 네임스페이스 생성하고 id 채우기**

```bash
cd workers/subscribe
npm install
npx wrangler kv namespace create SUBSCRIBERS
```

출력에 나온 `id = "..."` 값을 `wrangler.toml` 의 `PLACEHOLDER_네임스페이스_생성후_채울것` 자리에 넣는다.

- [ ] **Step 4: 문법 확인**

Run: `node --check workers/subscribe/src/index.js`
Expected: 출력 없음 (통과)

Run: `node --test workers/subscribe/test/`
Expected: PASS (17 tests) — index.js 를 추가해도 기존 테스트가 깨지지 않는다

- [ ] **Step 5: 커밋**

```bash
git add workers/subscribe/src/index.js workers/subscribe/wrangler.toml \
        workers/subscribe/package-lock.json
git commit -m "feat(worker): 진입점 — 라우팅 · CORS · Resend 발송"
```

---

### Task 6: 배포와 실물 검증

**Files:**
- Create: `workers/subscribe/README.md`

**Interfaces:**
- Consumes: Task 5 의 배포 가능한 Worker
- Produces: 동작하는 `https://econpilot.org/api/*`

- [ ] **Step 1: 시크릿 설정**

```bash
cd workers/subscribe

# Resend 키 — GitHub Secret 에 넣은 것과 같은 값
npx wrangler secret put RESEND_API_KEY

# 명단 조회용 토큰 — 새로 만든다
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
npx wrangler secret put SUBSCRIBERS_TOKEN
```

`SUBSCRIBERS_TOKEN` 은 같은 값을 GitHub Secret 에도 넣는다:
`Settings → Secrets and variables → Actions → New repository secret`

- [ ] **Step 2: 배포**

Run: `npx wrangler deploy`
Expected: `Deployed econpilot-subscribe` 와 라우트 `econpilot.org/api/*` 가 출력된다

- [ ] **Step 3: 성공 기준 확인 — 인증**

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://econpilot.org/api/export
# 기대: 401

curl -s -H "Authorization: Bearer <SUBSCRIBERS_TOKEN>" https://econpilot.org/api/export
# 기대: {"subscribers":[],"count":0}
```

- [ ] **Step 4: 성공 기준 확인 — 가입과 해지**

```bash
curl -s -X POST https://econpilot.org/api/subscribe \
  -H 'Content-Type: application/json' \
  -d '{"email":"robin1967@unist.ac.kr","level":"alert"}'
# 기대: {"ok":true} + 환영 메일 도착
```

메일에서 해지 링크를 열어 **버튼을 누르기 전에는 아직 구독자가 남아 있는지** 확인한다:

```bash
curl -s -H "Authorization: Bearer <SUBSCRIBERS_TOKEN>" https://econpilot.org/api/export
# 기대: count 1  ← GET 만으로는 지워지지 않는다
```

버튼을 누른 뒤 다시 확인한다:

```bash
curl -s -H "Authorization: Bearer <SUBSCRIBERS_TOKEN>" https://econpilot.org/api/export
# 기대: count 0
```

- [ ] **Step 5: 성공 기준 확인 — 요청 제한**

```bash
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "$i: %{http_code}\n" -X POST https://econpilot.org/api/subscribe \
    -H 'Content-Type: application/json' -d '{"email":"ratetest@example.com","level":"alert"}'
done
# 기대: 1~5 는 200, 6 은 429
```

끝나면 남은 테스트 레코드를 지운다:

```bash
npx wrangler kv key list --binding SUBSCRIBERS --prefix sub:
npx wrangler kv key delete --binding SUBSCRIBERS "sub:<해시>"
```

- [ ] **Step 6: 성공 기준 확인 — CORS**

허용 출처면 헤더가 붙고, 아니면 안 붙는다.

```bash
curl -s -D - -o /dev/null -X OPTIONS https://econpilot.org/api/subscribe   -H 'Origin: https://aicp-econpilot.github.io' | grep -i access-control-allow-origin
# 기대: access-control-allow-origin: https://aicp-econpilot.github.io

curl -s -D - -o /dev/null -X OPTIONS https://econpilot.org/api/subscribe   -H 'Origin: https://evil.example' | grep -i access-control-allow-origin
# 기대: 출력 없음 (헤더가 붙지 않아 브라우저가 응답을 막는다)
```

두 번째가 **HTTP 200 인 것은 정상이다.** CORS 는 서버가 요청을 거부하는 장치가
아니라 브라우저가 응답을 읽지 못하게 하는 장치다 (spec §5-3).

- [ ] **Step 7: README 작성**

`workers/subscribe/README.md`:

````markdown
# 구독 접수 창구 (Cloudflare Worker)

설계: `docs/superpowers/specs/2026-09-10-subscription-worker-design.md`

## 엔드포인트

| 메서드 | 경로 | |
|---|---|---|
| `POST` | `/api/subscribe` | `{email, level}` → 명단 등록 + 환영 메일 |
| `GET` | `/api/unsubscribe?t=` | 확인 페이지. **지우지 않는다** |
| `POST` | `/api/unsubscribe` | 실제 삭제 |
| `GET` | `/api/export` | 명단 반환 (Bearer 인증) |

## 로컬

```bash
npm install
node --test test/          # 핸들러 테스트
npx wrangler dev           # 로컬 실행
```

## 배포

```bash
npx wrangler deploy
```

## 시크릿

| 이름 | 어디에 | 무엇 |
|---|---|---|
| `RESEND_API_KEY` | Worker + GitHub Actions | 메일 발송 |
| `SUBSCRIBERS_TOKEN` | Worker + GitHub Actions | `/api/export` 인증 |

```bash
npx wrangler secret put RESEND_API_KEY
npx wrangler secret put SUBSCRIBERS_TOKEN
```

**리포에 넣지 않는다.** 저장소가 PUBLIC 이다.

## 주의

- **구독자 이메일을 리포에 커밋하지 않는다.** `/api/export` 응답을 파일로 쓰지 말 것.
- **해지 GET 에서 삭제하지 않는다.** 메일 클라이언트의 링크 프리페치로 클릭 없이
  해지된다. 이 동작을 "단순화"하려는 수정은 되돌릴 것.
- **`ALLOWED_ORIGIN` 을 `*` 로 바꾸지 않는다.**

## 프로젝트 종료 시

```bash
npx wrangler kv key list --binding SUBSCRIBERS   # 남은 구독자 확인
npx wrangler kv namespace delete --binding SUBSCRIBERS
```
````

- [ ] **Step 8: 커밋**

```bash
git add workers/subscribe/README.md workers/subscribe/wrangler.toml
git commit -m "docs(worker): 배포 절차와 주의사항"
```

---

## 이 계획이 다루지 않는 것

- **구독 폼 UI** — 대시보드 작업이고 `A-3`(위치)이 미결이다
- **발송 코드** — `agents/notifier.py` 는 손대지 않는다. 조교님 순서 ⑤ 단계다
- **폼 공개** — 구독자 이메일 수집의 절차적 요건을 조교님께 확인한 뒤에 한다 (spec §9)
- **캡차(Turnstile)** — 지금 넣지 않는다. 폼 공개 후 KV 증가 추이를 보고
  봇 트래픽이 실제로 관측되면 그때 추가한다 (spec §7)
