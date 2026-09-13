// node --test dashboard-web/src/lib/subscribe.test.js
// dashboard-web/package.json 이 "type": "module" 이라 ESM import 가 그대로 돈다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { SUBSCRIBE_URL, messageFor, submitSubscribe } from "./subscribe.js";

test("messageFor: Worker 응답 코드와 1:1", () => {
  assert.match(messageFor(200), /신청되었습니다/);
  assert.match(messageFor(400), /이메일 주소를 확인/);
  assert.match(messageFor(429), /잠시 후 다시/);
  assert.match(messageFor(502), /메일 발송에 실패/);
  assert.match(messageFor(null), /연결에 실패/);
  assert.match(messageFor(500), /잠시 후 다시/);
});

test("submitSubscribe: 이메일만 JSON 으로 POST 하고 200 이면 ok", async () => {
  const calls = [];
  const fake = async (url, init) => { calls.push({ url, init }); return { status: 200 }; };
  const r = await submitSubscribe("prof@uni.ac.kr", fake);
  assert.equal(r.ok, true);
  assert.equal(calls[0].url, SUBSCRIBE_URL);
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { email: "prof@uni.ac.kr" });
});

test("submitSubscribe: 200 이 아니면 ok 아님", async () => {
  const r = await submitSubscribe("x", async () => ({ status: 400 }));
  assert.equal(r.ok, false);
  assert.match(r.message, /이메일 주소를 확인/);
});

test("submitSubscribe: 네트워크 오류는 연결 실패 문구", async () => {
  const r = await submitSubscribe("x", async () => { throw new TypeError("offline"); });
  assert.deepEqual(r, { ok: false, message: messageFor(null) });
});
