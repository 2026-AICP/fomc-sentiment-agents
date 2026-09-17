// 통합지수의 연준 값이 어떤 문서들로 계산됐는지 — 화면 표시용 (계산은 파이프라인이 한다).
//
// 연준 축은 도착한 문서끼리만 표준화 점수를 평균한다: 성명문(회의 당일) → 기자회견 원고
// (며칠 뒤) → 회의록(약 3주 뒤). 확정판은 회의록이 들어올 때 한 번만 기록되므로
// (agents/graph.py: fed_final = "minutes" in axes) 확정 여부도 회의록 도착으로 판단한다.
// ★axis_status 의 complete(n_axes == expected)로 판단하면 안 된다 — 2011~2018 비분기
//   회의는 기자회견을 기대하지만 원고가 없어, 회의록이 와서 확정됐는데도 영원히 미완성이 된다.
const DOCS = [["statement", "성명문"], ["presser", "기자회견"], ["minutes", "회의록"]];

/** onDate 이전(포함) 가장 최근 회의의 상태. 회의가 없으면 null. */
export function fedAxisStatus(axisRows, onDate) {
  const rows = (axisRows || []).filter((r) => !onDate || r.date <= onDate);
  const r = rows[rows.length - 1];
  if (!r) return null;
  const expected = r.expected ?? DOCS.length;
  const final = !!r.minutes;
  const docs = DOCS
    // 기자회견이 없던 시기(기대 문서 2개)에는 목록에서 뺀다
    .filter(([key]) => !(key === "presser" && expected < DOCS.length && !r.presser))
    .map(([key, name]) => `${name} ${r[key] ? "✓" : final ? "없음" : "대기"}`);
  return {
    date: r.date,
    final,
    badge: final ? "확정" : `잠정 · ${r.n_axes}/${expected}`,
    docsText: docs.join(" · "),
  };
}
