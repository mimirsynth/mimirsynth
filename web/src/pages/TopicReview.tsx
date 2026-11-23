import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { fmt, get, send } from "../api";
import { T } from "../i18n";
import { Block, Btn, CellText, Check, Compare, ConfirmDialog, DataState, DataTable, EmptyState, ListCard, MutationError, Notice, Pill, Segments, TextArea, useTabParam, ViewBar } from "../ui";
import TopicQueue from "./TopicQueue";

type Row = { id: number; entity_uuid: string; name: string; status: "queued" | "running" | "ready" | "failed"; error: string; error_code: string;
  created_at: string; finished_at: string | null; job: number | null; calls: number; counts: Record<"pending" | "approved" | "rejected" | "outdated", number>;
  trigger?: "manual" | "retirement" };
/** A fact that says the entity was retired or replaced (issue 455), as it was when it started the review. */
type Anchor = { uuid: string; fact: string; relation: string; source?: string; target?: string; proposal: number | null };
type Prec = Record<string, { approved: number; rejected: number; pending: number; precision: number | null }>;
type Item = { kind: "fact"; uuid: string; fact: string; source: string; target: string; valid_at: string | null; invalid_at: string | null; probe: string | null;
  now: "current" | "invalidated" | "gone" | null } | { kind: "episode"; uuid: string; name: string; valid_at: string | null; source: string; text: string };
type Secret = { label: string };
type Act = { i: number; type: string; facts: string[]; keep: string | null; evidence: string[]; text: string; why: string; edited: boolean;
  decision: "pending" | "applying" | "approved" | "rejected" | "outdated"; became: { proposal: number; fact?: string; status: string }[];
  skipped: { fact: string; why: string }[]; secrets: Secret[]; flagged: boolean };
type Detail = Row & { state: string; state_secrets: Secret[]; state_flagged: boolean; prompt_version: string; actions: Act[]; discarded: Record<string, number>;
  left_out: Record<string, number>; items: Record<string, Item>; anchors: Anchor[] };
type List = { engine: boolean; items: Row[]; precision: Prec };

/** What each kind of action does, as the curator reads it. */
const TYPE: Record<string, string> = { invalidate: T("Invalidar"), merge: T("Unir repetidos"), rewrite: T("Reescribir"), drop_trivial: T("Quitar por vacío"),
  gap: T("Falta en la memoria") };
const DISCARDED: Record<string, string> = { unknown_id: T("citaban algo que no se les envió"), no_evidence: T("no citaban pruebas"),
  not_a_fact: T("actuaban sobre algo que no es un hecho"), not_own: T("cambiaban un hecho de otra entidad"), not_current: T("actuaban sobre un hecho ya invalidado"),
  too_many: T("cambiaban más de diez hechos a la vez"), rule: T("no cumplían las reglas de su tipo"), secrets: T("llevaban secretos"),
  anchor: T("habrían cambiado el propio hecho de la retirada") };
const DECISION: Record<string, [string, "success" | "neutral" | "warn" | "alt"]> = { approved: [T("Aprobada"), "success"], rejected: [T("Rechazada"), "neutral"],
  outdated: [T("Ya no aplicaba"), "warn"], applying: [T("Aplicándose…"), "alt"] };
/** Why a fact of an approved action was left alone. */
const SKIPPED: Record<string, string> = { not_current: T("ya no estaba vigente"), gone: T("ya no existe"), secrets: T("su corrección llevaba secretos"),
  error: T("no se pudo corregir; inténtalo desde Hechos") };
/** What stopped a review, in words; the server's own text goes under «Detalle técnico». */
const FAILURE: Record<string, string> = { no_engine: T("No hay ningún motor LLM configurado."), gone: T("La entidad ya no está en la memoria."),
  paused: T("El brain ha agotado su presupuesto de IA de este mes."), invalid_reply: T("El motor devolvió una respuesta que no se pudo leer."),
  secrets: T("El motor escribió secretos que el brain bloquea."), engine: T("No se pudo hablar con el motor."), cancelled: T("Se canceló desde Trabajos."),
  interrupted: T("Se interrumpió antes de terminar, por ejemplo al reiniciarse el servicio."), failed: T("Falló por un error inesperado.") };
const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "?");
const busy = (r?: Row) => r?.status === "queued" || r?.status === "running";

/** Topic reviews (issue 454): the list of the brain's reviews and, opened, one review to decide action by action. */
export default function TopicReviews({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const open = Number(params.get("revision")) || null;
  const go = (id: number | null) => { const p = new URLSearchParams(params); if (id) p.set("revision", String(id)); else p.delete("revision"); setParams(p); };
  const [view, setView] = useTabParam("reviews", "vista");
  const q = useQuery({ queryKey: ["topics", graph], enabled: !open && view !== "queue", refetchInterval: (c) => (c.state.data?.items.some(busy) ? 3000 : false),
    queryFn: () => get<List>(`brains/${graph}/topics`) });
  if (open) return <ReviewDetail graph={graph} id={open} back={() => go(null)} />;
  const switcher = <Segments label={t("Ver")} value={view} onChange={setView}
    data={[{ value: "reviews", label: t("Revisiones") }, { value: "queue", label: t("Por revisar") }]} />;
  if (view === "queue") return <TopicQueue graph={graph} switcher={switcher} />;
  const d = q.data;
  // what waits for a decision first, then the newest
  const items = [...(d?.items ?? [])].sort((a, b) => Number(b.counts.pending > 0) - Number(a.counts.pending > 0) || b.created_at.localeCompare(a.created_at));
  return (
    <>
      <ViewBar title={t("Revisiones de tema")}
        help={<>{t("Una revisión de tema lee todo lo que la memoria sabe de una entidad (sus hechos, los episodios que la mencionan y los hechos de sus vecinos) y propone qué invalidar, qué unir, qué reescribir y qué falta, citando en cada caso sus pruebas. Se pide desde la página de la entidad, en Curación, o desde «Por revisar». Cada acción la decide un curador: al aprobarla se convierte en una corrección, que se aplica en el momento y se puede deshacer, o, si es algo que falta, en una propuesta de la cola.")} {t("Además, cuando se ingiere un hecho que dice que una entidad se retiró o se sustituyó, se pide sola una revisión de esa entidad, marcada «Por una retirada».")}</>}>
        {switcher}
      </ViewBar>
      {d && !d.engine && <Notice tone="warn">{t("No hay ningún motor LLM configurado (Administración → Proveedores IA).")}</Notice>}
      {!d ? <DataState query={q} /> : items.length === 0 && <EmptyState>{t("Aún no hay revisiones de tema. Se piden desde la página de una entidad (Curación → Revisar este tema) o desde «Por revisar», que ordena los temas donde una revisión rinde más.")}</EmptyState>}
      {items.map((r) => (
        <ListCard key={r.id} onOpen={() => go(r.id)} title={r.name || r.entity_uuid} aside={fmt(r.created_at)} tags={<RowState r={r} />}
          note={r.status === "failed" ? t(FAILURE[r.error_code] ?? FAILURE.failed) : undefined} />))}
      {d && items.length > 0 && <Precision p={d.precision} />}
    </>
  );
}

/** Where a ready review stands: what is left to decide, decided, or nothing proposed. */
const standing = (r: Row) => (r.counts.pending > 0 ? "pending" : r.counts.approved + r.counts.rejected + r.counts.outdated > 0 ? "decided" : "none");

function RowState({ r }: { r: Row }) {
  const { t } = useTranslation();
  const from = r.trigger === "retirement" && <Pill>{t("Por una retirada")}</Pill>;   // where it came from, after where it stands
  if (busy(r)) return <><Pill tone="alt">{t("Revisando…")}</Pill>{from}</>;
  if (r.status === "failed") return <><Pill tone="danger">{t("Falló")}</Pill>{from}</>;
  const s = standing(r);
  return <>
    {s === "pending" ? <Pill tone="warn">{t("Por decidir: {{n}}", { n: r.counts.pending })}</Pill> : <Pill>{s === "decided" ? t("Decidida") : t("Sin cambios propuestos")}</Pill>}
    {r.counts.approved > 0 && <Pill tone="success">{t("Aprobadas: {{n}}", { n: r.counts.approved })}</Pill>}
    {from}
  </>;
}

/** The technical text of a failure, folded, as MutationError does. */
function Technical({ text }: { text: string }) {
  const { t } = useTranslation();
  if (!text) return null;
  return <details className="ms-errdetail"><summary>{t("Detalle técnico")}</summary><code>{text}</code></details>;
}

function ReviewDetail({ graph, id, back }: { graph: string; id: number; back: () => void }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["topic", graph, id], refetchInterval: (c) => (busy(c.state.data) ? 2000 : false),
    queryFn: () => get<Detail>(`brains/${graph}/topics/${id}`) });
  const d = q.data;
  const qc = useQueryClient();
  const pendingIdx = useMemo(() => (d?.actions ?? []).filter((a) => a.decision === "pending").map((a) => a.i), [d]);
  const [unticked, setUnticked] = useState<Set<number>>(new Set());   // all pending ones are ticked until the curator unticks one
  const [texts, setTexts] = useState<Record<number, string>>({});
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<BatchResult[] | null>(null);
  const ticked = pendingIdx.filter((i) => !unticked.has(i));
  const rest = pendingIdx.filter((i) => unticked.has(i));
  const textOf = (a: Act) => texts[a.i] ?? a.text;
  const blocked = !!d && ticked.some((i) => ["rewrite", "gap"].includes(d.actions[i].type) && !textOf(d.actions[i]).trim());
  const batch = useMutation({
    mutationFn: () => send<{ results: BatchResult[] }>("POST", `brains/${graph}/topics/${id}/actions/decide`, {
      approve: ticked, reject: rest, note, texts: Object.fromEntries(ticked.filter((i) => texts[i] !== undefined).map((i) => [i, texts[i]])) }),
    onSuccess: (r) => { setResult(r.results); setUnticked(new Set()); setNote("");
      ["topic", "topics", "entity", "proposals"].forEach((k) => qc.invalidateQueries({ queryKey: k === "topic" ? [k, graph, id] : [k, graph] })); } });
  const left = d ? Object.entries(d.left_out).filter(([, n]) => n > 0) : [];
  const dropped = d ? Object.entries(d.discarded).filter(([, n]) => n > 0) : [];
  const LEFT: Record<string, string> = { facts: t("hechos de la entidad"), episodes: t("episodios"), neighbour_facts: t("hechos de sus vecinos") };
  return (
    <div className="ms-topic-wrap">
      <ViewBar title={t("Revisión de tema")}
        meta={d && <>{d.name} · {d.status === "ready" ? <>{{ pending: t("por decidir: {{n}}", { n: d.counts.pending }), decided: t("decidida"), none: t("sin cambios propuestos") }[standing(d)]} · </> : ""}{fmt(d.finished_at ?? d.created_at)}</>}
        help={<>{t("A la izquierda, cómo está el tema según lo que la memoria sabe ahora; a la derecha, lo que el motor propone cambiar, cada acción con los hechos sobre los que actúa y las pruebas que cita. Un hecho tachado ya no está vigente. Aprobar una invalidación, una unión, un hecho vacío o una reescritura aplica una corrección en el momento (se deshace desde la propuesta, con «Reactivar el hecho»); aprobar lo que falta lo manda a la cola de propuestas.")}
          {d && d.anchors.length > 0 ? " " + t("Una revisión por una retirada busca los hechos que aún describen la entidad como vigente, con los hechos que la lanzaron como prueba; nada se invalida sin que un curador lo apruebe.") : ""}
          {d?.status === "ready" ? " " + t("Llamadas al motor: {{n}}. Formato de la respuesta: {{version}}.", { n: d.calls, version: d.prompt_version }) : ""}</>}>
        <Btn kind="link" onClick={back}>{t("← Todas las revisiones")}</Btn>
        {d && <Btn kind="link" component={Link} to={`/entidad/${d.entity_uuid}`}>{t("Ver la entidad «{{name}}»", { name: d.name })}</Btn>}
      </ViewBar>
      {!d ? <DataState query={q} /> : <>
        {d.anchors.length > 0 && <Anchors anchors={d.anchors} name={d.name} />}
        {busy(d) && <Notice title={t("Revisando el tema «{{name}}»…", { name: d.name })}>{t("El motor está leyendo lo que la memoria sabe de la entidad. Esta página se actualiza sola.")}</Notice>}
        {d.status === "failed" && <Notice tone="danger" title={t("La revisión falló")}><Stack gap={4}>
          <Text inherit>{t(FAILURE[d.error_code] ?? FAILURE.failed)} {t("No se ha guardado nada de ella. Puedes pedirla otra vez desde la página de la entidad.")}</Text>
          <Technical text={d.error} /></Stack></Notice>}
        {d.status === "ready" && <div className="ms-topic-cols">
          <Block title={t("Estado del tema")} meta={d.state_secrets.length > 0 ? (d.state_flagged ? t("posibles secretos: revísalo") : t("secretos tapados")) : undefined}>
            <Text size="sm" className="ms-prose">{d.state}</Text>
          </Block>
          <Block title={t("Acciones propuestas")} count={d.actions.length}
            help={t("Cada acción pendiente sale marcada para aprobarla. El botón de arriba aprueba las marcadas, una a una y por el mismo camino que su propio botón Aprobar, y rechaza las desmarcadas con la nota que escribas. Una que no se pueda aplicar dice por qué y sigue pendiente.")}
            meta={pendingIdx.length > 1 && blocked ? t("Falta el texto de una acción marcada") : undefined}
            actions={pendingIdx.length > 1 && <Btn kind="primary" size="row" icon="check" disabled={blocked}
              onClick={() => { batch.reset(); setAsking(true); }}>{rest.length ? t("Aprobar {{n}} y rechazar {{m}}", { n: ticked.length, m: rest.length }) : t("Aprobar {{n}}", { n: ticked.length })}</Btn>}>
            {result && <BatchNotice results={result} onClose={() => setResult(null)} />}
            {d.actions.length === 0 ? <EmptyState>{t("El motor no propone ningún cambio en este tema.")}</EmptyState>
              : <Stack gap="sm">{d.actions.map((a) => <ActionCard key={a.i} graph={graph} d={d} a={a} ticked={!unticked.has(a.i)} batchable={pendingIdx.length > 1}
                  onTick={(on) => setUnticked((u) => { const n = new Set(u); if (on) n.delete(a.i); else n.add(a.i); return n; })}
                  text={textOf(a)} onText={(v) => setTexts((m) => ({ ...m, [a.i]: v }))} />)}</Stack>}
          </Block>
        </div>}
        {d.status === "ready" && <ConfirmDialog opened={asking} onClose={() => setAsking(false)} tone="primary" title={rest.length ? t("Aprobar {{n}} y rechazar {{m}}", { n: ticked.length, m: rest.length }) : t("Aprobar {{n}}", { n: ticked.length })}
          action={rest.length ? t("Aprobar {{n}} y rechazar {{m}}", { n: ticked.length, m: rest.length }) : t("Aprobar {{n}}", { n: ticked.length })} onConfirm={() => batch.mutateAsync()}
          warning={<BatchSummary acts={d.actions.filter((a) => ticked.includes(a.i))} rejected={rest.length} />}>
          {rest.length > 0 && <TextArea label={t("Nota")} description={t("Se guarda en las acciones que se rechazan.")} autosize minRows={2} maxRows={6} maxLength={2000}
            value={note} onChange={(e) => setNote(e.currentTarget.value)} />}
          <MutationError error={batch.error} />
        </ConfirmDialog>}
        {(left.length > 0 || dropped.length > 0) && <Notice title={t("Lo que no entró en la revisión")}><Stack gap={4}>
          {left.length > 0 && <Text inherit>{t("No cupo y no se leyó:")} {left.map(([k, n]) => `${LEFT[k] ?? k}: ${n}`).join(" · ")}. {t("Un administrador del brain puede darles más llamadas al motor con el ajuste topic_calls del curador.")}</Text>}
          {dropped.length > 0 && <Text inherit>{t("Acciones que el motor propuso y no se muestran porque")} {dropped.map(([k, n]) => `${t(DISCARDED[k] ?? k)} (${n})`).join(", ")}.</Text>}
        </Stack></Notice>}
      </>}
    </div>
  );
}

/** The facts that started a review on their own (issue 455): each one says the entity was retired or replaced. */
function Anchors({ anchors, name }: { anchors: Anchor[]; name: string }) {
  const { t } = useTranslation();
  return (
    <Notice title={anchors.length === 1 ? t("Un hecho dice que «{{name}}» se retiró o se sustituyó", { name })
      : t("{{n}} hechos dicen que «{{name}}» se retiró o se sustituyó", { n: anchors.length, name })}>
      <Stack gap={6}>
        {anchors.map((a) => <CellText key={a.uuid} sub={<>{a.source && a.target ? `${a.source} → ${a.target} · ` : ""}<span className="ms-data">{a.relation}</span>
          {a.proposal ? ` · ${t("de la propuesta #{{id}}", { id: a.proposal })}` : ""}</>}>
          {a.fact ? t("«{{fact}}»", { fact: a.fact }) : t("(su texto llevaba un secreto que el brain bloquea)")}</CellText>)}
      </Stack>
    </Notice>
  );
}

/** How curators decided each kind of action so far in this brain: nothing is approved on its own, this is what would tell when it could. */
function Precision({ p }: { p: Prec }) {
  const { t } = useTranslation();
  return (
    <Block title={t("Precisión por tipo")} help={t("De las acciones de cada tipo que los curadores de este brain han decidido, qué parte aprobaron. Las que ya no aplicaban no cuentan.")}>
      <DataTable fz="sm" aria-label={t("Precisión por tipo")}>
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th ta="right">{t("Precisión")}</DataTable.Th><DataTable.Th ta="right">{t("Aprobadas")}</DataTable.Th>
          <DataTable.Th ta="right">{t("Rechazadas")}</DataTable.Th><DataTable.Th ta="right">{t("Por decidir")}</DataTable.Th>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{Object.entries(TYPE).map(([k, label]) => {
          const v = p[k] ?? { approved: 0, rejected: 0, pending: 0, precision: null };
          return <DataTable.Tr key={k}><DataTable.Td>{t(label)}</DataTable.Td>
            <DataTable.Td ta="right" className="ms-data">{v.precision == null ? "—" : `${Math.round(v.precision * 100)} %`}</DataTable.Td>
            <DataTable.Td ta="right" className="ms-data">{v.approved}</DataTable.Td><DataTable.Td ta="right" className="ms-data">{v.rejected}</DataTable.Td>
            <DataTable.Td ta="right" className="ms-data">{v.pending}</DataTable.Td></DataTable.Tr>;
        })}</DataTable.Tbody>
      </DataTable>
    </Block>
  );
}

function ItemLine({ it, keep }: { it?: Item; keep?: boolean }) {
  const { t } = useTranslation();
  if (!it) return null;
  if (it.kind === "episode") return (
    <CellText sub={<Text inherit lineClamp={3}>{day(it.valid_at)}{it.source ? ` · ${it.source}` : ""} — «{it.text}»</Text>}>
      <Btn kind="link" component={Link} to={`/diario?episodio=${it.uuid}`}>{it.name || t("Episodio")}</Btn>
    </CellText>);
  const old = !!it.now && it.now !== "current";
  const gone = it.now === "gone" ? t("ya no existe") : it.now === "invalidated" ? t("ya no está vigente") : "";
  return (
    <CellText sub={<>{it.source} → {it.target} · {it.invalid_at ? t("válido {{from}} → {{to}}", { from: day(it.valid_at), to: day(it.invalid_at) }) : t("vigente desde {{from}}", { from: day(it.valid_at) })}
      {it.probe ? ` · ${t("sonda: {{state}}", { state: it.probe })}` : ""}{gone ? ` · ${gone}` : ""}</>}>
      <Text inherit className={old ? "ms-fact-old" : undefined}>{keep ? `${t("Se queda:")} ` : ""}{it.fact}</Text>
    </CellText>);
}

function ActionCard({ graph, d, a, ticked, batchable, onTick, text, onText }: { graph: string; d: Detail; a: Act; ticked: boolean; batchable: boolean;
  onTick: (on: boolean) => void; text: string; onText: (v: string) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const setText = onText;
  const [applied, setApplied] = useState<number[]>([]);   // the corrections this card just applied, to undo them from here
  const refresh = () => { qc.invalidateQueries({ queryKey: ["topic", graph, d.id] }); qc.invalidateQueries({ queryKey: ["topics", graph] });
    qc.invalidateQueries({ queryKey: ["entity", graph] }); qc.invalidateQueries({ queryKey: ["proposals", graph] }); };
  const approve = useMutation({ mutationFn: () => send<{ action: Act }>("POST", `brains/${graph}/topics/${d.id}/actions/${a.i}/approve`, { text: text !== a.text ? text : null }),
    onSuccess: (r) => { refresh(); setApplied(a.type === "gap" || a.type === "rewrite" ? [] : r.action.became.filter((b) => b.status !== "pending").map((b) => b.proposal)); } });
  const undo = useMutation({ mutationFn: (ids: number[]) => Promise.all(ids.map((p) => send("POST", `brains/${graph}/proposals/${p}/reactivate`))),
    onSuccess: () => { setApplied([]); refresh(); } });
  const reject = useMutation({ mutationFn: () => send("POST", `brains/${graph}/topics/${d.id}/actions/${a.i}/reject`), onSuccess: refresh });
  const pending = a.decision === "pending";
  const editable = a.type === "rewrite" || a.type === "gap";
  const list = (ids: string[], keep?: string | null) => <Stack gap={6}>{ids.map((x) => <ItemLine key={x} it={d.items[x]} keep={!!keep && x === keep} />)}</Stack>;
  const field = editable && (pending
    ? <TextArea aria-label={a.type === "gap" ? t("Lo que falta") : t("Texto nuevo")} autosize minRows={2} maxRows={8} maxLength={2000} value={text} onChange={(e) => setText(e.currentTarget.value)} />
    : <Text inherit>{a.text}</Text>);
  const [label, tone] = DECISION[a.decision] ?? ["", "neutral"];
  const cols = [
    a.facts.length > 0 && { label: a.type === "merge" ? t("Hechos que se repiten") : a.type === "rewrite" ? t("Ahora") : t("Actúa sobre"), children: list(a.facts, a.keep) },
    editable && { label: a.type === "gap" ? t("Lo que falta") : t("Texto nuevo"), children: field },
    a.evidence.length > 0 && { label: t("Pruebas"), children: list(a.evidence) },
  ].filter(Boolean) as { label: string; children: ReactNode }[];
  return (
    <ListCard title={t(TYPE[a.type] ?? a.type)}
      aside={!pending && label ? <Pill tone={tone}>{t(label)}</Pill>
        : pending && batchable ? <Check label={ticked ? t("Se aprueba") : t("Se rechaza")} aria-label={t("Aprobar «{{type}}» al decidir las marcadas; desmarcada, se rechaza", { type: t(TYPE[a.type] ?? a.type) })}
          checked={ticked} onChange={(e) => onTick(e.currentTarget.checked)} /> : undefined}
      notice={<Text size="sm" className="ms-prose">{a.why}</Text>}
      tags={(a.edited || a.secrets.length > 0) && <>
        {a.edited && <Pill>{t("editado por un curador")}</Pill>}
        {a.secrets.length > 0 && <Pill tone={a.flagged ? "warn" : "neutral"} title={a.secrets.map((s) => s.label).join(", ")}>{a.flagged ? t("posibles secretos: revísalo") : t("secretos tapados")}</Pill>}</>}
      note={(!pending || approve.error || reject.error) && <><Outcome a={a} />
        {applied.length > 0 && <> <Btn kind="link" loading={undo.isPending} onClick={() => undo.mutate(applied)}>{t("Deshacer")}</Btn></>}
        {undo.isSuccess && <> {t("Deshecho: los hechos vuelven a estar como antes.")}</>}
        <MutationError error={approve.error ?? reject.error ?? undo.error} /></>}
      actions={pending ? <>
        <Btn kind="primary" size="row" icon="check" loading={approve.isPending} disabled={reject.isPending || (editable && !text.trim())} onClick={() => approve.mutate()}>
          {editable && text !== a.text ? t("Aprobar con mis cambios") : t("Aprobar")}</Btn>
        <Btn kind="danger" size="row" loading={reject.isPending} disabled={approve.isPending} onClick={() => reject.mutate()}>{t("Rechazar")}</Btn>
      </> : undefined}>
      <Compare items={cols} />
    </ListCard>
  );
}

type BatchResult = { i: number; decision: string; error?: string; status?: number; became?: { proposal: number; status: string }[] };

/** How many facts each ticked action invalidates: a merge keeps one of its facts. */
const factsOf = (a: Act) => (a.type === "gap" ? 0 : a.type === "merge" ? a.facts.length - 1 : a.facts.length);

function BatchSummary({ acts, rejected }: { acts: Act[]; rejected: number }) {
  const { t } = useTranslation();
  // a correction with a possible secret waits in the queue for a person to mask it, as with its own Approve button
  const facts = acts.reduce((n, a) => n + (a.flagged ? 0 : factsOf(a)), 0);
  const gaps = acts.filter((a) => a.type === "gap").length + acts.reduce((n, a) => n + (a.flagged ? factsOf(a) : 0), 0);
  return <>{facts === 1 ? t("Se invalida 1 hecho, con su propia corrección, que se deshace aparte.") : facts > 1 ? t("Se invalidan {{n}} hechos, cada uno con su propia corrección, que se deshace aparte.", { n: facts }) : ""}{" "}
    {gaps === 1 ? t("1 va a la cola como propuesta.") : gaps > 1 ? t("{{n}} van a la cola como propuestas.", { n: gaps }) : ""}{" "}
    {rejected === 1 ? t("Se rechaza 1.") : rejected > 1 ? t("Se rechazan {{m}}.", { m: rejected }) : ""}</>;
}

function BatchNotice({ results, onClose }: { results: BatchResult[]; onClose: () => void }) {
  const { t } = useTranslation();
  const failed = results.filter((r) => r.error);
  const n = (d: string) => results.filter((r) => r.decision === d).length;
  return (
    <Notice tone={failed.length ? "warn" : "success"} title={failed.length ? t("Decididas, salvo {{n}}", { n: failed.length }) : t("Decididas")} onClose={onClose} withCloseButton>
      {t("Aprobadas: {{a}}. Rechazadas: {{r}}. Ya no aplicaban: {{o}}.", { a: n("approved"), r: n("rejected"), o: n("outdated") })}
      {failed.map((r) => <div key={r.i}>{t("Acción {{i}}: {{why}}", { i: r.i + 1, why: r.error })}</div>)}
    </Notice>
  );
}

/** What an approved action became: the corrections applied (or left in the queue) and the facts it could no longer act on. */
function Outcome({ a }: { a: Act }) {
  const { t } = useTranslation();
  const lines = [
    ...a.became.map((b) => a.type === "gap" ? t("Propuesta #{{id}} en la cola de propuestas.", { id: b.proposal })
      : b.status === "pending" ? t("Corrección #{{id}} pendiente en la cola: algo en ella necesita que alguien la mire.", { id: b.proposal })
      : t("Corrección #{{id}} aplicada.", { id: b.proposal })),
    ...a.skipped.map((s) => t("Un hecho no se tocó: {{why}}.", { why: t(SKIPPED[s.why] ?? SKIPPED.error) })),
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
      <Btn size="row" icon="refresh" loading={start.isPending} disabled={busy(r)} onClick={() => { start.reset(); start.mutate(); }}>{t("Revisar este tema")}</Btn>
      {busy(r) && <CellText sub={t("El motor lee lo que la memoria sabe de ella; la revisión se abre al terminar.")}>{t("Revisando el tema…")}</CellText>}
      {r && !busy(r) && r.id !== mine && <Btn kind="link" onClick={() => open(r.id)}>{t("Ver la última revisión ({{date}})", { date: fmt(r.created_at) })}</Btn>}
      <MutationError error={start.error} />
    </Stack>
  );
}
