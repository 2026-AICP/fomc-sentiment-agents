// 데이터 훅 — public/data/*.json (파이썬 export_dashboard.py 산출)을 fetch.
// 프론트는 계산하지 않고 표시만 한다 (환각 차단 원칙).
import { useEffect, useState } from "react";

const cache = {};

export function useJson(name) {
  const [data, setData] = useState(cache[name] ?? null);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (cache[name]) return;
    fetch(`/data/${name}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${name}: HTTP ${r.status}`))))
      .then((d) => { cache[name] = d; setData(d); })
      .catch(setError);
  }, [name]);
  return { data, error };
}

export const fmt = (v, d = 3, sign = true) =>
  v == null ? "—" : `${sign && v > 0 ? "+" : ""}${v.toFixed(d)}`;

export const GRADE_COLOR = {
  "🟢 정합": "var(--good)",
  "🔴 경고": "var(--bad)",
  "⚠️ 주의": "var(--warn)",
  "⚪ 중립": "var(--muted)",
};
