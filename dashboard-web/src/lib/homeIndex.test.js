// node --test dashboard-web/src/lib/homeIndex.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { homeIndex } from "./homeIndex.js";

const headline = [
  { date: "2026-09-20", index: 0.7068 },
  { date: "2026-09-21", index: 0.2844 },
];

test("같은 날짜의 감성지수 탭 값(daily_headline)을 쓴다", () => {
  // 2026-09-21: 신호 기록은 기자회견 반영 전 0.181, 감성지수 탭은 반영 후 0.284
  assert.equal(homeIndex({ date: "2026-09-21", index: 0.181 }, headline), 0.2844);
});

test("그 날짜 결합값이 없으면 신호 기록 값 — 다른 날짜 값을 빌려오지 않는다", () => {
  assert.equal(homeIndex({ date: "2026-09-22", index: 0.5 }, headline), 0.5);
});

test("결합값이 비어 있으면(null) 신호 기록 값", () => {
  assert.equal(homeIndex({ date: "2026-09-21", index: 0.181 },
    [{ date: "2026-09-21", index: null }]), 0.181);
});
