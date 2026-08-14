import { useJson, fmt, gradeInfo, firedNames, stripEmoji } from "../lib/data";
import { Pill } from "../components/ui";

// 네 가지 판정 규칙 — 내부 코드명 대신 화면용 이름으로 설명한다.
const SIGNAL_DEFS = [
  {
    code: "A", name: "톤 급변", color: "var(--warn)",
    what: "직전 회의보다 어조가 크게 달라졌습니다.",
    why: "연준의 기조가 바뀌는 시점으로, 시장이 발표문을 다시 읽는 순간입니다.",
  },
  {
    code: "B", name: "톤·시장 엇갈림", color: "var(--crit)",
    what: "연준의 어조와 발표 당일 주가의 방향이 서로 반대입니다. 둘 다 충분히 클 때만 발동합니다.",
    why: "과거 위기 구간에서 평소보다 2.4배 자주 나타났습니다. 위기를 예측하는 것은 아니며, 자세히 살펴볼 필요가 있다는 표시입니다.",
  },
  {
    code: "C", name: "톤·변동성 이례", color: "var(--blue)",
    what: "어조가 좋아졌는데도 변동성지수(VIX)가 함께 오르는 등, 평소의 반대 방향 관계가 깨졌습니다.",
    why: "발표문과 시장 심리가 따로 움직이는 드문 경우입니다.",
  },
  {
    code: "D", name: "톤·금리 이탈", color: "var(--accent)",
    what: "어조와 2년 만기 국채금리의 움직임이 평소의 관계에서 벗어났습니다.",
    why: "2년물 금리는 정책 기대를 민감하게 반영하므로, 시장의 해석이 발표문과 어긋났다는 뜻입니다.",
  },
];

const GRADES = [
  { label: "경고", color: "var(--crit)",
    d: "어조와 시장 반응이 크게 어긋났습니다. 그날 어떤 일이 있었는지 확인해볼 만합니다." },
  { label: "주의", color: "var(--warn)",
    d: "규칙 중 하나 이상이 발동했습니다. 가볍게 살펴보시기 바랍니다." },
  { label: "정합", color: "var(--up)",
    d: "어조와 시장이 같은 방향으로 움직였습니다." },
  { label: "중립", color: "var(--muted)",
    d: "판단할 만큼 변화가 크지 않았습니다." },
];

export default function Signals() {
  const { data: alerts } = useJson("alerts");
  if (!alerts) return <div className="loading">데이터를 불러오는 중입니다.</div>;

  return (
    <>
      <h1>신호</h1>
      <p className="sub">
        회의마다 연준의 어조와 시장 반응을 미리 정한 네 가지 규칙으로 비교합니다.
        매수·매도 권고가 아니라, 살펴볼 만한 날을 표시하는 알림입니다.
      </p>

      <h2 className="sec" style={{ marginTop: 8 }}>네 가지 규칙</h2>
      <div className="cards2">
        {SIGNAL_DEFS.map((s) => (
          <div className="panel" key={s.code} style={{ marginTop: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span className="pill" style={{ background: `color-mix(in srgb, ${s.color} 15%, transparent)`, color: s.color, fontSize: 13 }}>{s.code}</span>
              <b>{s.name}</b>
            </div>
            <div style={{ fontSize: 13.5 }}>{s.what}</div>
            <div className="cap">{s.why}</div>
          </div>
        ))}
      </div>
      <div className="note">
        발동 기준선은 임의로 정하지 않고, 과거 자료의 분포에서 상위 구간에 해당하는 값으로
        정했습니다.
      </div>

      <h2 className="sec">등급은 어떻게 읽나요?</h2>
      <div className="kpis">
        {GRADES.map((x) => (
          <div className="kpi" key={x.label}>
            <div className="big" style={{ fontSize: 20, color: x.color }}>{x.label}</div>
            <div className="mt">{x.d}</div>
          </div>
        ))}
      </div>

      <h2 className="sec">회의별 기록 (전체 {alerts.length}건, 최신순)</h2>
      {alerts.slice().reverse().map((a) => {
        const gi = gradeInfo(a.grade);
        return (
          <div className="alert-row" key={a.date}>
            <div>
              <div className="d1">{a.date} · {stripEmoji(a.detail) || "특이 사항 없음"}</div>
              <div className="d2">
                톤 {fmt(a.tone)} · 시장 반응 {a.reaction == null ? "—" : `${fmt(a.reaction, 2)}%`} ·{" "}
                {a.fired.length ? `발동 규칙: ${firedNames(a.fired)}` : "발동한 규칙 없음"}
              </div>
            </div>
            <Pill color={gi.color}>{gi.label}</Pill>
          </div>
        );
      })}
    </>
  );
}
