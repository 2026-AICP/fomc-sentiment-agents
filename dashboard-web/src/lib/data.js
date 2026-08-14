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

// 등급 표시 — 데이터의 원문("🔴 경고")에서 이모지를 뗀 텍스트 배지용.
// 실제 금융 사이트는 색 배지에 텍스트만 쓴다(investing.com 등).
export const gradeInfo = (g) => {
  const label = (g || "").replace(/[^가-힣]/g, "").trim() || "—";
  return { label, color: GRADE_COLOR[g] || "var(--muted)" };
};

// 지수 해석 라벨 — 실측 분포(일별 지수 대략 −0.85~+0.63, 중앙값 +0.05) 기준 구간.
export const toneLabel = (v) => {
  if (v == null) return null;
  if (v >= 0.30) return { text: "뚜렷한 낙관", color: "var(--up)" };
  if (v >= 0.10) return { text: "약한 낙관", color: "var(--up)" };
  if (v > -0.10) return { text: "중립", color: "var(--muted)" };
  if (v > -0.30) return { text: "약한 우려", color: "var(--dn)" };
  return { text: "뚜렷한 우려", color: "var(--dn)" };
};

// 발동 규칙 내부 코드 → 화면용 한국어 (내부 식별자를 그대로 노출하지 않는다)
export const FIRED_KO = {
  tone_shift: "톤 급변",
  divergence: "톤·시장 엇갈림",
  tone_vs_vix: "톤·변동성 이례",
  tone_vs_rate: "톤·금리 이탈",
};
export const firedNames = (arr) =>
  (arr || []).map((f) => FIRED_KO[f] || f).join(", ");

// 백엔드 detail 문자열 앞의 이모지(🔼 등) 제거
export const stripEmoji = (s) =>
  (s || "").replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, "").trim();
