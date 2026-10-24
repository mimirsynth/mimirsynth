import { useSearchParams } from "react-router-dom";

/** Pestaña activa guardada en la dirección (`?tab=…`): se puede enlazar, recargar y volver atrás. La pestaña por defecto no deja rastro en la dirección. */
export function useTabParam(initial: string, key = "tab"): [string, (v: string | null) => void] {
  const [sp, setSp] = useSearchParams();
  const value = sp.get(key) ?? initial;
  const set = (v: string | null) => { const p = new URLSearchParams(sp); !v || v === initial ? p.delete(key) : p.set(key, v); setSp(p, { replace: true }); };
  return [value, set];
}
