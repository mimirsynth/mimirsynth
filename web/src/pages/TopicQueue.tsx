import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { fmtDay, get, send } from "../api";
import { Btn, CellText, DataState, DataTable, EmptyState, EntityChip, MutationError, Notice, Pill, ViewBar } from "../ui";

type Waiting = { id: number; status: "queued" | "running" | "ready"; trigger: "manual" | "retirement" };
type Item = { uuid: string; name: string; type: string | null; score: number; recalls: number; facts: number; repeats: number; flagged: number; flagged_share: number;
  retirement: boolean; last_review: { id: number; finished_at: string | null; new_facts: number } | null; waiting: Waiting | null };
type Queue = { engine: boolean; recalls_from: "replay" | "counts"; replay_days: number | null; entities: number; facts_truncated: boolean; items: Item[] };

/** Topics to review (issue 456): the brain's entities where a topic review would pay off, best first, each with what put it there. */
export default function TopicQueue({ graph, switcher }: { graph: string; switcher: ReactNode }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ["topics", graph, "queue"], queryFn: () => get<Queue>(`brains/${graph}/topics/queue`) });
  const open = (id: number) => { const p = new URLSearchParams(params); p.delete("vista"); p.set("revision", String(id)); setParams(p); };
  const start = useMutation({ mutationFn: (uuid: string) => send<{ review: { id: number } }>("POST", `brains/${graph}/topics/entity/${uuid}`),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["topics", graph] }); open(r.review.id); } });
  const d = q.data;
  const source = d?.recalls_from === "replay"
    ? t("Las consultas son las de la muestra de consultas de los últimos {{n}} días que trajeron alguno de sus hechos.", { n: d.replay_days })
    : t("Las consultas son las veces que se recuperó alguno de sus hechos, sin guardar el texto de la pregunta (con la muestra de consultas activada, se cuentan las de la muestra).");
  return (
    <>
      <ViewBar title={t("Temas por revisar")}
        help={<>{t("Las entidades donde una revisión de tema rinde más, primero las mejores. Cuentan cuántas veces se consultan (multiplica lo demás), cuántos hechos vigentes tienen, cuántos grupos de hechos repetidos, qué parte de sus hechos está marcada (pasados de su vida útil o refutados por su sonda) y si espera una revisión por una retirada. Un tema revisado baja hasta que le llegan hechos nuevos. No se hace ninguna llamada de IA para ordenarla.")}{" "}{d ? source : ""}</>}
        meta={d && d.entities > d.items.length ? t("Se muestran {{n}} de {{total}} temas.", { n: d.items.length, total: d.entities }) : undefined}>
        {switcher}
      </ViewBar>
      {d && !d.engine && <Notice tone="warn">{t("No hay ningún motor LLM configurado (Administración → Proveedores IA).")}</Notice>}
      {d?.facts_truncated && <Notice tone="warn">{t("Este brain tiene tantos hechos que solo se han leído los más recientes: la lista puede dejar fuera temas antiguos.")}</Notice>}
      <MutationError error={start.error} />
      {!d ? <DataState query={q} /> : d.items.length ? <DataTable aria-label={t("Temas por revisar")}>
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Tema")}</DataTable.Th><DataTable.Th>{t("Consultas")}</DataTable.Th><DataTable.Th>{t("Hechos")}</DataTable.Th>
          <DataTable.Th>{t("Repetidos")}</DataTable.Th><DataTable.Th>{t("Marcados")}</DataTable.Th><DataTable.Th>{t("Última revisión")}</DataTable.Th>
          <DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{d.items.map((i) => (
          <DataTable.Tr key={i.uuid}>
            <DataTable.Td><div className="ms-topicq-name"><CellText sub={i.retirement ? <Pill>{t("Retirada por revisar")}</Pill> : undefined}>
              <EntityChip name={i.name || i.uuid} type={i.type} to={`/entidad/${i.uuid}`} /></CellText></div></DataTable.Td>
            <DataTable.Td className="ms-data">{i.recalls}</DataTable.Td>
            <DataTable.Td className="ms-data">{i.facts}</DataTable.Td>
            <DataTable.Td className="ms-data">{i.repeats || "—"}</DataTable.Td>
            <DataTable.Td className="ms-data">{i.flagged ? `${i.flagged} (${Math.round(i.flagged_share * 100)} %)` : "—"}</DataTable.Td>
            <DataTable.Td><LastReview i={i} /></DataTable.Td>
            <DataTable.Td>{i.waiting
              ? <Btn size="row" onClick={() => open(i.waiting!.id)} aria-label={t("Ver la revisión de «{{name}}»", { name: i.name })}>{t("Ver la revisión")}</Btn>
              : <Btn size="row" icon="refresh" disabled={!d.engine} loading={start.isPending && start.variables === i.uuid}
                  onClick={() => { start.reset(); start.mutate(i.uuid); }} aria-label={t("Revisar el tema «{{name}}»", { name: i.name })}>{t("Revisar")}</Btn>}
            </DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{t("Aún no hay temas: hace falta alguna entidad con al menos dos hechos vigentes.")}</EmptyState>}
    </>
  );
}

/** When the topic was last reviewed and what came since, or the review it is waiting on. */
function LastReview({ i }: { i: Item }) {
  const { t } = useTranslation();
  const w = i.waiting;
  if (w) return <>{w.status === "ready" ? t("Revisión con acciones por decidir") : t("Revisando…")}</>;
  const r = i.last_review;
  if (!r) return <>{t("Nunca")}</>;
  return <CellText sub={r.new_facts ? t("{{n}} hechos nuevos desde entonces", { n: r.new_facts }) : t("nada nuevo desde entonces")}><span className="ms-data">{fmtDay(r.finished_at)}</span></CellText>;
}
