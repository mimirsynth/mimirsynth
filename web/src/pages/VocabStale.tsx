import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, get, send } from "../api";
import { Btn, DataTable, EmptyState, MutationError, Notice } from "../ui";

type Item = { uuid: string; relation: string; fact: string; source: string; source_uuid: string; target: string; valid_at: string;
  shelf_life_days: number; stale_since: string; confirmed_at: string | null; days_over: number };
type Stale = { relations: Record<string, number>; total: number; items: Item[]; truncated: boolean };

/** Hechos vigentes que han superado la vida útil de su relación: confirmarlos renueva su fecha (sin tocar el grafo); invalidarlos, como desde Hechos. */
export default function VocabStale({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["stale", graph];
  const q = useQuery({ queryKey: key, queryFn: () => get<Stale>(`brains/${graph}/review/stale`) });
  const done = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["vocabulary", graph] }); };
  const confirm = useMutation({ mutationFn: (u: string) => send("POST", `brains/${graph}/review/stale/${u}/confirm`), onSuccess: done });
  const invalidate = useMutation({ mutationFn: (u: string) => send("POST", `brains/${graph}/facts/${u}/invalidate`), onSuccess: done });
  const d = q.data;
  const rels = Object.entries(d?.relations ?? {});
  return (
    <Stack gap="sm">
      <Notice tone="info">{t("Hechos vigentes que llevan más tiempo sin confirmar que la vida útil de su relación (una IP, una versión, quién lleva un servicio). En el recall pesan menos y salen marcados. Confirma los que siguen siendo ciertos: se renueva su fecha sin tocar el grafo. Invalida los que ya no lo son. La vida útil se pone en Ontología, al editar cada relación.")}</Notice>
      {rels.length > 0 && <Text size="xs" c="dimmed">{t("Con vida útil: {{v}}", { v: rels.map(([r, n]) => t("{{r}} ({{n}} días)", { r, n })).join(", ") })}</Text>}
      {d?.truncated && <Notice tone="warn">{t("Este brain tiene tantos hechos de esas relaciones que solo se han revisado los más antiguos: la lista y el aviso diario se quedan cortos. Quita la vida útil a las relaciones que no la necesiten.")}</Notice>}
      <MutationError error={confirm.error ?? invalidate.error} />
      {d && d.items.length ? <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Hecho")}</DataTable.Th><DataTable.Th>{t("Relación")}</DataTable.Th><DataTable.Th>{t("Sin confirmar desde")}</DataTable.Th>
          <DataTable.Th>{t("Pasado de su vida útil")}</DataTable.Th><DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{d.items.map((i) => (
          <DataTable.Tr key={i.uuid}>
            <DataTable.Td><Text size="sm">{i.fact}</Text><Text size="xs" c="dimmed"><Link to={`/entidad/${i.source_uuid}`}>{i.source}</Link> → {i.target}</Text></DataTable.Td>
            <DataTable.Td><Text size="xs" className="ms-data">{i.relation}</Text></DataTable.Td>
            <DataTable.Td>{fmt(i.stale_since)}{i.confirmed_at && <Text size="xs" c="dimmed">{t("confirmado")}</Text>}</DataTable.Td>
            <DataTable.Td>{t("{{n}} días", { n: i.days_over })}</DataTable.Td>
            <DataTable.Td><Group gap={6} wrap="nowrap">
              <Btn size="row" icon="check" loading={confirm.isPending && confirm.variables === i.uuid} onClick={() => confirm.mutate(i.uuid)}>{t("Confirmar")}</Btn>
              <Btn size="row" kind="danger" loading={invalidate.isPending && invalidate.variables === i.uuid} onClick={() => invalidate.mutate(i.uuid)}>{t("Invalidar")}</Btn>
            </Group></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : q.isSuccess && <EmptyState>{rels.length ? t("No hay hechos a revisar: todos se han confirmado dentro de su vida útil.") : t("Ninguna relación tiene vida útil. Ponla en Ontología, al editar la relación, para las que se quedan viejas sin que nadie las contradiga.")}</EmptyState>}
      {d && d.total > d.items.length && <Text size="xs" c="dimmed">{t("Se muestran {{n}} de {{total}}.", { n: d.items.length, total: d.total })}</Text>}
    </Stack>
  );
}
