import type { ReactNode } from "react";

/** Tarjeta de una lista (hechos, episodios, pasajes, resultados): título y dato lateral, cuerpo, etiquetas, línea de datos y acciones.
 *  With `onOpen` the whole card opens on a click, and its title is a real button for the keyboard and screen readers (the card is not a
 *  `role="button"`, which would swallow its own actions). `invalid` marca lo que ya no es cierto.
 *  `notice`: what must be read before the body (that it may be superseded), set off by a rule. `note`: a sentence about the body (what
 *  it replaces, what replaced it), in the body's type. `anchor`: an id other cards can jump to; the card then takes the focus. */
export function ListCard({ title, aside, notice, note, tags, meta, actions, invalid, anchor, onOpen, children }:
  { title?: ReactNode; aside?: ReactNode; notice?: ReactNode; note?: ReactNode; tags?: ReactNode; meta?: ReactNode; actions?: ReactNode; invalid?: boolean;
    anchor?: string; onOpen?: () => void; children?: ReactNode }) {
  const head = onOpen && title
    ? <button type="button" className="ms-listcard-title ms-rowopen" onClick={(e) => { e.stopPropagation(); onOpen(); }}>{title}</button>
    : <div className="ms-listcard-title">{title}</div>;
  return (
    <div className="ms-listcard" id={anchor} tabIndex={anchor ? -1 : undefined} data-invalid={invalid ? "" : undefined} data-clickable={onOpen ? "" : undefined} onClick={onOpen}>
      {(title || aside) && <div className="ms-listcard-head">{head}{aside && <div className="ms-listcard-aside">{aside}</div>}</div>}
      {notice && <div className="ms-listcard-notice">{notice}</div>}
      {children && <div className="ms-listcard-body">{children}</div>}
      {note && <div className="ms-listcard-note">{note}</div>}
      {tags && <div className="ms-listcard-tags">{tags}</div>}
      {meta && <div className="ms-listcard-meta ms-data">{meta}</div>}
      {actions && <div className="ms-listcard-actions" onClick={(e) => e.stopPropagation()}>{actions}</div>}
    </div>
  );
}

/** A link, inside a sentence, to the card with this `anchor`. A real link and not a button: a button cannot break across lines, and what it
 *  names (a fact) is often longer than one. */
export function CardLink({ to, children }: { to: string; children: ReactNode }) {
  return <a className="ms-cardlink" href={`#${to}`} onClick={(e) => { e.preventDefault(); goToCard(to); }}>{children}</a>;
}

/** Jump to the card with this `anchor` and give it the focus; instant with reduced motion. */
export function goToCard(anchor: string) {
  const el = document.getElementById(anchor);
  if (!el) return;
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
  el.focus({ preventScroll: true });
}
