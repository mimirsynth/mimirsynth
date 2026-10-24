import { useState } from "react";
import { Btn } from "./Btn";
import { TextField } from "./Fields";
import { Icon } from "./Icon";

/** Búsqueda común. `mode="live"` filtra al escribir (listas y tablas donde el filtro es instantáneo); `mode="submit"` ejecuta al pulsar «Buscar» o Intro
 *  (búsqueda semántica, que cuesta una consulta). En modo `submit`, `onSubmit` recibe el texto y `onClear` vuelve a la vista normal. */
export function SearchBar(p:
  | { mode?: "live"; value: string; onChange: (v: string) => void; placeholder: string; label?: string }
  | { mode: "submit"; value: string; onChange: (v: string) => void; placeholder: string; onSubmit: (v: string) => void; onClear: () => void; submitted: boolean; minLength?: number; disabled?: boolean; loading?: boolean }) {
  if (p.mode !== "submit") {
    return <TextField style={{ flex: "1 1 260px" }} aria-label={p.label ?? "Buscar"} placeholder={p.placeholder} leftSection={<Icon name="search" size={16} />} value={p.value} onChange={(e) => p.onChange(e.currentTarget.value)} />;
  }
  const min = p.minLength ?? 2;
  const text = p.value.trim();
  return (
    <form className="ms-searchbar" onSubmit={(e) => { e.preventDefault(); if (text.length >= min && !p.disabled) p.onSubmit(text); }}>
      <TextField style={{ flex: 1 }} aria-label="Buscar" placeholder={p.placeholder} leftSection={<Icon name="search" size={16} />} value={p.value} onChange={(e) => p.onChange(e.currentTarget.value)} />
      <Btn kind="primary" type="submit" icon="search" loading={p.loading} disabled={text.length < min || p.disabled}>Buscar</Btn>
      {p.submitted && <Btn kind="ghost" onClick={p.onClear}>Limpiar</Btn>}
    </form>
  );
}
