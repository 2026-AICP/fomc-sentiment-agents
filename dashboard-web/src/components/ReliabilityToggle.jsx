import { useState } from "react";

// '신뢰도 보기' — 기본은 접힘. 기억하지 않는다(페이지를 열 때마다 접힌 상태로 시작).
export function useShowReliability() {
  const [show, setShow] = useState(false);
  return [show, () => setShow((v) => !v)];
}

export function ReliabilityToggle({ show, onToggle, style }) {
  return (
    <button type="button" onClick={onToggle}
      style={{ background: "none", border: "1px solid var(--line)", borderRadius: 999,
               padding: "3px 10px", fontSize: 12, color: "var(--muted)", cursor: "pointer",
               font: "inherit", ...style }}>
      {show ? "신뢰도 숨기기 ▴" : "신뢰도 보기 ▾"}
    </button>
  );
}
