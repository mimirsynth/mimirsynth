import type { KeyboardEvent, ReactNode } from "react";

/** Tarjeta de una lista (hechos, episodios, pasajes, resultados): título y dato lateral, cuerpo, etiquetas, línea de datos y acciones.
 *  Con `onOpen` entera es un botón (ratón y teclado). `invalid` marca lo que ya no es cierto. */
export function ListCard({ title, aside, tags, meta, actions, invalid, onOpen, children }:
  { title?: ReactNode; aside?: ReactNode; tags?: ReactNode; meta?: ReactNode; actions?: ReactNode; invalid?: boolean; onOpen?: () => void; children?: ReactNode }) {
  const key = (e: KeyboardEvent) => { if (onOpen && (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) { e.preventDefault(); onOpen(); } };
  return (
    <div className="ms-listcard" data-invalid={invalid ? "" : undefined} data-clickable={onOpen ? "" : undefined}
      role={onOpen ? "button" : undefined} tabIndex={onOpen ? 0 : undefined} onClick={onOpen} onKeyDown={key}>
      {(title || aside) && <div className="ms-listcard-head"><div className="ms-listcard-title">{title}</div>{aside && <div className="ms-listcard-aside">{aside}</div>}</div>}
      {children && <div className="ms-listcard-body">{children}</div>}
      {tags && <div className="ms-listcard-tags">{tags}</div>}
      {meta && <div className="ms-listcard-meta ms-data">{meta}</div>}
      {actions && <div className="ms-listcard-actions" onClick={(e) => e.stopPropagation()}>{actions}</div>}
    </div>
  );
}
