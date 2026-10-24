import { Badge } from "@mantine/core";
import type { ReactNode } from "react";

export type Tone = "neutral" | "success" | "warn" | "danger" | "alt";
const MAP: Record<string, Tone> = { teal: "success", green: "success", lime: "success", red: "danger", pink: "danger", yellow: "warn", orange: "warn", grape: "alt", violet: "alt", purple: "alt", indigo: "alt" };

/** Etiqueta de la aplicación. Una sola forma (píldora) y un solo conjunto de tonos en todas las pantallas.
 *  `strong` la rellena con el color de acento (p. ej. el contador de una pestaña activa). `circle` la ajusta a un contador. */
export function Pill({ tone, color, strong, circle, size = "sm", title, children, className }:
  { tone?: Tone; color?: string; strong?: boolean; circle?: boolean; size?: "xs" | "sm" | "md"; title?: string; children?: ReactNode; className?: string }) {
  const t: Tone = tone ?? MAP[color ?? ""] ?? "neutral";
  return (
    <Badge radius="sm" size={size} circle={circle} title={title} data-tone={t} data-strong={strong ? "" : undefined} className={`ms-pill${className ? ` ${className}` : ""}`}>
      {children}
    </Badge>
  );
}
