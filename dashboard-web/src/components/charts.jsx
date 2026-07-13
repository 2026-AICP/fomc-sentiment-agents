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
