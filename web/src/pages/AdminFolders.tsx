import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Btn, CellText, ClearFilters, ColHead, DataState, DataTable, DialogActions, Modal, Notice, Pill, SettingsBody, SettingsGroup, TextField, useTableView, MutationError, ConfirmDialog, EmptyState, ViewBar } from "../ui";

type Root = { id: number; name: string; path: string; description: string; available: boolean; sources: number };
type Data = { base: string; base_available: boolean; roots: Root[]; suggestions: string[] };

/** Administration → Folders: the server folders a brain's administrators can use as a document source. Instance administrator only.
 *  The section's table of authorised folders; «Authorise a folder» opens a dialog with the folders found under the base and the form. */
export default function AdminFolders() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["doc-roots"], queryFn: () => get<Data>("doc-roots") });
  const [f, setF] = useState({ name: "", path: "", description: "" });
  const [adding, setAdding] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["doc-roots"] });
  const add = useMutation({ mutationFn: () => send("POST", "doc-roots", f), onSuccess: () => { setF({ name: "", path: "", description: "" }); setAdding(false); refresh(); } });
  const [delRoot, setDelRoot] = useState<Root | null>(null);
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `doc-roots/${id}`), onSuccess: refresh });
  const d = q.data;
  const v = useTableView(d?.roots ?? [], { name: { get: (r: Root) => r.name }, path: { get: (r: Root) => r.path }, state: { get: (r: Root) => (r.available ? "disponible" : t("no disponible")), exact: true }, sources: { get: (r: Root) => r.sources } });
  const pick = (path: string) => setF({ ...f, path, name: f.name || path.split("/").pop()!.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").slice(0, 40) });
  const base = d?.base ?? "/sources";
  return (
    <SettingsGroup title={t("Carpetas")} description={t("Carpetas del servidor que los administradores de un brain pueden usar como fuente de documentos.")}
      help={<>{t("Carpetas que los administradores de cada brain pueden usar como fuente de documentos (Conocimiento → Fuentes). Solo se lee de ellas, nunca se escribe. Deben estar dentro de")} <span className="ms-data">{base}</span>{t(", la carpeta que el contenedor monta en solo lectura.")}</>}
      action={<Btn kind="primary" icon="plus" disabled={!d} onClick={() => { add.reset(); setAdding(true); }}>{t("Autorizar una carpeta")}</Btn>}>
      <SettingsBody>
        {d && !d.base_available && <Notice tone="warn">{t("La carpeta base {{base}} no existe dentro del contenedor: revisa el bind MIMIRSYNTH_SOURCES_DIR en docker-compose.yml.", { base: d.base })}</Notice>}
        {!d ? <DataState query={q} /> : d.roots.length === 0 ? <EmptyState>{t("Aún no hay carpetas autorizadas.")}</EmptyState> : <>
          <ViewBar title={t("Carpetas")}>{v.active && <ClearFilters active onClear={v.clear} shown={v.rows.length} total={v.total} />}</ViewBar>
          {v.rows.length === 0 ? <EmptyState>{t("Sin resultados")}</EmptyState> : <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr><ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Nombre")}</ColHead><ColHead filter={v.text("path")}>{t("Ruta en el contenedor")}</ColHead><ColHead filter={v.select("state")}>{t("Estado")}</ColHead><ColHead sort={v.sortProps("sources")}>{t("Fuentes")}</ColHead><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{v.rows.map((r) => (
              <DataTable.Tr key={r.id}>
                <DataTable.Td><CellText sub={r.description || undefined}>{r.name}</CellText></DataTable.Td>
                <DataTable.Td className="ms-data">{r.path}</DataTable.Td>
                <DataTable.Td><Pill tone={r.available ? "success" : "danger"}>{r.available ? t("disponible") : t("no disponible")}</Pill></DataTable.Td>
                <DataTable.Td className="ms-data">{r.sources}</DataTable.Td>
                <DataTable.Td><Btn kind="danger" size="row" icon="trash" disabled={r.sources > 0} title={r.sources ? t("Hay fuentes usando esta raíz") : undefined} onClick={() => setDelRoot(r)}>{t("Quitar")}</Btn></DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable>}
        </>}
        <ConfirmDialog opened={!!delRoot} onClose={() => setDelRoot(null)} title={t("Quitar carpeta autorizada")} action={t("Quitar carpeta")} subject={delRoot?.path}
          warning={t("Los brains dejan de poder usar esta carpeta como fuente. Los ficheros no se tocan.")} onConfirm={() => del.mutateAsync(delRoot!.id)} />
        <Modal opened={adding} onClose={() => setAdding(false)} title={t("Autorizar una carpeta")}>
          {d && <Stack gap="sm">
            {d.suggestions.length > 0 && (
              <Group gap={6}><Text size="sm">{t("Detectadas bajo")} <span className="ms-data">{d.base}</span>:</Text>{d.suggestions.map((s) => <Btn size="row" key={s} onClick={() => pick(s)}>{s.replace(`${d.base}/`, "")}</Btn>)}</Group>)}
            {d.suggestions.length === 0 && d.base_available && <EmptyState>{t("No hay carpetas nuevas bajo {{base}}. Móntalas en el host dentro de la carpeta del bind y aparecerán aquí.", { base: d.base })}</EmptyState>}
            <TextField label={t("Nombre")} placeholder={t("notas")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} data-autofocus />
            <TextField label={t("Ruta")} placeholder={`${base}/${t("notas")}`} value={f.path} onChange={(e) => setF({ ...f, path: e.currentTarget.value })} />
            <TextField label={t("Descripción (opcional)")} value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} />
            <MutationError error={add.error} />
            <DialogActions>
              <Btn kind="ghost" onClick={() => setAdding(false)}>{t("Cancelar")}</Btn>
              <Btn kind="primary" icon="plus" disabled={!f.name || !f.path} loading={add.isPending} onClick={() => add.mutate()}>{t("Autorizar")}</Btn>
            </DialogActions>
          </Stack>}
        </Modal>
      </SettingsBody>
    </SettingsGroup>
  );
}
