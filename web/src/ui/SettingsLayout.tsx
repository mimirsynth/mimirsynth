import { useId, type ReactNode } from "react";

/** Pantalla de ajustes: navegación de secciones a la izquierda y, a la derecha, la sección elegida. En pantalla estrecha la navegación pasa arriba. */
export function SettingsLayout({ nav, children }: { nav: ReactNode; children: ReactNode }) {
  return <div className="ms-settings"><div className="ms-settings-nav">{nav}</div><div className="ms-settings-body">{children}</div></div>;
}

type NavEntry = { value: string; label: string };

/** Vertical section navigation (one option active). A `heading` starts a group: the groups are set apart by a rule and the one
 *  holding the active option is marked, so it is clear at a glance which section a page belongs to. */
export function SubNav({ value, onChange, items, label }: { value: string; onChange: (v: string) => void; items: (NavEntry | { heading: string })[]; label: string }) {
  const id = useId();
  const groups: { heading: string; entries: NavEntry[] }[] = [];
  for (const i of items) {
    if ("heading" in i) groups.push({ heading: i.heading, entries: [] });
    else if (groups.length) groups[groups.length - 1].entries.push(i);
    else groups.push({ heading: "", entries: [i] });
  }
  return (
    <nav className="ms-subnav" aria-label={label}>
      {groups.map((g, n) => (
        <div key={`${n}-${g.heading}`} className="ms-subnav-group" role={g.heading ? "group" : undefined} aria-labelledby={g.heading ? `${id}-${n}` : undefined}
          data-active={g.entries.some((e) => e.value === value) || undefined}>
          {g.heading && <div id={`${id}-${n}`} className="ms-subnav-head">{g.heading}</div>}
          {g.entries.map((e) => <button key={e.value} type="button" aria-current={value === e.value ? "page" : undefined} onClick={() => onChange(e.value)}>{e.label}</button>)}
        </div>))}
    </nav>
  );
}

/** Sección de ajustes: título, descripción y una lista de filas separadas por filetes. */
export function SettingsGroup({ title, description, action, children }: { title: string; description?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="ms-setgroup">
      <header className="ms-setgroup-head"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</header>
      {children}
    </section>
  );
}

/** Fila de ajuste: nombre y ayuda a la izquierda, el control a la derecha (y debajo, sus acciones). */
export function SettingsRow({ label, help, children }: { label: string; help?: ReactNode; children: ReactNode }) {
  return (
    <div className="ms-setrow">
      <div><div className="ms-setrow-label">{label}</div>{help && <div className="ms-setrow-help">{help}</div>}</div>
      <div className="ms-setrow-ctl">{children}</div>
    </div>
  );
}

/** Contenido libre dentro de una sección (tablas, formularios): con el mismo margen que las filas. */
export function SettingsBody({ children }: { children: ReactNode }) {
  return <div className="ms-setgroup-body">{children}</div>;
}
