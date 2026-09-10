// 테스트용 가짜 KV.
//
// 실제 Workers KV 와 다른 점 두 가지를 알고 쓴다.
//   - expirationTtl 을 무시한다. 만료 동작은 테스트하지 않는다
//     (Cloudflare 가 지우는 것이고 우리 코드의 책임이 아니다).
//   - list() 가 항상 한 번에 전부 준다. 실제 KV 는 1000건씩 끊어 주므로
//     핸들러는 cursor 루프를 돌아야 한다 — 그 루프는 여기서 1회로 끝난다.
export class FakeKV {
  constructor() {
    this.store = new Map();
  }

  async get(key, type) {
    const v = this.store.get(key);
    if (v === undefined) return null;
    return type === 'json' ? JSON.parse(v) : v;
  }

  async put(key, value) {
    this.store.set(key, value);
  }

  async delete(key) {
    this.store.delete(key);
  }

  async list({ prefix = '' } = {}) {
    const keys = [...this.store.keys()]
      .filter((k) => k.startsWith(prefix))
      .map((name) => ({ name }));
    return { keys, list_complete: true, cursor: undefined };
  }
}
