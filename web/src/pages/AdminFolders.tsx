import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Btn, ClearFilters, ColHead, DataTable, Notice, Pill, TextField, useTableView, MutationError, ConfirmDialog, EmptyState } from "../ui";

type Root = { id: number; name: string; path: string; description: string; available: boolean; sources: number };
type Data = { base: string; base_available: boolean; roots: Root[]; suggestions: string[] };

/** Carpetas del servidor que un administrador de brain puede usar como fuente de documentos. Solo el administrador de la instancia. */
export default function AdminFolders() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["doc-roots"], queryFn: () => get<Data>("doc-roots") });
  const [f, setF] = useState({ name: "", path: "", description: "" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["doc-roots"] });
  const add = useMutation({ mutationFn: () => send("POST", "doc-roots", f), onSuccess: () => { setF({ name: "", path: "", description: "" }); refresh(); } });
  const [delRoot, setDelRoot] = useState<Root | null>(null);
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `doc-roots/${id}`), onSuccess: refresh });
  const d = q.data;
  const v = useTableView(d?.roots ?? [], { name: { get: (r: Root) => r.name }, path: { get: (r: Root) => r.path }, state: { get: (r: Root) => (r.available ? "disponible" : "no disponible"), exact: true }, sources: { get: (r: Root) => r.sources } });
  const pick = (path: string) => setF({ ...f, path, name: f.name || path.split("/").pop()!.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").slice(0, 40) });
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">Carpetas que los administradores de cada brain pueden usar como fuente de documentos (Conocimiento → Fuentes). Solo se lee de ellas, nunca se escribe. Deben estar dentro de <code>{d?.base ?? "/sources"}</code>, la carpeta que el contenedor monta en solo lectura.</Text>
      {d && !d.base_available && <Notice tone="warn">La carpeta base {d.base} no existe dentro del contenedor: revisa el bind <code>MIMIRSYNTH_SOURCES_DIR</code> en docker-compose.yml.</Notice>}
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={v.sortProps("name")} filter={v.text("name")}>Nombre</ColHead><ColHead filter={v.text("path")}>Ruta en el contenedor</ColHead><ColHead filter={v.select("state")}>Estado</ColHead><ColHead sort={v.sortProps("sources")}>Fuentes</ColHead><DataTable.Th /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((r) => (
          <DataTable.Tr key={r.id}>
            <DataTable.Td><Text size="sm" fw={500}>{r.name}</Text>{r.description && <Text size="xs" c="dimmed">{r.description}</Text>}</DataTable.Td>
            <DataTable.Td><Text size="xs" className="ms-data">{r.path}</Text></DataTable.Td>
            <DataTable.Td><Pill size="xs" tone={r.available ? "success" : "danger"}>{r.available ? "disponible" : "no disponible"}</Pill></DataTable.Td>
            <DataTable.Td>{r.sources}</DataTable.Td>
            <DataTable.Td><Btn kind="danger" size="row" icon="trash" disabled={r.sources > 0} title={r.sources ? "Hay fuentes usando esta raíz" : undefined} onClick={() => setDelRoot(r)}>Quitar</Btn></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
      {d?.roots.length === 0 && <EmptyState>Aún no hay carpetas autorizadas.</EmptyState>}
      <ConfirmDialog opened={!!delRoot} onClose={() => setDelRoot(null)} title="Quitar carpeta autorizada" action="Quitar carpeta" subject={delRoot?.path}
        warning="Los brains dejan de poder usar esta carpeta como fuente. Los ficheros no se tocan." onConfirm={() => del.mutateAsync(delRoot!.id)} />
      <Text size="sm" fw={500}>Autorizar una carpeta</Text>
      {d && d.suggestions.length > 0 && (
        <Group gap={6}><Text size="xs" c="dimmed">Detectadas bajo {d.base}:</Text>{d.suggestions.map((s) => <Btn size="row" key={s} onClick={() => pick(s)}>{s.replace(`${d.base}/`, "")}</Btn>)}</Group>)}
      {d && d.suggestions.length === 0 && d.base_available && <EmptyState>No hay carpetas nuevas bajo {d.base}. Móntalas en el host dentro de la carpeta del bind y aparecerán aquí.</EmptyState>}
      <Group align="flex-end" gap="xs">
        <TextField size="xs" label="Nombre" placeholder="notas" w={160} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
        <TextField size="xs" label="Ruta" placeholder={`${d?.base ?? "/sources"}/notas`} w={300} value={f.path} onChange={(e) => setF({ ...f, path: e.currentTarget.value })} />
        <TextField size="xs" label="Descripción (opcional)" w={240} value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} />
        <Btn kind="primary" icon="plus" disabled={!f.name || !f.path} loading={add.isPending} onClick={() => add.mutate()}>Autorizar</Btn>
      </Group>
      <MutationError error={add.error} />
    </Stack>
  );
}
