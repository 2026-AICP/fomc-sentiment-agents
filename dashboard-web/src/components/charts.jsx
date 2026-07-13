// 차트 — recharts 다크 스타일 (Streamlit 버전의 Altair 톤과 맞춤)
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell,
} from "recharts";

const AXIS = { stroke: "#282d37", tick: { fill: "#9aa2ad", fontSize: 11 } };
const TIP = {
  contentStyle: { background: "#15181e", border: "1px solid #282d37", borderRadius: 10, fontSize: 12.5 },
  labelStyle: { color: "#e9ebef" },
};

export function IndexArea({ data, x = "date", y, color = "var(--accent)", height = 240 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
        <defs>
          <linearGradient id={`g-${y}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.55} />
            <stop offset="100%" stopColor={color} stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#20242c" vertical={false} />
        <XAxis dataKey={x} {...AXIS} minTickGap={40} />
        <YAxis {...AXIS} />
        <Tooltip {...TIP} />
        <ReferenceLine y={0} stroke="#9aa2ad" strokeDasharray="4 4" opacity={0.5} />
        <Area type="monotone" dataKey={y} stroke={color} strokeWidth={2.2}
          fill={`url(#g-${y})`}
          dot={data.length > 120 ? false : { r: 2.5, fill: color }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SimpleLine({ data, x = "date", series, height = 240 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke="#20242c" vertical={false} />
        <XAxis dataKey={x} {...AXIS} minTickGap={40} />
        <YAxis {...AXIS} />
        <Tooltip {...TIP} />
        <ReferenceLine y={0} stroke="#9aa2ad" strokeDasharray="4 4" opacity={0.5} />
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.name}
            stroke={s.color} strokeWidth={2} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// 이중 축 오버레이 — 감성(왼쪽) vs 시장지표(오른쪽) 관계 표시용
export function DualLine({ data, x = "month", left, right, height = 280 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 0, left: -14, bottom: 0 }}>
        <CartesianGrid stroke="#20242c" vertical={false} />
        <XAxis dataKey={x} {...AXIS} minTickGap={50} />
        <YAxis yAxisId="l" {...AXIS} />
        <YAxis yAxisId="r" orientation="right" {...AXIS} />
        <Tooltip {...TIP} />
        <ReferenceLine yAxisId="l" y={0} stroke="#9aa2ad" strokeDasharray="4 4" opacity={0.5} />
        <Line yAxisId="l" type="monotone" dataKey={left.key} name={left.name}
          stroke={left.color} strokeWidth={2.2} dot={false} />
        <Line yAxisId="r" type="monotone" dataKey={right.key} name={right.name}
          stroke={right.color} strokeWidth={1.8} dot={false} opacity={0.85} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function CompareBars({ data, x, y, colorBy, height = 230 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke="#20242c" vertical={false} />
        <XAxis dataKey={x} {...AXIS} />
        <YAxis {...AXIS} />
        <Tooltip {...TIP} />
        <Bar dataKey={y} radius={[6, 6, 0, 0]}>
          {data.map((d, i) => <Cell key={i} fill={colorBy(d)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
