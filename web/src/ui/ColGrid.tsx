import type { ReactNode } from "react";

/** Rejilla de tarjetas: reparte en las columnas que caben con un ancho mínimo (`min`, 320 px por defecto). `span` hace que un hijo ocupe todo el ancho. */
export function ColGrid({ children, min = 320 }: { children: ReactNode; min?: number }) {
  return <div className="ms-colgrid" style={{ ["--min" as string]: `${min}px` }}>{children}</div>;
}
