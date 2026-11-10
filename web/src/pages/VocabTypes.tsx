import { tr } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Block, Btn, ClearFilters, ColHead, ComboField, DataTable, DialogActions, EmptyState, Modal, Notice, Pill, TextArea, TextField, useTableView, MutationError, ConfirmDialog, DataState, ViewBar } from "../ui";
import { OpsTable, type VocabOp } from "./VocabOps";

type TypeItem = { name: string; description: string; in_ontology: boolean; count: number };
type Types = { items: TypeItem[]; untyped: number; ops: VocabOp[] };
type Preview = { entities: number; already_target: number; target_in_ontology: boolean; sample: string[] };
type Dlg = { kind: "form" | "move" | "delete"; item?: TypeItem } | null;
const NO_TYPES: TypeItem[] = [];

const TYPE_COLS = {
  name: { get: (i: TypeItem) => i.name }, count: { get: (i: TypeItem) => i.count }, desc: { get: (i: TypeItem) => i.description },
  onto: { get: (i: TypeItem) => (i.in_ontology ? tr("en la ontología") : tr("fuera de la ontología")), exact: true },
};

/** Changes a curator makes, and so may undo: fact edits and the type of one entity (the server checks the same). */
const curated = (kind: string) => kind.startsWith("fact.") || kind === "entity.retype" || kind === "entity.summary";

/** Vocabulary → Entity types: the bar (what the catalogue is for, how many entities have no type, «Create type»), the types observed in
 *  the graph with their place in the ontology, and under them the recent changes with their Undo. */
export default function VocabTypes({ graph, isAdmin, isCurator }: { graph: string; isAdmin: boolean; isCurator: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["vocab-types", graph], queryFn: () => get<Types>("vocab/types", { graph }) });
  const data = q.data;
  const v = useTableView(data?.items ?? NO_TYPES, TYPE_COLS, { key: "count", dir: "desc" });
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
  const open = (d: Dlg, item?: TypeItem) => { save.reset(); move.reset(); del.reset(); setTo(""); setName(item?.name ?? ""); setDesc(item?.description ?? ""); setDlg(d); };
  const items = data?.items ?? NO_TYPES;
  const others = items.filter((i) => i.name !== dlg?.item?.name).map((i) => i.name);
  const merging = !!to && items.some((i) => i.name === to && i.in_ontology);
  const last = data?.ops.find((o) => o.status === "applied");
  const err = (save.error || move.error || del.error || revert.error) as Error | null;

  return (
    <>
      <ViewBar title={t("Tipos de entidad")}
        help={t("El catálogo de tipos de la ontología guía qué tipos extrae el ingestor y propone el corrector. Renombrar o fusionar un tipo también reetiqueta sus entidades del grafo (se puede deshacer).")}
        meta={data && data.untyped > 0 ? t("{{n}} entidades sin tipo", { n: data.untyped }) : undefined}
        actions={isAdmin && <Btn kind="primary" icon="plus" onClick={() => open({ kind: "form" })}>{t("Crear tipo")}</Btn>}>
        <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      </ViewBar>
      {!dlg && <MutationError error={err} />}
      {!data ? <DataState query={q} /> : items.length === 0 ? <EmptyState>{t("Sin tipos de entidad.")}</EmptyState> : (
        <DataTable fz="sm" aria-label={t("Tipos de entidad")}>
          <DataTable.Thead><DataTable.Tr>
            <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Tipo")}</ColHead>
            <ColHead sort={v.sortProps("count")} filter={v.select("onto")}>{t("Entidades")}</ColHead>
            <ColHead filter={v.text("desc", t("Buscar en la descripción…"))}>{t("Descripción")}</ColHead>
            {isAdmin && <DataTable.ActionsHead />}
          </DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{v.rows.map((i) => (
            <DataTable.Tr key={i.name}>
              <DataTable.Td><Group gap={6}><Text size="sm">{i.name}</Text>{!i.in_ontology && <Pill tone="warn">{t("fuera de la ontología")}</Pill>}</Group></DataTable.Td>
              <DataTable.Td className="ms-data">{i.count}</DataTable.Td>
              <DataTable.Td><Text size="sm" lineClamp={2}>{i.description || "—"}</Text></DataTable.Td>
              {isAdmin && <DataTable.Td><Group gap={6} wrap="nowrap">
                <Btn size="row" icon={i.in_ontology ? "edit" : "plus"} onClick={() => open({ kind: "form", item: i }, i)}>{i.in_ontology ? t("Editar") : t("Añadir a la ontología")}</Btn>
                <Btn size="row" icon="refresh" onClick={() => open({ kind: "move", item: i }, i)}>{t("Renombrar / fusionar")}</Btn>
                {i.in_ontology && <Btn kind="danger" size="row" icon="trash" onClick={() => open({ kind: "delete", item: i }, i)}>{t("Quitar")}</Btn>}
              </Group></DataTable.Td>}
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable>)}
      {data && data.ops.length > 0 && (
        <Block title={t("Cambios recientes")} count={data.ops.length} help={t("Solo se puede deshacer la última, mientras no haya otro cambio de vocabulario después.")}>
          <OpsTable ops={data.ops} lastApplied={last?.id} canRevert={isAdmin || (isCurator && !!last && curated(last.kind))}
            reverting={revert.isPending} onRevert={(id) => revert.mutate(id)} label={t("Cambios recientes")} />
        </Block>)}

      <Modal opened={dlg?.kind === "form"} onClose={() => setDlg(null)} title={dlg?.item?.in_ontology ? t("Editar {{name}}", { name: dlg.item.name }) : dlg?.item ? t("Añadir {{name}} a la ontología", { name: dlg.item.name }) : t("Crear tipo")}>
        <Stack gap="sm">
          <TextField label={t("Nombre")} description={t("PascalCase, sin espacios (p. ej. Service)")} value={name} disabled={!!dlg?.item} onChange={(e) => setName(e.currentTarget.value)} />
          <TextArea label={t("Descripción")} description={t("Cuándo se usa este tipo; guía al ingestor y al decisor")} minRows={3} autosize value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <MutationError error={save.error} />
          <DialogActions><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" disabled={!name || desc.trim().length < 3} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></DialogActions>
        </Stack>
      </Modal>

      <Modal opened={dlg?.kind === "move"} onClose={() => setDlg(null)} title={t("Renombrar o fusionar {{name}}", { name: dlg?.item?.name ?? "" })}>
        <Stack gap="sm">
          <Text size="sm">{t("Las {{count}} entidades de tipo «{{name}}» pasarán al tipo que elijas. Si el destino ya existe en la ontología se fusionan; si es un nombre nuevo, se renombra (hereda la descripción).", { count: dlg?.item?.count, name: dlg?.item?.name })}</Text>
          <ComboField label={t("Nuevo tipo")} data={others} limit={50} value={to} onChange={setTo} placeholder={t("Elige uno existente o escribe un nombre nuevo")} />
          {preview.data && (
            <Notice tone={merging ? "warn" : "info"} title={merging ? t("Fusión") : t("Renombrado")}>
              {t("Se reetiquetan {{count}} entidades", { count: preview.data.entities })}{preview.data.already_target > 0 ? t(" ({{already_target}} ya eran {{to}})", { already_target: preview.data.already_target, to: to }) : ""}.
              {preview.data.sample.length > 0 && t(" Ejemplos: {{v}}.", { v: preview.data.sample.join(", ") })} {t("Podrás deshacerlo desde «Cambios recientes» mientras no hagas otro cambio después.")}
            </Notice>)}
          <MutationError error={move.error} />
          <DialogActions><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" disabled={!/^[A-Z][A-Za-z0-9]{1,40}$/.test(to)} loading={move.isPending} onClick={() => move.mutate()}>{merging ? t("Fusionar") : t("Renombrar")}</Btn></DialogActions>
        </Stack>
      </Modal>

      <ConfirmDialog opened={dlg?.kind === "delete"} onClose={() => setDlg(null)} title={t("Quitar {{name}} de la ontología", { name: dlg?.item?.name ?? "" })} action={t("Quitar tipo")}
        warning={t("El tipo deja de guiar la extracción y el corrector. Las {{count}} entidades del grafo conservan su etiqueta (no se tocan) y pasan a mostrarse «fuera de la ontología». Los pares del mapa de relaciones que lo usan se eliminan.", { count: dlg?.item?.count })}
        onConfirm={() => del.mutateAsync()} />
    </>
  );
}
