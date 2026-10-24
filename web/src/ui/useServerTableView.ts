import { useEffect, useState } from "react";
import type { ColSort, SortDir } from "./ColHead";

/** Orden, filtros y paginación de una tabla cuyos datos se piden al servidor. Un solo sitio para lo que antes se cableaba a mano en cada pantalla:
 *  los filtros de texto (`debounced`) se envían con 300 ms de espera, cualquier cambio de filtro u orden vuelve a la primera página y pulsar una cabecera
 *  recorre «primer sentido → contrario → sin orden» (`firstDir` fija cuál es el primero de cada columna; por defecto, de mayor a menor). */
export function useServerTableView<F extends Record<string, string>>(empty: F, opts: { debounced: (keyof F)[]; firstDir?: Record<string, SortDir>; pageSize?: number }) {
  const [f, setF] = useState<F>(empty);
  const [sent, setSent] = useState<F>(empty);
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(null);
  const [page, setPage] = useState({ offset: 0, limit: opts.pageSize ?? 50 });
  const first = (p: Partial<typeof page>) => setPage((x) => ({ ...x, ...p, offset: 0 }));

  const typed = opts.debounced.map((k) => f[k]).join("\u0000");
  useEffect(() => {
    const t = setTimeout(() => { setSent((s) => ({ ...s, ...Object.fromEntries(opts.debounced.map((k) => [k, f[k]])) })); first({}); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed]);

  /** Cambia filtros; los no debounced se envían ya, los de texto esperan. */
  const setFilter = (p: Partial<F>) => {
    setF((x) => ({ ...x, ...p }));
    const now = Object.fromEntries(Object.entries(p).filter(([k]) => !opts.debounced.includes(k)));
    if (Object.keys(now).length) { setSent((s) => ({ ...s, ...now })); first({}); }
  };
  const sortProps = (key: string): ColSort => ({
    dir: sort?.key === key ? sort.dir : null,
    onSort: () => {
      const a: SortDir = opts.firstDir?.[key] ?? "desc"; const b: SortDir = a === "asc" ? "desc" : "asc";
      setSort((s) => (!s || s.key !== key ? { key, dir: a } : s.dir === a ? { key, dir: b } : null));
      first({});
    },
  });
  const active = Object.entries(f).some(([k, v]) => v !== empty[k]);
  const clear = () => { setF(empty); setSent(empty); first({}); };
  return { f, sent, setFilter, sort, sortProps, page, setPage, active, clear };
}
