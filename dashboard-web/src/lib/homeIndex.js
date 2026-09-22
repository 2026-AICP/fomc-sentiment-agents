/**
 * 홈 탭의 '통합 감성지수' 값 — 감성지수 탭과 같은 daily_headline 에서 읽는다.
 *
 * daily_signals.index 는 그날 처음 기록된 속보치라 고치지 않는다(과거 실시간 값
 * 덮어쓰기 금지). 그 기록이 결합값과 어긋나면 홈과 감성지수 탭이 다른 숫자를
 * 보여준다 — 2026-09-21 신호 기록 0.181(기자회견 반영 전) vs 감성지수 탭 0.284.
 * 등급·발동 규칙은 신호 기록 그대로 두고, 화면의 지수만 감성지수 탭과 맞춘다.
 * 그 날짜 결합값이 없을 때만 신호 기록 값을 쓴다(다른 날짜 값을 빌리지 않는다).
 */
export function homeIndex(signal, headline) {
  const row = (headline || []).find((r) => r.date === signal?.date);
  return row?.index ?? signal?.index ?? null;
}
