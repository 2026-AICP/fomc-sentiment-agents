import { useState } from "react";
import { submitSubscribe } from "../lib/subscribe";

// 신호 탭 "알림 받기" — 이메일 하나만 받는다.
// 수집 안내문은 docs/notification_design.md §6-3 요구사항이다. 빼지 않는다.
export default function SubscribeForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);   // { ok, message }

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    const r = await submitSubscribe(email.trim());
    setResult(r);
    if (r.ok) setEmail("");
    setBusy(false);
  }

  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>알림 받기</div>
      <div style={{ fontSize: 13.5, marginBottom: 10 }}>
        경고 신호와 FOMC 일정(연 약 16회)을 이메일로 보내드립니다.
      </div>
      <form onSubmit={onSubmit} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input type="email" required value={email} placeholder="이메일 주소"
          aria-label="이메일 주소" onChange={(e) => setEmail(e.target.value)}
          style={{ flex: "1 1 220px", padding: "8px 10px", font: "inherit",
                   border: "1px solid var(--line)", borderRadius: 4,
                   background: "transparent", color: "inherit" }} />
        <button type="submit" disabled={busy}
          style={{ padding: "8px 16px", font: "inherit", fontWeight: 600,
                   cursor: busy ? "default" : "pointer", borderRadius: 4,
                   border: "1px solid var(--accent)", background: "var(--accent)",
                   color: "#fff", opacity: busy ? 0.6 : 1 }}>
          {busy ? "신청 중…" : "신청"}
        </button>
      </form>
      {result && (
        <div role="status" style={{ marginTop: 8, fontSize: 13.5,
             color: result.ok ? "var(--up)" : "var(--crit)" }}>
          {result.message}
        </div>
      )}
      <div className="cap" style={{ marginTop: 10, lineHeight: 1.7 }}>
        수집하는 정보: 이메일 주소 1개 · 사용 목적: 알림 발송 · 보관 기간: 프로젝트 종료 시 전량 삭제
        <br />
        해지: 모든 메일 하단 링크로 즉시 해지, 해지 시 주소 즉시 삭제
        <br />
        참고용이며 투자조언이 아닙니다.
      </div>
    </div>
  );
}
