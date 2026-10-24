import { Progress, Slider as MSlider, Stack, Text, type SliderProps } from "@mantine/core";
import type { ReactNode } from "react";

/** Deslizador con su etiqueta y valor, siempre con el mismo aspecto. */
export function SliderField({ label, value, onChange, min, max, step, width = 220 }: { label: ReactNode; value: number; onChange: (v: number) => void; min: number; max: number; step: number; width?: number }) {
  return (
    <div className="ms-field-row">
      <Text size="xs">{label}: <span className="ms-data">{value.toFixed(2)}</span></Text>
      <Slider w={width} min={min} max={max} step={step} value={value} onChange={onChange} />
    </div>
  );
}

/** Barra de progreso con texto. */
export function ProgressBar({ done, total, text }: { done: number; total: number; text: ReactNode }) {
  return (
    <Stack gap={4}>
      <Text size="xs" c="dimmed">{text}</Text>
      <Progress className="ms-progress" value={total ? (100 * done) / total : 0} animated />
    </Stack>
  );
}

/** Tarjeta de cifra con etiqueta y nota. */
export function StatCard({ label, value, hint, inline }: { label: string; value: number | string; hint?: string; inline?: boolean }) {
  return (
    <div className="ms-stat" data-inline={inline ? "" : undefined}>
      <Text size="sm" c="dimmed">{label}</Text>
      <div className="ms-stat-value">{value}</div>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </div>
  );
}

/** Deslizador de la aplicación (sin burbuja de valor). */
export function Slider(props: SliderProps) {
  return <MSlider label={null} {...props} className={`ms-slider${props.className ? ` ${props.className}` : ""}`} />;
}
