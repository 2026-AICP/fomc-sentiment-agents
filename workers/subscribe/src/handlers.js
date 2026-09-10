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
