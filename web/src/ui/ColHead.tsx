import { useTranslation } from "react-i18next";
import { Popover, UnstyledButton } from "@mantine/core";
import { useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import { TextField } from "./Fields";
import { DataTable } from "./DataTable";

export type SortDir = "asc" | "desc";
export type ColSort = { dir: SortDir | null; onSort: () => void };
export type ColFilter =
  | { kind: "text"; value: string; onChange: (v: string) => void; placeholder?: string; extra?: ReactNode }
  | { kind: "select"; value: string; onChange: (v: string) => void; options: { value: string; label: string; count?: number }[]; allLabel?: string; extra?: ReactNode };

/** Cabecera de columna con orden y filtro integrados: pulsar el título ordena (descendente, ascendente, sin orden) y el embudo abre el filtro de esa columna.
 *  Una columna con filtro activo se marca en el color de acento. Sirve igual para tablas paginadas en el servidor que para tablas en el cliente. */
export function ColHead({ children, sort, filter, width }: { children: ReactNode; sort?: ColSort; filter?: ColFilter; width?: number | string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const active = !!filter && filter.value !== "";
  const label = sort
    ? <UnstyledButton className="ms-colhead-label" onClick={sort.onSort} aria-label={`Ordenar por ${typeof children === "string" ? children : t("esta columna")}`}>{children}<span data-on={sort.dir ? "" : undefined}><Icon name={sort.dir === "asc" ? "sortUp" : sort.dir === "desc" ? "sortDown" : "sortNone"} size={14} /></span></UnstyledButton>
    : <span className="ms-colhead-label">{children}</span>;
  return (
    <DataTable.Th className="ms-colhead" aria-sort={sort ? (sort.dir === "asc" ? "ascending" : sort.dir === "desc" ? "descending" : "none") : undefined} data-filtered={active ? "" : undefined} style={width ? { width } : undefined}>
      <span className="ms-colhead-in">
        {label}
        {filter && (
          <Popover opened={open} onChange={setOpen} position="bottom-start" withArrow shadow="md" width={240} trapFocus>
            <Popover.Target>
              <UnstyledButton className="ms-colhead-filter" data-active={active ? "" : undefined} onClick={() => setOpen((o) => !o)} aria-label={t("Filtrar esta columna")} title={active ? t("Filtro activo") : t("Filtrar")}><Icon name="filter" size={14} /></UnstyledButton>
            </Popover.Target>
            <Popover.Dropdown className="ms-colhead-pop">
              {filter.kind === "text"
                ? <TextField size="xs" autoFocus placeholder={filter.placeholder ?? t("Contiene…")} value={filter.value} onChange={(e) => filter.onChange(e.currentTarget.value)} onKeyDown={(e) => e.key === "Enter" && setOpen(false)} />
                : <div className="ms-colhead-opts" role="listbox">
                    {[{ value: "", label: filter.allLabel ?? t("Todos") }, ...filter.options].map((o) => (
                      <UnstyledButton key={o.value} role="option" aria-selected={filter.value === o.value} data-on={filter.value === o.value ? "" : undefined} onClick={() => { filter.onChange(o.value); setOpen(false); }}>
                        <span>{o.label}</span>{"count" in o && o.count !== undefined && <span className="ms-colhead-count">{o.count}</span>}
                      </UnstyledButton>))}
                  </div>}
              {filter.extra}
              {active && <UnstyledButton className="ms-colhead-clear" onClick={() => { filter.onChange(""); setOpen(false); }}>{t("Quitar filtro")}</UnstyledButton>}
            </Popover.Dropdown>
          </Popover>)}
      </span>
    </DataTable.Th>
  );
}
