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

// 구독 접수. 확인 메일 단계는 없다 — 넣는 즉시 명단에 들어간다(spec §3).
// 그래서 환영 메일이 선택이 아니다: 오등록된 사람이 자기가 등록됐음을 아는
// 유일한 통로다.
export async function subscribe(kv, sendMail, { email, level }) {
  // 정규화를 먼저 한다. 붙여넣기한 주소에 앞뒤 공백이 붙는 일이 흔한데,
  // isValidEmail 은 공백을 거부하므로 원본을 그대로 검증하면 멀쩡한 주소가
  // 막힌다. isValidEmail 은 표준형에 대해 엄격한 채로 둔다 — 안에서 trim 하면
  // 검증과 정규화 두 일을 겸하게 된다.
  const normalized = typeof email === 'string' ? normalizeEmail(email) : '';
  if (!isValidEmail(normalized)) {
    return { status: 400, body: { error: 'invalid_email' } };
  }

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
