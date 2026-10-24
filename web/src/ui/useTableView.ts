import { useMemo, useState } from "react";
import type { ColFilter, ColSort, SortDir } from "./ColHead";

type Col<T> = { get: (row: T) => string | number; label?: (v: string) => string; exact?: boolean };  // exact: el filtro compara el valor entero (columnas de selección)

/** Orden y filtros por columna para tablas cuyos datos ya están en el cliente. Devuelve las filas visibles y los props de cada `ColHead`.
 *  Las opciones de un filtro de selección salen de los valores distintos de la columna. */
export function useTableView<T>(rows: T[], cols: Record<string, Col<T>>, initial?: { key: string; dir: SortDir }) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(initial ?? null);

  const view = useMemo(() => {
    let out = rows.filter((r) => Object.entries(filters).every(([k, v]) => !v || (cols[k] && (cols[k].exact ? String(cols[k].get(r)) === v : String(cols[k].get(r)).toLowerCase().includes(v.toLowerCase())))));
    if (sort && cols[sort.key]) {
      const g = cols[sort.key].get;
      out = [...out].sort((a, b) => { const x = g(a), y = g(b); const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "es", { numeric: true }); return sort.dir === "asc" ? c : -c; });
    }
    return out;
  }, [rows, filters, sort, cols]);

  const sortProps = (key: string): ColSort => ({
    dir: sort?.key === key ? sort.dir : null,
    onSort: () => setSort((s) => (s?.key !== key ? { key, dir: "desc" } : s.dir === "desc" ? { key, dir: "asc" } : null)),
  });
  const text = (key: string, placeholder?: string): ColFilter => ({ kind: "text", value: filters[key] ?? "", onChange: (v) => setFilters((f) => ({ ...f, [key]: v })), placeholder });
  const select = (key: string): ColFilter => {
    const counts = new Map<string, number>();
    rows.forEach((r) => { const v = String(cols[key].get(r)); counts.set(v, (counts.get(v) ?? 0) + 1); });
    return { kind: "select", value: filters[key] ?? "", onChange: (v) => setFilters((f) => ({ ...f, [key]: v })),
      options: [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0], "es")).map(([value, count]) => ({ value, label: cols[key].label?.(value) ?? (value || "(vacío)"), count })) };
  };
  const active = Object.values(filters).some(Boolean);
  return { rows: view, sortProps, text, select, active, clear: () => setFilters({}), total: rows.length };
}
