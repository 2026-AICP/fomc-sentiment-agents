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
