import { Group } from "@mantine/core";
import type { ReactNode } from "react";
import { ClearFilters } from "./ClearFilters";
import { SelectField, TextField } from "./Fields";
import { SearchBar } from "./SearchBar";

export type BarFilter =
  | { kind: "select"; label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string; count?: number }[]; allLabel?: string; width?: number; clearable?: boolean }
  | { kind: "date"; label: string; value: string; onChange: (v: string) => void };

/** Barra de filtros para listas de tarjetas (Diario, Hechos…), donde no hay cabeceras de columna: búsqueda a la izquierda y, con su rótulo, un campo por filtro
 *  (selección o fecha). La misma forma en todas las pantallas; las tablas usan `ColHead` en su cabecera y las vistas alternativas de una lista, `Tabs`. */
export function FilterBar({ search, filters = [], active, onClear, children }:
  { search: { value: string; onChange: (v: string) => void; placeholder: string }; filters?: BarFilter[]; active?: boolean; onClear?: () => void; children?: ReactNode }) {
  return (
    <div className="ms-filterbar">
      <Group gap="xs" align="flex-end" wrap="wrap">
        <SearchBar value={search.value} onChange={search.onChange} placeholder={search.placeholder} />
        {filters.map((f) => f.kind === "select"
          ? <SelectField key={f.label} size="sm" label={f.label} w={f.width ?? 170} placeholder={f.allLabel ?? "Todos"} clearable={f.clearable ?? true} value={f.value || null} onChange={(v) => f.onChange(v ?? "")}
              data={f.options.map((o) => ({ value: o.value, label: o.count !== undefined ? `${o.label} (${o.count})` : o.label }))} />
          : <TextField key={f.label} size="sm" type="date" label={f.label} w={150} value={f.value} onChange={(e) => f.onChange(e.currentTarget.value)} />)}
        {children}
      </Group>
      {onClear && <ClearFilters active={!!active} onClear={onClear} />}
    </div>
  );
}
