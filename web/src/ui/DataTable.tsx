import { Table } from "@mantine/core";
import { useEffect, useRef, type ComponentProps } from "react";

type P = Omit<ComponentProps<typeof Table>, "striped" | "highlightOnHover" | "withTableBorder" | "withRowBorders" | "variant">;

/** Tabla de la aplicación: rayado, resalte y filetes siempre iguales. Los sitios de uso solo eligen el tamaño de letra. */
function DataTableRoot(props: P) {
  const box = useRef<HTMLDivElement>(null);
  // En pantallas estrechas cada fila se pinta como una tarjeta (CSS) y cada celda necesita su rótulo: se toma de la cabecera de su columna.
  useEffect(() => {
    const heads = Array.from(box.current?.querySelectorAll("thead th") ?? []).map((h) => (h.textContent ?? "").trim());
    box.current?.querySelectorAll("tbody tr").forEach((tr) => Array.from(tr.children).forEach((td, i) => { if (td.tagName === "TD") td.setAttribute("data-label", heads[i] ?? ""); }));
  });
  return <div ref={box} className="ms-tablewrap"><Table striped highlightOnHover withTableBorder withRowBorders fz="sm" {...props} className={`ms-table${props.className ? ` ${props.className}` : ""}`} /></div>;
}
export const DataTable = Object.assign(DataTableRoot, { Thead: Table.Thead, Tbody: Table.Tbody, Tr: Table.Tr, Th: Table.Th, Td: Table.Td });

/** Props para una fila que se abre al pulsarla: también con teclado (Tab, Intro, Espacio). `<DataTable.Tr {...rowOpen(() => abrir(id))}>`. */
export function rowOpen(onOpen: () => void) {
  return {
    role: "button" as const, tabIndex: 0, style: { cursor: "pointer" }, onClick: onOpen,
    onKeyDown: (e: { key: string; target: unknown; currentTarget: unknown; preventDefault: () => void }) => { if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) { e.preventDefault(); onOpen(); } },
  };
}
