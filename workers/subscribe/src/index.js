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

// title·message 를 이스케이프 없이 그대로 삽입한다. 반드시 하드코딩된
// 문자열만 넘길 것 — 요청에서 온 값을 절대 넣지 않는다.
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
      // request.json() 은 리터럴 null·숫자·문자열도 성공시킨다. 객체가 아니면
      // 아래에서 payload.email 이 터지므로 여기서 걸러낸다.
      if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
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
      // 시크릿이 안 걸려 있으면 무조건 거부한다. 없는 채로 비교하면 비교 대상이
      // "Bearer undefined" 라는 문자열이 되어, 그 헤더를 보낸 아무나 통과한다.
      const expected = env.SUBSCRIBERS_TOKEN;
      const auth = request.headers.get('Authorization') || '';
      if (!expected || auth !== `Bearer ${expected}`) {
        return json({ error: 'unauthorized' }, 401, origin);
      }
      const result = await exportSubscribers(env.SUBSCRIBERS);
      return json(result.body, result.status, origin);
    }

    return json({ error: 'not_found' }, 404, origin);
  },
};
