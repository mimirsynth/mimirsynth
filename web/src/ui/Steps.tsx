import type { ReactNode } from "react";
import type { Tone } from "./Pill";

/** Pasos de un proceso en vertical (envío → revisión → ingesta). Cada `Step` lleva un título, un tono (color del punto) y su detalle. */
export function Steps({ children, label }: { children: ReactNode; /** What the steps are the story of, for a screen reader. */ label?: string }) {
  return <ol className="ms-steps" aria-label={label}>{children}</ol>;
}
export function Step({ title, tone = "neutral", children }: { title: string; tone?: Tone; children?: ReactNode }) {
  return (
    <li className="ms-step" data-tone={tone}>
      <div className="ms-step-title">{title}</div>
      <div className="ms-step-body">{children}</div>
    </li>
  );
}
