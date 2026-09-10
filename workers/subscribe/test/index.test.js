import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';
import { FakeKV } from './fake-kv.js';

const ORIGIN = 'https://aicp-econpilot.github.io';

function env(overrides = {}) {
  return { SUBSCRIBERS: new FakeKV(), SUBSCRIBERS_TOKEN: 's3cret', RESEND_API_KEY: 'k', ...overrides };
}

test('/api/export: 헤더 없으면 401', async () => {
  const res = await worker.fetch(new Request('https://econpilot.org/api/export'), env());
  assert.equal(res.status, 401);
});

test('/api/export: 틀린 토큰이면 401', async () => {
  const res = await worker.fetch(
    new Request('https://econpilot.org/api/export', { headers: { Authorization: 'Bearer wrong' } }), env());
  assert.equal(res.status, 401);
});

test('/api/export: 시크릿 미설정이면 Bearer undefined 로도 못 뚫는다', async () => {
  const res = await worker.fetch(
    new Request('https://econpilot.org/api/export', { headers: { Authorization: 'Bearer undefined' } }),
    env({ SUBSCRIBERS_TOKEN: undefined }));
  assert.equal(res.status, 401);
});

test('/api/export: 올바른 토큰이면 명단을 준다', async () => {
  const res = await worker.fetch(
    new Request('https://econpilot.org/api/export', { headers: { Authorization: 'Bearer s3cret' } }), env());
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { subscribers: [], count: 0 });
});

test('GET /api/unsubscribe: 페이지만 주고 아무것도 지우지 않는다', async () => {
  const e = env();
  await e.SUBSCRIBERS.put('tok:abc', 'somehash');
  await e.SUBSCRIBERS.put('sub:somehash', '{}');
  const res = await worker.fetch(new Request('https://econpilot.org/api/unsubscribe?t=abc'), e);
  assert.equal(res.status, 200);
  assert.equal(e.SUBSCRIBERS.store.size, 2, 'GET 은 삭제하면 안 된다');
});

test('POST /api/unsubscribe: 실제로 지운다', async () => {
  const e = env();
  await e.SUBSCRIBERS.put('tok:abc', 'somehash');
  await e.SUBSCRIBERS.put('sub:somehash', '{}');
  const res = await worker.fetch(
    new Request('https://econpilot.org/api/unsubscribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: 'abc' }),
    }), e);
  assert.equal(res.status, 200);
  assert.equal(e.SUBSCRIBERS.store.size, 0);
});

test('/api/subscribe: null 본문이면 400', async () => {
  const res = await worker.fetch(
    new Request('https://econpilot.org/api/subscribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: 'null',
    }), env());
  assert.equal(res.status, 400);
});

test('CORS: 허용 출처에만 헤더가 붙는다', async () => {
  const ok = await worker.fetch(
    new Request('https://econpilot.org/api/subscribe', { method: 'OPTIONS', headers: { Origin: ORIGIN } }), env());
  assert.equal(ok.headers.get('access-control-allow-origin'), ORIGIN);

  const bad = await worker.fetch(
    new Request('https://econpilot.org/api/subscribe', { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } }), env());
  assert.equal(bad.headers.get('access-control-allow-origin'), null);
});

test('알 수 없는 경로는 404', async () => {
  const res = await worker.fetch(new Request('https://econpilot.org/api/nope'), env());
  assert.equal(res.status, 404);
});
