import { useSearchParams } from "react-router-dom";

/** Pestaña activa guardada en la dirección (`?tab=…`): se puede enlazar, recargar y volver atrás. La pestaña por defecto no deja rastro en la dirección.
 *  `drop`: parámetros que se quitan al elegir una pestaña (los que eligieron la inicial, como el `?estado=` de Propuestas). */
export function useTabParam(initial: string, key = "tab", drop: string[] = []): [string, (v: string | null) => void] {
  const [sp, setSp] = useSearchParams();
  const value = sp.get(key) ?? initial;
  // from the address as it is now, not as some earlier render saw it: another control may have changed a parameter since (the
  // proposals' ?estado=), and a stale copy would put it back
  const set = (v: string | null) => {
    const p = new URLSearchParams(window.location.search);
    for (const k of drop) p.delete(k);
    if (!v || v === initial) p.delete(key); else p.set(key, v);
    setSp(p, { replace: true });
  };
  return [value, set];
}
