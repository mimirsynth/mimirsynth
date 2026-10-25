import { useTranslation } from "react-i18next";
import { T, locale } from "../i18n";
import { Text } from "@mantine/core";
import { useEffect, useRef, useState, type ReactNode } from "react";

/** Gráficas SVG sencillas y sin dependencias; los colores salen de los tokens del tema (claro y oscuro). */
import { SERIES } from "./palette";
export { SERIES };

export type AreaSeries = { name: string; color?: string; values: number[] };

/** Tamaño en píxeles del contenedor, siguiendo sus cambios (ventana, paneles que se abren…). */
function useBox<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setBox({ w: Math.floor(e.contentRect.width), h: Math.floor(e.contentRect.height) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, box] as const;
}

/** Líneas con relleno suave, una por serie, sobre el mismo eje. Ocupa todo el ancho y el alto disponibles de su contenedor: el SVG se dibuja al tamaño real, sin deformar el texto. */
export function AreaChart({ series, labels, height = 220 }: { series: AreaSeries[]; labels: string[]; height?: number }) {
  const { t } = useTranslation();
  const [ref, box] = useBox<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const W = Math.max(box.w, 240), H = Math.max(box.h, height), P = { l: 36, r: 10, t: 10, b: 26 };
  const n = Math.max(labels.length, 2);
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const step = max <= 4 ? 1 : Math.pow(10, Math.floor(Math.log10(max / 4))) * ([1, 2, 2.5, 5, 10].find((m) => (max / (m * Math.pow(10, Math.floor(Math.log10(max / 4))))) <= 4) ?? 10);
  const nice = max <= 4 ? max : Math.ceil(max / step) * step;
  const x = (i: number) => P.l + (i * (W - P.l - P.r)) / (n - 1);
  const y = (v: number) => P.t + (1 - v / nice) * (H - P.t - P.b);
  const ticks = Array.from({ length: Math.floor(nice / step) + 1 }, (_, i) => i * step).filter((t) => t <= nice);
  const fmtD = (d: string) => new Date(d).toLocaleDateString(locale(), { day: "numeric", month: "short" });
  const nLabels = Math.max(2, Math.min(8, Math.floor((W - P.l) / 90)));
  const xi = Array.from({ length: nLabels }, (_, k) => Math.round((k * (n - 1)) / (nLabels - 1)));
  return (
    <div className="ms-chart">
      <div ref={ref} className="ms-chart-box" style={{ minHeight: height }}>
        {hover !== null && box.w > 0 && (
          <div className="ms-chart-tip" style={{ left: Math.min(Math.max(x(hover) + 12, 4), W - 190), top: 8 }}>
            <div className="ms-chart-tip-title">{t("Semana del")} {fmtD(labels[hover])}</div>
            {series.map((s, k) => <div key={s.name}><i style={{ background: s.color ?? SERIES[k % SERIES.length] }} />{s.name}<b>{s.values[hover] ?? 0}</b></div>)}
          </div>)}
        {box.w > 0 && (
          <svg width={W} height={H} role="img" style={{ position: "absolute", inset: 0 }}
            onPointerMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); const i = Math.round(((e.clientX - r.left - P.l) / (W - P.l - P.r)) * (n - 1)); setHover(i >= 0 && i < n && e.clientX - r.left >= P.l - 8 ? i : null); }}
            onPointerLeave={() => setHover(null)}>
            {ticks.map((t) => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="ms-chart-grid" /><text x={P.l - 6} y={y(t) + 4} textAnchor="end" className="ms-chart-tick">{Math.round(t)}</text></g>)}
            {series.map((s, k) => {
              const c = s.color ?? SERIES[k % SERIES.length];
              const pts = s.values.map((v, i) => `${x(i)},${y(v)}`);
              return (
                <g key={s.name}>
                  <polygon points={`${x(0)},${y(0)} ${pts.join(" ")} ${x(s.values.length - 1)},${y(0)}`} fill={c} opacity={0.14} />
                  <polyline points={pts.join(" ")} fill="none" stroke={c} strokeWidth={2} strokeLinejoin="round" />
                  {s.values.map((v, i) => v > 0 && <circle key={i} cx={x(i)} cy={y(v)} r={hover === i ? 5 : 3} fill={c} />)}
                </g>);
            })}
            {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} className="ms-chart-cross" />}
            {hover !== null && series.map((s, k) => <circle key={s.name} cx={x(hover)} cy={y(s.values[hover] ?? 0)} r={5} fill="var(--ms-raised)" stroke={s.color ?? SERIES[k % SERIES.length]} strokeWidth={2} />)}
            {xi.map((i, k) => labels[i] && <text key={k} x={x(i)} y={H - 7} textAnchor={k === 0 ? "start" : k === xi.length - 1 ? "end" : "middle"} className="ms-chart-tick">{fmtD(labels[i])}</text>)}
          </svg>)}
      </div>
      <div className="ms-legend">{series.map((s, k) => <span key={s.name}><i style={{ background: s.color ?? SERIES[k % SERIES.length] }} />{s.name} <b>{s.values.reduce((a, b) => a + b, 0)}</b></span>)}</div>
    </div>
  );
}

export type Slice = { label: string; value: number; color?: string };

/** Anillo con el total en el centro y leyenda con porcentajes. Se escala para llenar el alto y el ancho que le deja su contenedor. */
export function Donut({ slices, center }: { slices: Slice[]; center?: ReactNode }) {
  const total = slices.reduce((a, s) => a + s.value, 0);
  const R = 52, C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <div className="ms-donut">
      <div className="ms-donut-art">
        <svg viewBox="0 0 140 140" role="img" preserveAspectRatio="xMidYMid meet">
          <circle cx={70} cy={70} r={R} fill="none" className="ms-chart-grid" strokeWidth={16} />
          {total > 0 && slices.map((s, k) => {
            const len = (s.value / total) * C;
            const el = <circle key={s.label} cx={70} cy={70} r={R} fill="none" stroke={s.color ?? SERIES[k % SERIES.length]} strokeWidth={16} strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-acc} transform="rotate(-90 70 70)"><title>{`${s.label}: ${s.value}`}</title></circle>;
            acc += len; return el;
          })}
          <text x={70} y={68} textAnchor="middle" className="ms-donut-num">{total}</text>
          <text x={70} y={86} textAnchor="middle" className="ms-donut-sub">{center ?? "total"}</text>
        </svg>
      </div>
      <div className="ms-legend ms-legend-col">{slices.map((s, k) => <span key={s.label}><i style={{ background: s.color ?? SERIES[k % SERIES.length] }} />{s.label} <b>{s.value}</b>{total > 0 && <em>{Math.round((100 * s.value) / total)} %</em>}</span>)}</div>
    </div>
  );
}

export type BarItem = { label: string; value: number; hint?: string };

/** Lista de barras horizontales proporcionales al mayor valor. */
export function BarList({ items, color = SERIES[0], empty = T("Sin datos") }: { items: BarItem[]; color?: string; empty?: string }) {
  const { t } = useTranslation();
  const max = Math.max(1, ...items.map((i) => i.value));
  if (items.length === 0) return <Text size="sm" c="dimmed">{t(empty)}</Text>;
  return (
    <div className="ms-bars">
      {items.map((i) => (
        <div key={i.label} className="ms-bar-row" title={i.hint}>
          <span className="ms-bar-label">{i.label}</span>
          <span className="ms-bar-track"><span className="ms-bar-fill" style={{ width: `${(100 * i.value) / max}%`, background: color }} /></span>
          <span className="ms-bar-value">{i.value}</span>
        </div>))}
    </div>
  );
}
