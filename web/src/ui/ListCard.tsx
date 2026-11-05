import type { ReactNode } from "react";

/** Tarjeta de una lista (hechos, episodios, pasajes, resultados): título y dato lateral, cuerpo, etiquetas, línea de datos y acciones.
 *  With `onOpen` the whole card opens on a click, and its title is a real button for the keyboard and screen readers (the card is not a
 *  `role="button"`, which would swallow its own actions). `invalid` marca lo que ya no es cierto. */
export function ListCard({ title, aside, tags, meta, actions, invalid, onOpen, children }:
  { title?: ReactNode; aside?: ReactNode; tags?: ReactNode; meta?: ReactNode; actions?: ReactNode; invalid?: boolean; onOpen?: () => void; children?: ReactNode }) {
  const head = onOpen && title
    ? <button type="button" className="ms-listcard-title ms-rowopen" onClick={(e) => { e.stopPropagation(); onOpen(); }}>{title}</button>
    : <div className="ms-listcard-title">{title}</div>;
  return (
    <div className="ms-listcard" data-invalid={invalid ? "" : undefined} data-clickable={onOpen ? "" : undefined} onClick={onOpen}>
      {(title || aside) && <div className="ms-listcard-head">{head}{aside && <div className="ms-listcard-aside">{aside}</div>}</div>}
      {children && <div className="ms-listcard-body">{children}</div>}
      {tags && <div className="ms-listcard-tags">{tags}</div>}
      {meta && <div className="ms-listcard-meta ms-data">{meta}</div>}
      {actions && <div className="ms-listcard-actions" onClick={(e) => e.stopPropagation()}>{actions}</div>}
    </div>
  );
}
