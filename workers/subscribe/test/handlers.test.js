import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isValidEmail, normalizeEmail, sha256Hex, randomToken, LEVELS, subscribe,
  unsubscribe, exportSubscribers,
} from '../src/handlers.js';
import { FakeKV } from './fake-kv.js';

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

test('subscribe: 비문자열 입력에 터지지 않고 400 을 준다', async () => {
  const kv = new FakeKV();
  const { sent, sendMail } = collectMail();

  for (const bad of [null, undefined, 42, {}, []]) {
    const res = await subscribe(kv, sendMail, { email: bad, level: 'alert' });
    assert.equal(res.status, 400, `${JSON.stringify(bad)} 는 400 이어야 한다`);
  }
  assert.equal(kv.store.size, 0);
  assert.equal(sent.length, 0);
});

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
