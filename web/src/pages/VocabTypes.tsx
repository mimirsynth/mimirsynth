import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, ClearFilters, ColHead, ComboField, DataTable, FillArea, Modal, Notice, Pill, TextArea, TextField, useTableView, MutationError, ConfirmDialog, DataState } from "../ui";

type TypeItem = { name: string; description: string; in_ontology: boolean; count: number };
type Op = { id: number; kind: string; summary: string; status: string; created_at: string };
type Types = { items: TypeItem[]; untyped: number; ops: Op[] };
type Preview = { entities: number; already_target: number; target_in_ontology: boolean; sample: string[] };
type Dlg = { kind: "form" | "move" | "delete"; item?: TypeItem } | null;

const TYPE_COLS = {
  name: { get: (i: TypeItem) => i.name }, count: { get: (i: TypeItem) => i.count }, desc: { get: (i: TypeItem) => i.description },
  onto: { get: (i: TypeItem) => (i.in_ontology ? "en la ontología" : "fuera de la ontología"), exact: true },
};
function TypesTable({ rows, isAdmin, open }: { rows: TypeItem[]; isAdmin: boolean; open: (d: NonNullable<Dlg>, i: TypeItem) => void }) {
  const v = useTableView(rows, TYPE_COLS, { key: "count", dir: "desc" });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>Tipo</ColHead>
          <ColHead sort={v.sortProps("count")} filter={v.select("onto")}>Entidades</ColHead>
          <ColHead filter={v.text("desc", "Buscar en la descripción…")}>Descripción</ColHead>
          {isAdmin && <DataTable.Th />}
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((i) => (
          <DataTable.Tr key={i.name}>
            <DataTable.Td><Group gap={6}><Text fw={500}>{i.name}</Text>{!i.in_ontology && <Pill size="xs" tone="warn">fuera de la ontología</Pill>}</Group></DataTable.Td>
            <DataTable.Td>{i.count}</DataTable.Td>
            <DataTable.Td><Text size="sm" c="dimmed" lineClamp={2}>{i.description || "—"}</Text></DataTable.Td>
            {isAdmin && <DataTable.Td><Group gap={6} wrap="nowrap">
              <Btn size="row" icon={i.in_ontology ? "edit" : "plus"} onClick={() => open({ kind: "form", item: i }, i)}>{i.in_ontology ? "Editar" : "Añadir a la ontología"}</Btn>
              <Btn size="row" icon="refresh" onClick={() => open({ kind: "move", item: i }, i)}>Renombrar / fusionar</Btn>
              {i.in_ontology && <Btn kind="danger" size="row" icon="trash" onClick={() => open({ kind: "delete", item: i }, i)}>Quitar</Btn>}
            </Group></DataTable.Td>}
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
}

export default function VocabTypes({ graph, isAdmin }: { graph: string; isAdmin: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["vocab-types", graph], queryFn: () => get<Types>("vocab/types", { graph }) });
  const data = q.data;
  const [dlg, setDlg] = useState<Dlg>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [to, setTo] = useState("");
  const done = () => { setDlg(null); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); qc.invalidateQueries({ queryKey: ["vocab", graph] }); qc.invalidateQueries({ queryKey: ["ontology"] }); };
  const save = useMutation({
    mutationFn: () => dlg?.item?.in_ontology
      ? send("PUT", `vocab/types/${dlg.item.name}`, { description: desc }, { graph })
      : send("POST", "vocab/types", { name, description: desc }, { graph }),
    onSuccess: done,
  });
  const move = useMutation({ mutationFn: () => send("POST", `vocab/types/${dlg?.item?.name}/move`, { to }, { graph }), onSuccess: done });
  const del = useMutation({ mutationFn: () => send("DELETE", `vocab/types/${dlg?.item?.name}`, undefined, { graph }), onSuccess: done });
  const revert = useMutation({ mutationFn: (id: number) => send("POST", `vocab/ops/${id}/revert`, undefined, { graph }), onSuccess: done });
  const preview = useQuery({
    queryKey: ["vocab-preview", graph, dlg?.item?.name, to], enabled: dlg?.kind === "move" && /^[A-Z][A-Za-z0-9]{1,40}$/.test(to),
    queryFn: () => get<Preview>(`vocab/types/${dlg?.item?.name}/preview`, { graph, to }),
  });
  if (!data) return <DataState query={q} />;
  const open = (d: Dlg, item?: TypeItem) => { save.reset(); move.reset(); del.reset(); setTo(""); setName(item?.name ?? ""); setDesc(item?.description ?? ""); setDlg(d); };
  const others = data.items.filter((i) => i.name !== dlg?.item?.name).map((i) => i.name);
  const merging = !!to && data.items.some((i) => i.name === to && i.in_ontology);
  const last = data.ops.find((o) => o.status === "applied");
  const err = (save.error || move.error || del.error || revert.error) as Error | null;

  return (
    <FillArea>
      <Stack gap="sm">
        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            El catálogo de tipos de la ontología guía qué tipos extrae el ingestor y propone el corrector. Renombrar o fusionar un tipo también reetiqueta sus entidades del grafo (se puede deshacer).
            {data.untyped > 0 && ` Hay ${data.untyped} entidades sin tipo.`}
          </Text>
          {isAdmin && <Btn kind="primary" icon="plus" onClick={() => open({ kind: "form" })}>Crear tipo</Btn>}
        </Group>
        <TypesTable rows={data.items} isAdmin={isAdmin} open={open} />
        {data.ops.length > 0 && (
          <Stack gap={4}>
            <Text fw={600} size="sm">Cambios recientes</Text>
            <DataTable fz="sm"><DataTable.Tbody>{data.ops.map((o) => (
              <DataTable.Tr key={o.id}>
                <DataTable.Td w={140}>{fmt(o.created_at)}</DataTable.Td>
                <DataTable.Td>{o.summary}</DataTable.Td>
                <DataTable.Td w={140}>{o.status === "reverted" ? <Pill size="xs">deshecho</Pill> : isAdmin && o.id === last?.id
                  ? <Btn size="row" icon="undo" loading={revert.isPending} onClick={() => revert.mutate(o.id)}>Deshacer</Btn> : null}</DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody></DataTable>
            {err && !dlg && <Notice tone="danger">{err.message}</Notice>}
          </Stack>
        )}
      </Stack>

      <Modal opened={dlg?.kind === "form"} onClose={() => setDlg(null)} title={dlg?.item?.in_ontology ? `Editar ${dlg.item.name}` : dlg?.item ? `Añadir ${dlg.item.name} a la ontología` : "Crear tipo"} centered>
        <Stack>
          <TextField label="Nombre" description="PascalCase, sin espacios (p. ej. Service)" value={name} disabled={!!dlg?.item} onChange={(e) => setName(e.currentTarget.value)} />
          <TextArea label="Descripción" description="Cuándo se usa este tipo; guía al ingestor y al decisor" minRows={3} autosize value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <MutationError error={save.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setDlg(null)}>Cancelar</Btn><Btn kind="primary" icon="check" disabled={!name || desc.trim().length < 3} loading={save.isPending} onClick={() => save.mutate()}>Guardar</Btn></Group>
        </Stack>
      </Modal>

      <Modal opened={dlg?.kind === "move"} onClose={() => setDlg(null)} title={`Renombrar o fusionar ${dlg?.item?.name ?? ""}`} centered>
        <Stack>
          <Text size="sm">Las {dlg?.item?.count} entidades de tipo <b>{dlg?.item?.name}</b> pasarán al tipo que elijas. Si el destino ya existe en la ontología se fusionan; si es un nombre nuevo, se renombra (hereda la descripción).</Text>
          <ComboField label="Nuevo tipo" data={others} limit={50} value={to} onChange={setTo} placeholder="Elige uno existente o escribe un nombre nuevo" />
          {preview.data && (
            <Notice tone={merging ? "warn" : "info"} title={merging ? "Fusión" : "Renombrado"}>
              Se reetiquetan {preview.data.entities} entidades{preview.data.already_target > 0 ? ` (${preview.data.already_target} ya eran ${to})` : ""}.
              {preview.data.sample.length > 0 && ` Ejemplos: ${preview.data.sample.join(", ")}.`} Podrás deshacerlo desde «Cambios recientes» mientras no hagas otro cambio después.
            </Notice>)}
          <MutationError error={move.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setDlg(null)}>Cancelar</Btn><Btn kind="primary" icon="check" disabled={!/^[A-Z][A-Za-z0-9]{1,40}$/.test(to)} loading={move.isPending} onClick={() => move.mutate()}>{merging ? "Fusionar" : "Renombrar"}</Btn></Group>
        </Stack>
      </Modal>

      <ConfirmDialog opened={dlg?.kind === "delete"} onClose={() => setDlg(null)} title={`Quitar ${dlg?.item?.name ?? ""} de la ontología`} action="Quitar tipo"
        warning={`El tipo deja de guiar la extracción y el corrector. Las ${dlg?.item?.count} entidades del grafo conservan su etiqueta (no se tocan) y pasan a mostrarse «fuera de la ontología». Los pares del mapa de relaciones que lo usan se eliminan.`}
        onConfirm={() => del.mutateAsync()} />
    </FillArea>
  );
}
