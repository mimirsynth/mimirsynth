import type { ReactNode } from "react";

/** Pantalla de ajustes: navegación de secciones a la izquierda y, a la derecha, la sección elegida. En pantalla estrecha la navegación pasa arriba. */
export function SettingsLayout({ nav, children }: { nav: ReactNode; children: ReactNode }) {
  return <div className="ms-settings"><div className="ms-settings-nav">{nav}</div><div className="ms-settings-body">{children}</div></div>;
}

/** Navegación vertical de secciones (una opción activa). */
export function SubNav({ value, onChange, items, label }: { value: string; onChange: (v: string) => void; items: ({ value: string; label: string } | { heading: string })[]; label: string }) {
  return (
    <nav className="ms-subnav" aria-label={label}>
      {items.map((i) => "heading" in i
        ? <div key={`h-${i.heading}`} className="ms-subnav-head">{i.heading}</div>
        : <button key={i.value} type="button" aria-current={value === i.value ? "page" : undefined} onClick={() => onChange(i.value)}>{i.label}</button>)}
    </nav>
  );
}

/** Sección de ajustes: título, descripción y una lista de filas separadas por filetes. */
export function SettingsGroup({ title, description, action, children }: { title: string; description?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="ms-setgroup">
      <header className="ms-setgroup-head"><div><h3>{title}</h3>{description && <p>{description}</p>}</div>{action}</header>
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
