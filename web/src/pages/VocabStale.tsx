import { useTranslation } from "react-i18next";
import { Group } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, get, send } from "../api";
import { Btn, CellText, DataState, DataTable, EmptyState, MutationError, Notice, ViewBar } from "../ui";

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
  const ontology = <Btn kind="link" component={Link} to="/vocabulario?tab=onto">{t("Ir a Ontología")}</Btn>;
  return (
    <>
      <ViewBar title={t("A revisar")}
        help={<>{t("Hechos vigentes que llevan más tiempo sin confirmar que la vida útil de su relación (una IP, una versión, quién lleva un servicio). En el recall pesan menos y salen marcados. Confirma los que siguen siendo ciertos: se renueva su fecha sin tocar el grafo. Invalida los que ya no lo son.")}{" "}
          {t("Cuánto dura cada relación es parte del marco del brain: se pone en Vocabulario → Ontología, al editar la relación.")}{" "}
          {rels.length > 0 && t("Con vida útil: {{v}}", { v: rels.map(([r, n]) => t("{{r}} ({{n}} días)", { r, n })).join(", ") })}</>}
        meta={d && d.total > d.items.length ? t("Se muestran {{n}} de {{total}}.", { n: d.items.length, total: d.total }) : undefined}
        actions={ontology} />
      {d?.truncated && <Notice tone="warn">{t("Este brain tiene tantos hechos de esas relaciones que solo se han revisado los más antiguos: la lista y el aviso diario se quedan cortos. Quita la vida útil a las relaciones que no la necesiten.")}</Notice>}
      <MutationError error={confirm.error ?? invalidate.error} />
      {!d ? <DataState query={q} /> : d.items.length ? <DataTable aria-label={t("A revisar")}>
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Hecho")}</DataTable.Th><DataTable.Th>{t("Relación")}</DataTable.Th><DataTable.Th>{t("Sin confirmar desde")}</DataTable.Th>
          <DataTable.Th>{t("Pasado de su vida útil")}</DataTable.Th><DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{d.items.map((i) => (
          <DataTable.Tr key={i.uuid}>
            <DataTable.Td><CellText sub={<><Link to={`/entidad/${i.source_uuid}`}>{i.source}</Link> → {i.target}</>}>{i.fact}</CellText></DataTable.Td>
            <DataTable.Td className="ms-data">{i.relation}</DataTable.Td>
            <DataTable.Td><CellText data sub={i.confirmed_at ? t("confirmado") : undefined}>{fmt(i.stale_since)}</CellText></DataTable.Td>
            <DataTable.Td className="ms-data">{t("{{n}} días", { n: i.days_over })}</DataTable.Td>
            <DataTable.Td><Group gap={6} wrap="nowrap">
              <Btn size="row" icon="check" loading={confirm.isPending && confirm.variables === i.uuid} onClick={() => confirm.mutate(i.uuid)}>{t("Confirmar")}</Btn>
              <Btn size="row" kind="danger" loading={invalidate.isPending && invalidate.variables === i.uuid} onClick={() => invalidate.mutate(i.uuid)}>{t("Invalidar")}</Btn>
            </Group></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{rels.length ? t("No hay hechos a revisar: todos se han confirmado dentro de su vida útil.")
        : t("Ninguna relación tiene vida útil. Ponla en Vocabulario → Ontología, al editar la relación, para las que se quedan viejas sin que nadie las contradiga.")}</EmptyState>}
    </>
  );
}
