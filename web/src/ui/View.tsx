import { useTranslation } from "react-i18next";
import { useId, type ReactNode } from "react";
import { HelpTip } from "./Layout";

/* The anatomy of a view (DESIGN.md, the Screen Anatomy Rule): what a page or one of its tabs holds, top to bottom.
 *   ViewBar  — one row: the «i» with what the view is for, the filters, a short status, and on the right its actions.
 *   content  — exactly one of DataTable, a list of ListCard, SettingsGroup, Compare or EmptyState.
 *   Block    — a titled part under the content (history, what was set aside), with the same anatomy inside.
 * A screen never writes its own intro paragraph, heading, footnote or card: these are the only places they go. */

/** The bar that opens every view. `title` names the view for the «i» (it reads «What is “title”»); `help` is what the view is for, in a
 *  popover, never printed. `children` are the filters (Segments, SearchBar, fields with their label), `meta` a short status in the muted
 *  style (how many were analysed, when it was last measured), and `actions` the view's buttons on the right, at most one primary. Wraps on
 *  a narrow screen. Draws nothing when it has nothing. */
export function ViewBar({ title, help, meta, actions, children }: { title: string; help?: ReactNode; meta?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  if (!help && !meta && !actions && !children) return null;
  return (
    <div className="ms-viewbar">
      <div className="ms-viewbar-main">
        {help && <HelpTip title={title}>{help}</HelpTip>}
        {children}
        {meta && <span className="ms-viewbar-meta">{meta}</span>}
      </div>
      {actions && <div className="ms-viewbar-actions">{actions}</div>}
    </div>
  );
}

/** A titled part of a view, below its main content: its heading (the label style, with an optional count), its «i», its actions on the
 *  right, then its content at the full width. Not a card: the content draws its own surface (a table, list cards, a settings group). */
export function Block({ title, label, count, help, meta, actions, children }: { title: ReactNode; /** names the block for its «i» when `title` is
 *  not plain text (a heading with entity chips) */ label?: string; count?: number; help?: ReactNode; /** a short status beside the heading, in the muted style */ meta?: ReactNode;
  actions?: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <section className="ms-block" aria-labelledby={id}>
      <header className="ms-block-head">
        <h2 id={id} className="ms-block-title">{title}{count !== undefined && <span className="ms-block-count ms-data">{count}</span>}</h2>
        {help && <HelpTip title={label ?? (typeof title === "string" ? title : "")}>{help}</HelpTip>}
        {meta && <span className="ms-viewbar-meta">{meta}</span>}
        {actions && <div className="ms-block-actions">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

/** Two or more versions of the same thing side by side, in equal columns (now and proposed, before and after), each under its label;
 *  one under the other on a phone. */
export function Compare({ items }: { items: { label: string; children: ReactNode }[] }) {
  return (
    <div className="ms-compare">
      {items.map((it) => <div key={it.label} className="ms-compare-col"><div className="ms-compare-label">{it.label}</div><div className="ms-compare-body">{it.children}</div></div>)}
    </div>
  );
}

/** The buttons that close a dialog: right-aligned, Cancel (ghost) first and the dialog's action last. */
export function DialogActions({ children }: { children: ReactNode }) {
  return <div className="ms-dialog-actions">{children}</div>;
}

/** What shows while something loads: the empty state's place and type, announced to screen readers. `label`: what is being done
 *  («Searching…»), «Loading…» by default. */
export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return <div className="ms-empty" role="status">{label ?? t("Cargando…")}</div>;
}

/** A table cell with a main text and, under it, a secondary line in the muted style (a path, an origin, an identifier). */
export function CellText({ children, sub, data }: { children: ReactNode; sub?: ReactNode; /** the secondary line is data (an id, a path, a date) */ data?: boolean }) {
  return <div className="ms-cell"><div className="ms-cell-main">{children}</div>{sub && <div className={`ms-cell-sub${data ? " ms-data" : ""}`}>{sub}</div>}</div>;
}
