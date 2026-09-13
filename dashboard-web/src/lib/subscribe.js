// 구독 신청 — econpilot.org Worker 호출과 화면 문구.
// 문구는 Worker 응답 코드와 1:1 로 맞춘다 (docs/superpowers/specs/2026-09-13-alert-delivery-design.md §8).
// 이미 가입된 주소인지는 알리지 않는다 — Worker 가 항상 200 을 준다.
export const SUBSCRIBE_URL = "https://econpilot.org/api/subscribe";

export function messageFor(status) {
  switch (status) {
    case 200: return "신청되었습니다. 환영 메일을 확인해주세요 (스팸함도 확인해주세요).";
    case 400: return "이메일 주소를 확인해주세요.";
    case 429: return "잠시 후 다시 시도해주세요.";
    case 502: return "메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.";
    case null: return "연결에 실패했습니다.";
    default: return "잠시 후 다시 시도해주세요.";
  }
}

export async function submitSubscribe(email, fetchImpl = fetch) {
  try {
    const r = await fetchImpl(SUBSCRIBE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    return { ok: r.status === 200, message: messageFor(r.status) };
  } catch {
    return { ok: false, message: messageFor(null) };
  }
}
