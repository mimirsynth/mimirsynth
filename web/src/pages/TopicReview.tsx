import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { fmt, get, send } from "../api";
import { T } from "../i18n";
import { Block, Btn, CellText, DataState, EmptyState, ListCard, MutationError, Notice, Pill, TextArea, ViewBar } from "../ui";

type Row = { id: number; entity_uuid: string; name: string; status: "queued" | "running" | "ready" | "failed"; error: string; created_at: string;
  finished_at: string | null; job: number | null; calls: number; counts: Record<"pending" | "approved" | "rejected" | "outdated", number> };
type Prec = Record<string, { approved: number; rejected: number; pending: number; precision: number | null }>;
type Item = { kind: "fact"; uuid: string; fact: string; source: string; target: string; valid_at: string | null; invalid_at: string | null; probe: string | null;
  now: "current" | "invalidated" | "gone" | null } | { kind: "episode"; uuid: string; name: string; valid_at: string | null; source: string; text: string };
type Act = { i: number; type: string; facts: string[]; keep: string | null; evidence: string[]; text: string; why: string; edited: boolean;
  decision: "pending" | "approved" | "rejected" | "outdated"; became: { proposal: number; fact?: string; status: string }[]; skipped: { fact: string; why: string }[];
  secrets: { label: string }[]; flagged: boolean };
type Detail = Row & { state: string; prompt_version: string; actions: Act[]; discarded: Record<string, number>; left_out: Record<string, number>;
  items: Record<string, Item>; precision: Prec };
type List = { engine: boolean; items: Row[]; precision: Prec };

/** What each kind of action does, as the curator reads it. */
const TYPE: Record<string, string> = { invalidate: T("Invalidar"), merge: T("Unir repetidos"), rewrite: T("Reescribir"), drop_trivial: T("Quitar por vacío"),
  gap: T("Falta en la memoria") };
const DISCARDED: Record<string, string> = { unknown_id: T("citaban algo que no se les envió"), no_evidence: T("no citaban pruebas"),
  not_a_fact: T("actuaban sobre algo que no es un hecho"), not_current: T("actuaban sobre un hecho ya invalidado"), rule: T("no cumplían las reglas de su tipo"),
  secrets: T("llevaban secretos") };
const DECISION: Record<string, [string, "success" | "neutral" | "warn"]> = { approved: [T("Aprobada"), "success"], rejected: [T("Rechazada"), "neutral"],
  outdated: [T("Ya no aplicaba"), "warn"] };
const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "?");
const busy = (r?: Row) => r?.status === "queued" || r?.status === "running";

/** Topic reviews (issue 454): the list of the brain's reviews and, opened, one review to decide action by action. */
export default function TopicReviews({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const open = Number(params.get("revision")) || null;
  const go = (id: number | null) => { const p = new URLSearchParams(params); if (id) p.set("revision", String(id)); else p.delete("revision"); setParams(p); };
  const q = useQuery({ queryKey: ["topics", graph], enabled: !open, refetchInterval: (c) => (c.state.data?.items.some(busy) ? 3000 : false),
    queryFn: () => get<List>(`brains/${graph}/topics`) });
  if (open) return <ReviewDetail graph={graph} id={open} back={() => go(null)} />;
  const d = q.data;
  return (
    <>
      <ViewBar title={t("Revisiones de tema")}
        help={t("Una revisión de tema lee todo lo que la memoria sabe de una entidad (sus hechos, los episodios que la mencionan y los hechos de sus vecinos) y propone qué invalidar, qué unir, qué reescribir y qué falta, citando en cada caso sus pruebas. Se pide desde la página de la entidad, en Curación. Cada acción la decide un curador: al aprobarla se convierte en una corrección, que se aplica en el momento y se puede deshacer, o, si es algo que falta, en una propuesta de la cola.")} />
      {d && !d.engine && <Notice tone="warn">{t("No hay ningún motor LLM configurado (Administración → Proveedores IA).")}</Notice>}
      {!d ? <DataState query={q} /> : d.items.length === 0 && <EmptyState>{t("Aún no hay revisiones de tema. Se piden desde la página de una entidad: Curación → Revisar este tema.")}</EmptyState>}
      {d?.items.map((r) => (
        <ListCard key={r.id} onOpen={() => go(r.id)} title={r.name || r.entity_uuid} aside={fmt(r.created_at)} tags={<RowState r={r} />}
          note={r.status === "failed" ? r.error || t("Se interrumpió antes de terminar.") : undefined} />))}
    </>
  );
}

function RowState({ r }: { r: Row }) {
  const { t } = useTranslation();
  if (busy(r)) return <Pill tone="alt">{t("Revisando…")}</Pill>;
  if (r.status === "failed") return <Pill tone="danger">{t("Falló")}</Pill>;
  const decided = r.counts.approved + r.counts.rejected + r.counts.outdated;
  return <>
    {r.counts.pending > 0 ? <Pill tone="warn">{t("{{n}} por decidir", { n: r.counts.pending })}</Pill> : <Pill>{decided ? t("Decidida") : t("Sin cambios propuestos")}</Pill>}
    {r.counts.approved > 0 && <Pill tone="success">{t("{{n}} aprobadas", { n: r.counts.approved })}</Pill>}
  </>;
}

function ReviewDetail({ graph, id, back }: { graph: string; id: number; back: () => void }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["topic", graph, id], refetchInterval: (c) => (busy(c.state.data) ? 2000 : false),
    queryFn: () => get<Detail>(`brains/${graph}/topics/${id}`) });
  const d = q.data;
  const left = d ? Object.entries(d.left_out).filter(([, n]) => n > 0) : [];
  const dropped = d ? Object.entries(d.discarded).filter(([, n]) => n > 0) : [];
  const LEFT: Record<string, string> = { facts: t("hechos de la entidad"), episodes: t("episodios"), neighbour_facts: t("hechos de sus vecinos") };
  return (
    <>
      <ViewBar title={t("Revisión de tema")} meta={d && d.status === "ready" ? t("{{date}} · {{calls}} llamadas al motor · {{version}}", { date: fmt(d.finished_at ?? d.created_at), calls: d.calls, version: d.prompt_version }) : undefined}
        help={t("A la izquierda, cómo está el tema según lo que la memoria sabe ahora; a la derecha, lo que el motor propone cambiar, cada acción con los hechos sobre los que actúa y las pruebas que cita. Un hecho tachado ya no está vigente. Aprobar una invalidación, una unión, un hecho vacío o una reescritura aplica una corrección en el momento (se deshace desde la propuesta, con «Reactivar el hecho»); aprobar lo que falta lo manda a la cola de propuestas.")}>
        <Btn kind="link" onClick={back}>{t("← Todas las revisiones")}</Btn>
        {d && <Btn kind="link" component={Link} to={`/entidad/${d.entity_uuid}`}>{t("Ver la entidad «{{name}}»", { name: d.name })}</Btn>}
      </ViewBar>
      {!d ? <DataState query={q} /> : <>
        {busy(d) && <Notice title={t("Revisando el tema «{{name}}»…", { name: d.name })}>{t("El motor está leyendo lo que la memoria sabe de la entidad. Esta página se actualiza sola.")}</Notice>}
        {d.status === "failed" && <Notice tone="danger" title={t("La revisión falló")}><Stack gap={4}><Text inherit>{d.error || t("Se interrumpió antes de terminar.")}</Text>
          <Text inherit>{t("No se ha guardado nada de ella. Puedes pedirla otra vez desde la página de la entidad.")}</Text></Stack></Notice>}
        {left.length > 0 && <Notice tone="warn" title={t("No cupo todo")}>
          {t("Se quedaron fuera de la revisión:")} {left.map(([k, n]) => `${LEFT[k] ?? k}: ${n}`).join(" · ")}. {t("Las revisiones pueden usar más llamadas al motor con el ajuste topic_calls del curador.")}</Notice>}
        {dropped.length > 0 && <Notice tone="warn" title={t("Acciones descartadas")}>
          {t("El motor propuso más acciones que no se muestran porque")} {dropped.map(([k, n]) => `${t(DISCARDED[k] ?? k)} (${n})`).join(", ")}.</Notice>}
        {d.status === "ready" && <div className="ms-topic-cols">
          <Stack gap="md">
            <Block title={t("Estado del tema")}><Text size="sm" className="ms-prose">{d.state}</Text></Block>
            <Precision p={d.precision} />
          </Stack>
          <Block title={t("Acciones propuestas")} count={d.actions.length}>
            {d.actions.length === 0 ? <EmptyState>{t("El motor no propone ningún cambio en este tema.")}</EmptyState>
              : <Stack gap="sm">{d.actions.map((a) => <ActionCard key={a.i} graph={graph} d={d} a={a} />)}</Stack>}
          </Block>
        </div>}
      </>}
    </>
  );
}

/** How curators decided each kind of action so far in this brain: nothing is approved on its own, this is what would tell when it could. */
function Precision({ p }: { p: Prec }) {
  const { t } = useTranslation();
  return (
    <Block title={t("Precisión por tipo")} help={t("De las acciones de cada tipo que los curadores de este brain han decidido, qué parte aprobaron. Las que ya no aplicaban no cuentan.")}>
      <Stack gap={6}>
        {Object.entries(TYPE).map(([k, label]) => {
          const v = p[k];
          return <CellText key={k} data sub={t("{{approved}} aprobadas · {{rejected}} rechazadas · {{pending}} por decidir", v ?? { approved: 0, rejected: 0, pending: 0 })}>
            {t(label)}: {v?.precision == null ? "—" : `${Math.round(v.precision * 100)} %`}</CellText>;
        })}
      </Stack>
    </Block>
  );
}

function Part({ label, children }: { label: string; children: ReactNode }) {
  return <div className="ms-compare-col"><div className="ms-compare-label">{label}</div><div className="ms-compare-body">{children}</div></div>;
}

function ItemLine({ it, keep }: { it?: Item; keep?: boolean }) {
  const { t } = useTranslation();
  if (!it) return null;
  if (it.kind === "episode") return (
    <CellText sub={<Text inherit lineClamp={3}>{day(it.valid_at)}{it.source ? ` · ${it.source}` : ""} — «{it.text}»</Text>}>
      <Link to={`/diario?episodio=${it.uuid}`}>{it.name || t("Episodio")}</Link>
    </CellText>);
  const gone = it.now === "gone" ? t("ya no existe") : it.now === "invalidated" ? t("ya no está vigente") : "";
  return (
    <CellText sub={<>{it.source} → {it.target} · {it.invalid_at ? t("válido {{from}} → {{to}}", { from: day(it.valid_at), to: day(it.invalid_at) }) : t("vigente desde {{from}}", { from: day(it.valid_at) })}
      {it.probe ? ` · ${t("sonda: {{state}}", { state: it.probe })}` : ""}{gone ? ` · ${gone}` : ""}</>}>
      <Text inherit td={it.now && it.now !== "current" ? "line-through" : undefined}>{it.fact}</Text>{keep && <> <Pill tone="success">{t("se queda")}</Pill></>}
    </CellText>);
}

function ActionCard({ graph, d, a }: { graph: string; d: Detail; a: Act }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [text, setText] = useState(a.text);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["topic", graph, d.id] }); qc.invalidateQueries({ queryKey: ["topics", graph] });
    qc.invalidateQueries({ queryKey: ["entity", graph] }); qc.invalidateQueries({ queryKey: ["proposals", graph] }); };
  const approve = useMutation({ mutationFn: () => send("POST", `brains/${graph}/topics/${d.id}/actions/${a.i}/approve`, { text: text !== a.text ? text : null }), onSuccess: refresh });
  const reject = useMutation({ mutationFn: () => send("POST", `brains/${graph}/topics/${d.id}/actions/${a.i}/reject`), onSuccess: refresh });
  const pending = a.decision === "pending";
  const editable = a.type === "rewrite" || a.type === "gap";
  const list = (ids: string[], keep?: string | null) => <Stack gap={6}>{ids.map((x) => <ItemLine key={x} it={d.items[x]} keep={!!keep && x === keep} />)}</Stack>;
  const field = editable && (pending
    ? <TextArea aria-label={a.type === "gap" ? t("Lo que falta") : t("Texto nuevo")} autosize minRows={2} maxRows={8} maxLength={2000} value={text} onChange={(e) => setText(e.currentTarget.value)} />
    : <Text inherit>{a.text}</Text>);
  const [label, tone] = DECISION[a.decision] ?? ["", "neutral"];
  return (
    <ListCard title={t(TYPE[a.type] ?? a.type)}
      tags={<>{!pending && <Pill tone={tone}>{t(label)}</Pill>}
        {a.edited && <Pill>{t("editado por un curador")}</Pill>}
        {a.secrets.length > 0 && <Pill tone={a.flagged ? "warn" : "neutral"} title={a.secrets.map((s) => s.label).join(", ")}>{a.flagged ? t("posibles secretos: revísalo") : t("secretos tapados")}</Pill>}</>}
      note={!pending ? <Outcome a={a} /> : undefined}
      actions={pending ? <>
        <Btn kind="primary" size="row" icon="check" loading={approve.isPending} disabled={reject.isPending || (editable && !text.trim())} onClick={() => approve.mutate()}>
          {editable && text !== a.text ? t("Aprobar con mis cambios") : t("Aprobar")}</Btn>
        <Btn kind="danger" size="row" loading={reject.isPending} disabled={approve.isPending} onClick={() => reject.mutate()}>{t("Rechazar")}</Btn>
      </> : undefined}>
      <Stack gap="sm">
        <Text size="sm" className="ms-prose">{a.why}</Text>
        <div className="ms-compare">
          {a.facts.length > 0 && <Part label={a.type === "merge" ? t("Hechos que se repiten") : a.type === "rewrite" ? t("Ahora") : t("Actúa sobre")}>{list(a.facts, a.keep)}</Part>}
          {editable && <Part label={a.type === "gap" ? t("Lo que falta") : t("Texto nuevo")}>{field}</Part>}
          {a.type !== "rewrite" && a.evidence.length > 0 && <Part label={t("Pruebas")}>{list(a.evidence)}</Part>}
        </div>
        {a.type === "rewrite" && a.evidence.length > 0 && <Part label={t("Pruebas")}>{list(a.evidence)}</Part>}
        <MutationError error={approve.error ?? reject.error} />
      </Stack>
    </ListCard>
  );
}

/** What an approved action became: the corrections applied (or left in the queue) and the facts it could no longer act on. */
function Outcome({ a }: { a: Act }) {
  const { t } = useTranslation();
  const lines = [
    ...a.became.map((b) => a.type === "gap" ? t("Propuesta #{{id}} en la cola de propuestas.", { id: b.proposal })
      : b.status === "pending" ? t("Corrección #{{id}} pendiente en la cola: algo en ella necesita que alguien la mire.", { id: b.proposal })
      : t("Corrección #{{id}} aplicada.", { id: b.proposal })),
    ...a.skipped.map((s) => t("Un hecho no se tocó: {{why}}", { why: s.why })),
  ];
  if (!lines.length) return null;
  return <>{lines.join(" ")} {a.became.length > 0 && <Btn kind="link" component={Link} to={a.type === "gap" ? "/propuestas" : "/propuestas?tab=decididas"}>{t("Ver en Propuestas")}</Btn>}</>;
}

/** The entity page's way in: ask for a review of this entity, follow it, and open it when it is ready. */
export function TopicReviewStart({ graph, uuid }: { graph: string; uuid: string }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [mine, setMine] = useState<number | null>(null);
  const last = useQuery({ queryKey: ["topics", graph, "entity", uuid], refetchInterval: (c) => (busy(c.state.data?.items[0]) ? 2000 : false),
    queryFn: () => get<List>(`brains/${graph}/topics`, { entity: uuid, limit: 1 }) });
  const start = useMutation({ mutationFn: () => send<{ review: Row; created: boolean }>("POST", `brains/${graph}/topics/entity/${uuid}`),
    onSuccess: (r) => { setMine(r.review.id); qc.invalidateQueries({ queryKey: ["topics", graph] }); } });
  const r = last.data?.items[0];
  const open = (id: number) => nav(`/calidad?tab=topics&revision=${id}`);
  useEffect(() => { if (mine && r?.id === mine && r.status !== "queued" && r.status !== "running") open(mine); }, [mine, r?.id, r?.status]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Stack gap={4} align="flex-start">
      <Btn kind="link" loading={start.isPending} disabled={busy(r)} onClick={() => { start.reset(); start.mutate(); }}>{t("Revisar este tema")}</Btn>
      {busy(r) && <CellText sub={t("El motor lee lo que la memoria sabe de ella; la revisión se abre al terminar.")}>{t("Revisando el tema…")}</CellText>}
      {r && !busy(r) && r.id !== mine && <Btn kind="link" onClick={() => open(r.id)}>{t("Ver la última revisión ({{date}})", { date: day(r.created_at) })}</Btn>}
      <MutationError error={start.error} />
    </Stack>
  );
}
