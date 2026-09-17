// node --test dashboard-web/src/lib/fedAxis.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { fedAxisStatus } from "./fedAxis.js";

const row = (date, s, p, m, expected = 3) => ({
  date, statement: s, presser: p, minutes: m,
  n_axes: [s, p, m].filter(Boolean).length, expected,
  complete: [s, p, m].filter(Boolean).length === expected,
});

test("회의 당일 — 성명문만 있으면 잠정 1/3, 나머지는 대기", () => {
  const st = fedAxisStatus([row("2026-09-16", true, false, false)]);
  assert.equal(st.final, false);
  assert.equal(st.badge, "잠정 · 1/3");
  assert.equal(st.docsText, "성명문 ✓ · 기자회견 대기 · 회의록 대기");
});

test("기자회견 원고까지 — 잠정 2/3", () => {
  const st = fedAxisStatus([row("2026-09-16", true, true, false)]);
  assert.equal(st.badge, "잠정 · 2/3");
  assert.equal(st.docsText, "성명문 ✓ · 기자회견 ✓ · 회의록 대기");
});

test("회의록까지 — 확정", () => {
  const st = fedAxisStatus([row("2026-07-29", true, true, true)]);
  assert.equal(st.final, true);
  assert.equal(st.badge, "확정");
  assert.equal(st.docsText, "성명문 ✓ · 기자회견 ✓ · 회의록 ✓");
});

test("회의록은 왔는데 기자회견 원고가 없는 회의 — complete 가 거짓이어도 확정, 빠진 문서는 '없음'", () => {
  const st = fedAxisStatus([row("2013-03-20", true, false, true)]);
  assert.equal(st.final, true);
  assert.equal(st.badge, "확정");
  assert.equal(st.docsText, "성명문 ✓ · 기자회견 없음 · 회의록 ✓");
});

test("기자회견이 없던 시기(기대 2개)에는 기자회견을 목록에서 뺀다", () => {
  const st = fedAxisStatus([row("2008-10-29", true, false, true, 2)]);
  assert.equal(st.docsText, "성명문 ✓ · 회의록 ✓");
});

test("onDate 이전의 가장 최근 회의를 고른다", () => {
  const rows = [row("2026-07-29", true, true, true), row("2026-09-16", true, false, false)];
  assert.equal(fedAxisStatus(rows, "2026-09-15").date, "2026-07-29");
  assert.equal(fedAxisStatus(rows, "2026-09-16").date, "2026-09-16");
  assert.equal(fedAxisStatus(rows).date, "2026-09-16");
});

test("데이터가 없으면 null", () => {
  assert.equal(fedAxisStatus(null), null);
  assert.equal(fedAxisStatus([], "2026-09-16"), null);
});
