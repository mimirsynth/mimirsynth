import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { fmtDay, get, send } from "../api";
import { locale } from "../i18n";
import { Btn, CellText, DataState, DataTable, EmptyState, EntityChip, MutationError, Notice, Pill, ViewBar } from "../ui";

type Waiting = { id: number; status: "queued" | "running" | "ready"; trigger: "manual" | "retirement"; pending: number };
type Item = { uuid: string; name: string; type: string | null; score: number; recalls: number; facts: number; repeats: number; flagged: number; flagged_share: number;
  retirement: boolean; last_review: { id: number; finished_at: string | null; new_facts: number } | null; waiting: Waiting | null };
type Queue = { engine: boolean; recalls_from: "replay" | "counts"; replay_days: number | null; entities: number; facts_truncated: boolean; items: Item[] };

const working = (i: Item) => !!i.waiting && i.waiting.status !== "ready";

/** Where to start (issue 456): the brain's entities where a topic review would pay off, best first, each with what put it there. */
export default function TopicQueue({ graph, switcher }: { graph: string; switcher: ReactNode }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ["topics", graph, "queue"], refetchInterval: (c) => (c.state.data?.items.some(working) ? 3000 : false),
    queryFn: () => get<Queue>(`brains/${graph}/topics/queue`) });
  // the view stays in the address, so the review's way back returns here
  const open = (id: number) => { const p = new URLSearchParams(params); p.set("revision", String(id)); setParams(p); };
  const start = useMutation({ mutationFn: (uuid: string) => send<{ review: { id: number } }>("POST", `brains/${graph}/topics/entity/${encodeURIComponent(uuid)}`),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["topics", graph] }); open(r.review.id); } });
  const d = q.data;
  const source = d?.recalls_from === "replay"
    ? t("Las consultas son las de la muestra de consultas de los últimos {{n}} días que trajeron alguno de sus hechos.", { n: d.replay_days })
    : t("Las consultas son las veces que se recuperó alguno de sus hechos, sin guardar el texto de la pregunta (con la muestra de consultas activada, se cuentan las de la muestra).");
  return (
    <>
      <ViewBar title={t("Por dónde empezar")}
        help={<>{t("Las entidades donde una revisión de tema rinde más, primero las mejores. Cuentan cuántas veces se consultan (multiplica lo demás), cuántos hechos vigentes tienen, cuántos grupos de hechos repetidos, qué parte de sus hechos está marcada (pasados de su vida útil o refutados por su sonda) y si espera una revisión por una retirada. Un tema revisado baja hasta que le llegan hechos nuevos. No se hace ninguna llamada de IA para ordenarla.")}{" "}{d ? source : ""}</>}
        meta={d && d.entities > d.items.length ? t("Se muestran {{n}} de {{total}} temas.", { n: d.items.length, total: d.entities }) : undefined}>
        {switcher}
      </ViewBar>
      {d && !d.engine && <Notice tone="warn">{t("No hay ningún motor LLM configurado (Administración → Proveedores IA).")}</Notice>}
      {d?.facts_truncated && <Notice tone="warn">{t("Este brain tiene tantos hechos que solo se han leído los más recientes: la lista puede dejar fuera temas antiguos.")}</Notice>}
      {!d ? <DataState query={q} /> : d.items.length ? <DataTable aria-label={t("Por dónde empezar")}>
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Tema")}</DataTable.Th><DataTable.Th ta="right">{t("Consultas")}</DataTable.Th><DataTable.Th>{t("Última revisión")}</DataTable.Th>
          <DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{d.items.map((i) => (
          <DataTable.Tr key={i.uuid}>
            <DataTable.Td><CellText sub={<Signals i={i} />}><EntityChip wrap name={i.name || i.uuid} type={i.type} to={`/entidad/${encodeURIComponent(i.uuid)}`} /></CellText></DataTable.Td>
            <DataTable.Td ta="right" className="ms-data">{i.recalls}</DataTable.Td>
            <DataTable.Td><LastReview i={i} /></DataTable.Td>
            <DataTable.Td ta="right">{i.waiting
              ? <Btn size="row" onClick={() => open(i.waiting!.id)} aria-label={t("Ver la revisión de «{{name}}»", { name: i.name })}>{t("Ver la revisión")}</Btn>
              : <Btn size="row" icon="refresh" disabled={!d.engine || (start.isPending && start.variables !== i.uuid)} loading={start.isPending && start.variables === i.uuid}
                  onClick={() => { start.reset(); start.mutate(i.uuid); }} aria-label={t("Revisar el tema «{{name}}»", { name: i.name })}>{t("Revisar")}</Btn>}
              {start.variables === i.uuid && <MutationError error={start.error} />}
            </DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{t("Aún no hay temas: hace falta alguna entidad con al menos dos hechos vigentes.")}</EmptyState>}
    </>
  );
}

/** What puts the topic in the list, besides its recalls: its facts, its repeats, its flagged facts and a retirement waiting. */
function Signals({ i }: { i: Item }) {
  const { t } = useTranslation();
  const share = i.flagged_share.toLocaleString(locale(), { style: "percent", maximumFractionDigits: 0 });
  const parts = [t("{{n}} hechos", { n: i.facts }),
    i.repeats === 1 ? t("1 grupo de repetidos") : i.repeats > 1 ? t("{{n}} grupos de repetidos", { n: i.repeats }) : null,
    i.flagged === 1 ? t("1 marcado ({{share}})", { share }) : i.flagged > 1 ? t("{{n}} marcados ({{share}})", { n: i.flagged, share }) : null].filter(Boolean);
  return <>{parts.join(" · ")}{i.retirement && <> <Pill>{t("Por una retirada")}</Pill></>}</>;
}

/** When the topic was last reviewed and what came since, or the review it is waiting on, as the reviews list shows it. */
function LastReview({ i }: { i: Item }) {
  const { t } = useTranslation();
  const w = i.waiting;
  if (w) return w.status === "ready" ? <Pill tone="warn">{t("Por decidir: {{n}}", { n: w.pending })}</Pill> : <Pill tone="alt">{t("Revisando…")}</Pill>;
  const r = i.last_review;
  if (!r) return <>{t("Nunca")}</>;
  const since = r.new_facts === 1 ? t("1 hecho nuevo desde entonces") : r.new_facts > 1 ? t("{{n}} hechos nuevos desde entonces", { n: r.new_facts }) : t("nada nuevo desde entonces");
  return <CellText sub={since}><span className="ms-data">{fmtDay(r.finished_at)}</span></CellText>;
}
