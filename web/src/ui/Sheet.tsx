import type { ReactNode } from "react";

/** A record's own data as a short sheet: each value under its label (who sent it, when, from where, what a model said of it). It is a
 *  section of the panel it sits in, ruled off from the content, not a card inside a card. `label` names it for screen readers and heads it. */
export function Sheet({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <section className={`ms-sheet${className ? ` ${className}` : ""}`} aria-label={label}>
      <h3 className="ms-section-title">{label}</h3>
      <dl className="ms-sheet-list">{children}</dl>
    </section>
  );
}

/** One row of a Sheet: its label, then its value. `wide`: a longer value that takes the whole width when the sheet lays its rows side by side. */
export function SheetRow({ term, children, wide }: { term: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className="ms-sheet-row" data-wide={wide ? "" : undefined}>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}
