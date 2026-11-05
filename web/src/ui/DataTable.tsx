import { Table } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { useEffect, useRef, type ComponentProps, type CSSProperties, type ReactNode } from "react";

type P = Omit<ComponentProps<typeof Table>, "striped" | "highlightOnHover" | "withTableBorder" | "withRowBorders" | "variant">;

/** Tabla de la aplicación: rayado, resalte y filetes siempre iguales. Los sitios de uso solo eligen el tamaño de letra. */
function DataTableRoot(props: P) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  // En pantallas estrechas cada fila se pinta como una tarjeta (CSS) y cada celda necesita su rótulo: se toma de la cabecera de su columna.
  useEffect(() => {
    const heads = Array.from(box.current?.querySelectorAll("thead th") ?? []).map((h) => (h.textContent ?? "").trim());
    box.current?.querySelectorAll("tbody tr").forEach((tr) => Array.from(tr.children).forEach((td, i) => { if (td.tagName === "TD") td.setAttribute("data-label", heads[i] ?? ""); }));
  });
  // on a phone the column headers become a «Sort and filter» bar; its caption is drawn by CSS (::before) and comes from here, translated
  const caption = { "--ms-sortbar-label": JSON.stringify(t("Ordenar y filtrar")) } as CSSProperties;
  return <div ref={box} className="ms-tablewrap" style={caption}><Table striped highlightOnHover withTableBorder withRowBorders fz="sm" {...props} className={`ms-table${props.className ? ` ${props.className}` : ""}`} /></div>;
}
/** Cabecera de la columna de acciones de una fila: sin título visible, pero con texto para lectores de pantalla (una cabecera vacía es un error de accesibilidad). */
function ActionsHead(props: ComponentProps<typeof Table.Th>) {
  const { t } = useTranslation();
  return <Table.Th {...props}><span className="ms-sr">{t("Acciones")}</span></Table.Th>;
}

export const DataTable = Object.assign(DataTableRoot, { Thead: Table.Thead, Tbody: Table.Tbody, Tr: Table.Tr, Th: Table.Th, Td: Table.Td, ActionsHead });

/** Props for a row that opens when clicked anywhere: a mouse convenience only. The row stays a table row (screen readers keep the
 *  table and its cells); the keyboard and screen-reader way in is a real button in one of its cells, usually the title: `RowOpen`.
 *  `<DataTable.Tr {...rowOpen(() => abrir(id))}><DataTable.Td><RowOpen onOpen={() => abrir(id)}>{título}</RowOpen></DataTable.Td>…` */
export function rowOpen(onOpen: () => void) {
  return { "data-clickable": "", onClick: onOpen };
}

/** The real button that opens a row (see `rowOpen`): it looks like the cell's text and takes the focus, Enter and Space. */
export function RowOpen({ onOpen, children }: { onOpen: () => void; children: ReactNode }) {
  return <button type="button" className="ms-rowopen" onClick={(e) => { e.stopPropagation(); onOpen(); }}>{children}</button>;
}
