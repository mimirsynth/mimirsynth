import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";

/** Leyenda plegable sobre un lienzo: secciones con elementos que se pueden activar o apagar (ratón y teclado). */
export function Legend({ open, onToggle, children }: { open: boolean; onToggle: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="ms-legend-box">
      <button type="button" className="ms-legend-head" aria-expanded={open} onClick={onToggle}><span>{t("Leyenda")}</span><span>{open ? "▾" : "▸"}</span></button>
      {open && children}
    </div>
  );
}
export function LegendSection({ children }: { children: ReactNode }) {
  return <div className="ms-legend-sec">{children}</div>;
}
/** `dot`: color del punto (un tipo de entidad); sin él, una línea (una relación). */
export function LegendItem({ label, count, dot, off, onClick }: { label: string; count: number; dot?: string; off?: boolean; onClick: () => void }) {
  return (
    <button type="button" className="ms-legend-item" data-off={off ? "" : undefined} title={label} onClick={onClick}>
      {dot ? <span className="ms-legend-dot" style={{ background: dot }} /> : <span className="ms-legend-line" />}<span className="ms-legend-label">{label}</span> <span className="ms-legend-n">{count}</span>
    </button>
  );
}
