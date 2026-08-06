// 공용 UI — KPI 카드·필·패널 (SentiBoard 토큰 기반)
export function Kpi({ eyebrow, value, meta, pill, pillColor }) {
  return (
    <div className="kpi">
      <div className="eb">{eyebrow}</div>
      <div className="big">
        {value}
        {pill && <Pill color={pillColor}>{pill}</Pill>}
      </div>
      {meta && <div className="mt">{meta}</div>}
    </div>
  );
}

export function Pill({ color = "var(--muted)", children }) {
  return (
    <span className="pill" style={{ background: `color-mix(in srgb, ${color} 15%, transparent)`, color }}>
      {children}
    </span>
  );
}

export function Panel({ title, cap, children }) {
  return (
    <div className="panel">
      {title && <div style={{ fontWeight: 700, marginBottom: 10 }}>{title}</div>}
      {children}
      {cap && <div className="cap">{cap}</div>}
    </div>
  );
}
