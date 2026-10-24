import type { KeyboardEvent } from "react";

type Item = { value: string; label: string; count?: number };

/** Selector de una opción entre varias, en píldoras (la misma forma que las etiquetas). La activa va rellena; cada opción puede llevar un contador.
 *  Con `label` lleva delante su rótulo («Estado»), como los campos de una barra de filtros. Con teclado: Tab entra en el grupo (en la opción activa) y las flechas cambian de opción. */
export function Segments({ value, onChange, data, label }: { value: string; onChange: (v: string) => void; data: (string | Item)[]; label?: string; size?: string }) {
  const items = data.map((d) => (typeof d === "string" ? { value: d, label: d } : d));
  const move = (e: KeyboardEvent, i: number) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = items[(i + step + items.length) % items.length];
    onChange(next.value);
    (e.currentTarget.parentElement?.children[(i + step + items.length) % items.length] as HTMLElement | undefined)?.focus();
  };
  const focusable = items.some((i) => i.value === value) ? value : items[0]?.value;
  return (
    <div className="ms-segments" role="radiogroup" aria-label={label}>
      {label && <span className="ms-segments-label" aria-hidden>{label}</span>}
      {items.map((i, n) => (
        <button key={i.value} type="button" role="radio" aria-checked={value === i.value} tabIndex={i.value === focusable ? 0 : -1} className="ms-seg" data-active={value === i.value ? "" : undefined}
          onClick={() => onChange(i.value)} onKeyDown={(e) => move(e, n)}>
          {i.label}
          {i.count !== undefined && <span className="ms-seg-count">{i.count}</span>}
        </button>
      ))}
    </div>
  );
}
