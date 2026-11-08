import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fmt, get, send } from "../api";
import { Btn, ConfirmDialog, DataState, DataTable, EmptyState, FillArea, MutationError, Notice, Pill } from "../ui";

type Item = { uuid: string; name: string; aliases: string[]; dropped: string[] };
type Preview = { entities: number; aliases: number; items: Item[] };
type Ops = { ops: { id: number; kind: string; summary: string; status: string; created_at: string }[] };
type Job = { status: string; error?: string; result: { entities: number; aliases: number } | null };

/** Aliases that only repeat the entity's own name, or repeat another alias (issue 202): a preview that writes nothing, and «Clean», a
 *  background job that copies the graph first and leaves the change in Recent changes, where it can be undone. Brain administrators. */
export default function VocabAliasCleanup({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const pv = useQuery({ queryKey: ["entity-aliases", graph], queryFn: () => get<Preview>("vocab/entity-aliases", { graph }) });
  const ops = useQuery({ queryKey: ["vocab-types", graph], queryFn: () => get<Ops>("vocab/types", { graph }) });
  const [ask, setAsk] = useState(false);
  const run = useMutation({ mutationFn: () => send<{ job: number | null }>("POST", "vocab/entity-aliases", undefined, { graph }), onSuccess: () => setAsk(false) });
  const job = useQuery({ queryKey: ["job", graph, run.data?.job], enabled: !!run.data?.job, queryFn: () => get<Job>(`jobs/${run.data!.job}`, { graph }),
    refetchInterval: (q) => (["queued", "running"].includes(q.state.data?.status ?? "queued") ? 1500 : false) });
  const finished = job.data && !["queued", "running"].includes(job.data.status);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["entity-aliases", graph] }); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); };
  useEffect(() => { if (finished) refresh(); }, [finished]);  // eslint-disable-line react-hooks/exhaustive-deps
  const revert = useMutation({ mutationFn: (id: number) => send<{ restored: number }>("POST", `vocab/ops/${id}/revert`, undefined, { graph }), onSuccess: refresh });
  const last = ops.data?.ops.find((o) => o.status === "applied");
  const mine = (ops.data?.ops ?? []).filter((o) => o.kind === "entity.aliases");
  if (!pv.data) return <DataState query={pv} />;
  const d = pv.data;
  return (
    <FillArea><Stack gap="sm">
      <Text size="sm" c="dimmed" className="ms-measure">
        {t("Alias que solo repiten el nombre de la entidad (sin contar mayúsculas ni espacios) o repiten otro alias. Los dejaron fusiones antiguas; las de ahora ya no los escriben. La página de la entidad no los muestra, pero siguen en el grafo. Limpiar los quita y deja los demás alias como están; antes se guarda una copia del grafo y el cambio se puede deshacer.")}{" "}
        <Btn kind="link" component={Link} to="/calidad?tab=dup">{t("Fusionar duplicados")}</Btn>
      </Text>
      {d.entities === 0 ? <EmptyState>{t("No hay alias repetidos que limpiar.")}</EmptyState> : <>
        <Group justify="space-between">
          <Text size="sm">{t("{{aliases}} alias repetidos en {{entities}} entidades.", { aliases: d.aliases, entities: d.entities })}</Text>
          <Btn kind="primary" icon="check" loading={run.isPending || (!!run.data?.job && !finished)} onClick={() => { run.reset(); setAsk(true); }}>{t("Limpiar")}</Btn>
        </Group>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Entidad")}</DataTable.Th><DataTable.Th>{t("Se quitan")}</DataTable.Th><DataTable.Th>{t("Se quedan")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{d.items.map((i) => (
            <DataTable.Tr key={i.uuid}>
              <DataTable.Td><Link to={`/entidad/${i.uuid}`}>{i.name}</Link></DataTable.Td>
              {/* as written, not as pills: the difference between two spellings is often only their case */}
              <DataTable.Td><Text size="sm" className="ms-data" td="line-through" c="dimmed">{i.dropped.join(" · ")}</Text></DataTable.Td>
              <DataTable.Td>{i.aliases.length ? <Text size="sm" className="ms-data">{i.aliases.join(" · ")}</Text> : <Text span c="dimmed">—</Text>}</DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable>
      </>}
      <MutationError error={run.error ?? revert.error} />
      {run.data?.job && !finished && <Notice>{t("Limpiando: se hace una copia del grafo y después se escriben los cambios.")}</Notice>}
      {finished && job.data?.status === "done" && job.data.result && <Notice tone="success">{t("Limpiados {{aliases}} alias en {{entities}} entidades.", job.data.result)}</Notice>}
      {finished && job.data?.status !== "done" && <Notice tone="danger">{job.data?.error || t("La limpieza no terminó.")}</Notice>}
      {revert.data && <Notice tone="success">{t("Deshecho: alias recuperados en {{count}} entidades. Las que cambiaron después de la limpieza se han dejado como estaban.", { count: revert.data.restored })}</Notice>}
      {mine.length > 0 && <Stack gap={4}>
        <Text fw={600} size="sm">{t("Limpiezas anteriores")}</Text>
        <DataTable fz="sm"><DataTable.Tbody>{mine.map((o) => (
          <DataTable.Tr key={o.id}>
            <DataTable.Td w={140}>{fmt(o.created_at)}</DataTable.Td>
            <DataTable.Td>{o.summary}</DataTable.Td>
            <DataTable.Td w={140}>{o.status === "reverted" ? <Pill size="xs">{t("deshecho")}</Pill> : o.id === last?.id
              ? <Btn size="row" icon="undo" loading={revert.isPending} onClick={() => revert.mutate(o.id)}>{t("Deshacer")}</Btn> : null}</DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody></DataTable>
      </Stack>}
      <ConfirmDialog opened={ask} onClose={() => setAsk(false)} title={t("Limpiar alias repetidos")} action={t("Limpiar")}
        warning={t("Se quitan {{aliases}} alias de {{entities}} entidades. Antes se guarda una copia del grafo, y el cambio se puede deshacer desde aquí o desde Cambios recientes.", { aliases: d.aliases, entities: d.entities })}
        onConfirm={() => run.mutateAsync()} />
    </Stack></FillArea>
  );
}
