import { T, locale } from "../i18n";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Group, Loader, Stack, Text } from "@mantine/core";
import { Btn, ClearFilters, ConfirmDialog, Icon, IconButton, ColHead, CopyBtn, DataTable, EmptyState, FillArea, InboxLayout, Modal, MutationError, Notice, NumberField, Page, PageHeader, Pager, Panel,
  Pill, QueueList, RowOpen, focusedQueueItem, Segments, Steps, Step, Tabs, TextArea, TextField, Tone, humanRelation, rowOpen, useServerTableView, useShortcuts, useTabParam, type QueueItem } from "../ui";
import { SecretsNotice, type SecretFinding } from "./Secrets";
import ProposalCategories from "./ProposalCategories";
import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fmt, fmtDay, fmtNum, get, send } from "../api";

type Prop = { id: number; name: string; body: string; source: string; source_description: string; confidence: number | null; status: string; author: string;
  /** The author's name to show; `author` is the address (or the name when there is none), for its tooltip. */ author_name?: string;
  created_at: string; reviewed_at: string | null; reviewer?: string | null; ingest_report?: { entities: number; edges: number; ontology: boolean; off_ontology: string[]; untyped_entities: number; aliased_edges?: number; auto_merged?: string[]; merge_ambiguous?: string[] } | null; review_note: string; review_kind: string; decision: any; ingest_error: string; episode_uuid: string | null; ingested_at: string | null; purged_at?: string | null; secrets?: SecretFinding[];
  kind?: string; correction?: Correction | null; secrets_notice?: string; related_verdict?: string; claims?: Claim[] | null;
  /** Whether its new facts came back to a control question after ingesting (issue 296). */
  selftest?: { checked_at: string; retrievable?: boolean | null; skipped?: string; error?: string; results?: { fact_uuid: string; fact: string; question: string; found: boolean; rank: number | null; outranked_by: string[] }[] } | null };
/** A structured claim of the proposal, compared with the brain's current facts when it was sent, and what approving it did. */
type Claim = { subject: string; relation: string; value: string; valid_from: string | null; supersedes: string | null;
  verdict: "new" | "confirms" | "replaces" | "may_replace"; facts: { uuid: string; fact: string; target: string; valid_at: string | null }[];
  applied?: { action: string; facts: (string | { uuid: string; op: number })[]; invalid_at?: string; at: string } };
/** Correction of a fact: the fact as it was when proposed, the reason and, once applied, when (and whether it was undone). */
type Correction = { fact_uuid: string; fact: { fact: string; source: string; target: string; name: string; valid_at: string | null }; reason: string;
  invalid_at: string; applied_at?: string; reverted_at?: string };
const TONE: Record<string, Tone> = { pending: "warn", approved: "success", rejected: "neutral", ingested: "alt", failed: "danger" };
const LABEL: Record<string, string> = { pending: "pendiente", approved: "aprobada", rejected: "rechazada", ingested: "ingerida", failed: "fallida" };
const SOURCE: Record<string, string> = { text: T("texto"), message: T("conversación"), json: T("JSON") };
const LOW_CONFIDENCE = 0.6;  // the same threshold as the review queue's risk order in the API
/** Who sent it, by name: the address goes in the tooltip. */
const who = (p: Prop) => p.author_name || p.author;
const flagged = (p: Prop) => !!p.secrets?.some((f) => f.action === "flagged");
/** How a person decides one proposal. One with secrets flagged for review is never approved as written: «mask-and-approve» masks them first. */
type Verb = "approve" | "reject" | "mask-and-approve";

/** What a proposal does: adds knowledge or invalidates a fact. A correction is the delicate one, so it differs by icon, text and a filled look, not only by colour. */
function KindPill({ kind }: { kind?: string }) {
  const { t } = useTranslation();
  return kind === "correction"
    ? <Pill size="xs" tone="warn" strong title={t("Invalida un hecho del grafo")}><span className="ms-pill-row"><Icon name="undo" size={12} />{t("Corrige")}</span></Pill>
    : <Pill size="xs" tone="neutral" title={t("Añade conocimiento al grafo")}><span className="ms-pill-row"><Icon name="plus" size={12} />{t("Añade")}</span></Pill>;
}

/** Marker in the list for a proposal the secret detector touched: masked (already safe) or flagged (a person must look). Text and icon, not only colour. */
function SecretsPill({ found }: { found?: SecretFinding[] }) {
  const { t } = useTranslation();
  if (!found?.length) return null;
  const isFlagged = found.some((f) => f.action === "flagged");
  return <Pill size="xs" tone={isFlagged ? "warn" : "neutral"} title={[...new Set(found.map((f) => t(f.label)))].join(", ")}>
    <span className="ms-pill-row"><Icon name="lock" size={12} />{isFlagged ? t("Secreto por revisar") : t("Secreto enmascarado")}</span></Pill>;
}

/** Who decided a proposal, in a word: the curator, the decider, a trusted webhook, or its author on submission. */
function decidedBy(p: Prop, t: (k: string) => string): string {
  return p.review_kind === "decider" ? t("el decisor") : p.review_kind === "webhook" ? t("un webhook") : p.review_kind === "direct" ? t("al enviarla")
    : p.reviewer ?? "—";
}

/** How long a proposal has been waiting, in the interface language («hace 3 h»). */
function waited(iso: string): string {
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "always", style: "short" });
  for (const [unit, secs] of [["day", 86400], ["hour", 3600], ["minute", 60]] as const) if (Math.abs(s) >= secs) return rtf.format(Math.round(s / secs), unit);
  return rtf.format(0, "minute");
}

type PropList = { total: number; limit: number; offset: number; authors: { id: number; name: string }[]; items: Prop[] };
type Counts = Record<string, number> & { kinds?: Record<string, number>; kinds_in?: Record<string, Record<string, number>>; corrections_pending?: number };
/** The kind counts inside one state (or «all», «decided»), for a kind selector whose numbers match the state on screen: every option
 *  gets its number, or none does while the counts load. */
/** A choice and how many it holds, for a list that has no room for a separate count. */
const withCount = (label: string, n: number | undefined) => n === undefined ? label : `${label} (${n})`;
const kindCounts = (c: Counts | undefined, status: string) => {
  const k = c?.kinds_in?.[status];
  return { all: k ? (k.memory ?? 0) + (k.correction ?? 0) : undefined, memory: k?.memory, correction: k?.correction };
};
const PLURAL: Record<string, string> = { pending: T("Pendientes"), approved: T("Aprobadas"), rejected: T("Rechazadas"), failed: T("Fallidas"), ingested: T("Ingeridas") };
type View = ReturnType<typeof useProposalsView>;
const useProposalsView = () => useServerTableView({ q: "", author: "" }, { debounced: ["q"], firstDir: { name: "asc", author: "asc" }, defaultSort: { key: "at", dir: "desc" } });

/** Estado, filtros, orden y página se resuelven en el servidor (#88): con muchas propuestas se llega a todas y los filtros abarcan el conjunto entero.
 *  Devuelve hijos directos de la página: así solo la tabla (`FillArea`) se desplaza. `statuses` are the state segments it offers, the first one being «all of them». */
function ProposalsTable({ data, view, status, onStatus, statuses, kind, onKind, kindsFrom, onOpen, emptyAll, label, lead }: { data?: PropList; view: View; status: string; onStatus: (s: string) => void;
  /** A selector that goes first on the same row as the state and the kind (the queue's Show). */ lead?: ReactNode;
  /** The table's name for a screen reader. */ label: string;
  statuses: { value: string; label: string; count?: number }[]; kind: string; onKind: (k: string) => void; onOpen: (id: number) => void;
  /** The counts not filtered by kind, which the kind selector counts from. */ kindsFrom?: Counts;
  /** What to say when nothing at all is there yet (the first state, no filters). */ emptyAll: string }) {
  const { t } = useTranslation();
  const { f, setFilter, sortProps, page, setPage, active, clear } = view;
  const rows = data?.items ?? [];
  const mixed = new Set(rows.map((p) => p.kind)).size > 1;  // a Kind column only when the rows differ in it
  const kinds = kindCounts(kindsFrom, status);
  const byKind = kind !== "all" || (!!kinds.memory && !!kinds.correction);  // and a Kind filter only when there is something to tell apart
  return (<>
    <div className="ms-filter-row">
      {lead}
      <Segments label={t("Estado")} value={status} onChange={onStatus} data={statuses} />
      {byKind && <Segments label={t("Tipo")} value={kind} onChange={onKind}
        data={[{ value: "all", label: t("Todas"), count: kinds.all }, { value: "memory", label: t("Añaden"), count: kinds.memory },
          { value: "correction", label: t("Corrigen"), count: kinds.correction }]} />}
    </div>
    <ClearFilters active={active} onClear={clear} />
    <FillArea><DataTable fz="sm" aria-label={label}>
      <DataTable.Thead><DataTable.Tr>
        <ColHead sort={sortProps("id")}>#</ColHead>
        {mixed && <ColHead>{t("Tipo")}</ColHead>}
        <ColHead sort={sortProps("name")} filter={{ kind: "text", value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Título…") }}>{t("Título")}</ColHead>
        <ColHead sort={sortProps("author")} filter={{ kind: "select", value: f.author, onChange: (v) => setFilter({ author: v }), allLabel: t("Todos los autores"), options: (data?.authors ?? []).map((a) => ({ value: String(a.id), label: a.name })) }}>{t("Autor")}</ColHead>
        <ColHead sort={sortProps("conf")}>{t("Confianza")}</ColHead>
        <ColHead>{t("Estado")}</ColHead>
        <ColHead sort={sortProps("at")}>{t("Enviada")}</ColHead>
        <ColHead sort={sortProps("decided")}>{t("Decidida")}</ColHead>
      </DataTable.Tr></DataTable.Thead>
      <DataTable.Tbody>
        {rows.map((p) => (
          <DataTable.Tr key={p.id} {...rowOpen(() => onOpen(p.id))}>
            <DataTable.Td className="ms-data">#{p.id}</DataTable.Td>{mixed && <DataTable.Td><KindPill kind={p.kind} /></DataTable.Td>}
            <DataTable.Td><Group gap={4} wrap="wrap"><RowOpen onOpen={() => onOpen(p.id)}>{p.purged_at ? t("(texto purgado)") : p.name}</RowOpen><SecretsPill found={p.secrets} /></Group></DataTable.Td><DataTable.Td><span title={p.author}>{who(p)}</span></DataTable.Td><DataTable.Td className="ms-data">{fmtNum(p.confidence)}</DataTable.Td>
            <DataTable.Td><Pill size="sm" tone={TONE[p.status]}>{t(LABEL[p.status] ?? p.status)}</Pill></DataTable.Td><DataTable.Td className="ms-data">{fmt(p.created_at)}</DataTable.Td>
            <DataTable.Td>{p.reviewed_at ? <Stack gap={0}><Text size="sm">{decidedBy(p, t)}</Text><Text size="xs" c="dimmed" className="ms-data">{fmt(p.reviewed_at)}</Text></Stack> : "—"}</DataTable.Td>
          </DataTable.Tr>))}
        {data && rows.length === 0 && <DataTable.Tr><DataTable.Td colSpan={mixed ? 8 : 7}><EmptyState>{active ? t("Ninguna propuesta coincide con los filtros.") : status === statuses[0]?.value && kind === "all" ? emptyAll : t("No hay propuestas en este estado.")}</EmptyState></DataTable.Td></DataTable.Tr>}
      </DataTable.Tbody>
    </DataTable></FillArea>
    <Pager total={data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />
  </>);
}

/** The last decision taken here: what happened, what happens next, and the way back. An approval waits `undo_seconds` before ingestion;
 *  after that a single one is followed until it is ingested or failed. `ids` when it was a decision on several at once (`skipped`: how
 *  many of the selected ones were left to decide one at a time). */
type Decision = { id: number; ids?: number[]; skipped?: number; verb: "approve" | "reject" | "undone"; until: number | null;
  /** The title of the one proposal decided, so the notice names it as well as its number. */ name?: string };
/** Whether the last decision can still be taken back: a rejection, or an approval not yet handed to ingestion. */
const undoable = (last: Decision | null) => !!last && last.verb !== "undone" && (last.ids ?? [last.id]).length > 0
  && (last.verb === "reject" || !last.until || last.until > Date.now());

/** What to say about the last decision, shared by the notice on screen and the screen reader's live region. `phase` changes when the
 *  message does, never with the countdown, so the live region speaks each step once. */
function useDecisionText(base: string, graph: string, last: Decision | null, llm: boolean) {
  const { t } = useTranslation();
  const [, tick] = useState(0);  // only re-renders while counting: the time itself is read fresh on every render
  const now = Date.now();
  const waiting = !!last?.until && last.until > now;
  useEffect(() => {
    if (!waiting) return;
    const h = setInterval(() => tick((n) => n + 1), 500);
    return () => clearInterval(h);
  }, [waiting]);
  const many = !!last?.ids && last.ids.length !== 1;
  const follow = !!last && !many && last.verb === "approve" && !waiting && !!last.until;
  const p = useQuery({ queryKey: ["proposal", graph, last?.id, "after"], enabled: follow, queryFn: () => get<Prop>(`${base}/${last!.id}`),
    refetchInterval: (q) => (q.state.data?.status === "approved" ? 2000 : false) });
  if (!last) return null;
  // «#12 «Título»»: the messages say «Propuesta #{{id}} …», and the number alone tells the curator little
  const id = last.name ? `${last.id} «${last.name.length > 60 ? `${last.name.slice(0, 59)}…` : last.name}»` : String(last.id);
  const n = (last.ids ?? [id]).length;
  const s = last.until ? Math.max(1, Math.ceil((last.until - now) / 1000)) : 0;
  let tone: "success" | "danger" | "info" = "success";
  let text: string;
  let step: string;
  let undo = false, view = false;
  if (many) {
    if (n === 0) { tone = "info"; step = "none"; text = t("No se ha decidido ninguna: las seleccionadas se deciden una a una."); }
    else if (last.verb === "undone") { tone = "info"; step = "undone"; text = t("{{n}} propuestas otra vez pendientes.", { n }); }
    else if (last.verb === "reject") { tone = "info"; step = "reject"; undo = true; text = t("{{n}} propuestas rechazadas: no entra nada en el grafo.", { n }); }
    else if (waiting) { step = "wait"; undo = true; text = t("{{n}} propuestas aprobadas: entran en el grafo dentro de {{s}} s.", { n, s }); }
    else { step = "after"; text = last.until ? t("{{n}} propuestas aprobadas: entrando en el grafo. El resultado de cada una está en «Decididas».", { n }) : t("{{n}} propuestas aprobadas.", { n }); }
    if (last.skipped === 1) text += " " + t("1 se queda para decidirla aparte (una corrección, un secreto por revisar, algo que el brain ya sabe, tiene muy parecido o aún no ha comprobado, o ya decidida).");
    else if (last.skipped) text += " " + t("{{k}} se quedan para decidirlas una a una (correcciones, secretos por revisar, lo que el brain ya sabe, tiene muy parecido o aún no ha comprobado, o ya decididas).", { k: last.skipped });
  } else if (last.verb === "undone") {
    tone = "info"; step = "undone"; view = true; text = t("Propuesta #{{id}} otra vez pendiente.", { id });
  } else if (last.verb === "reject") {
    tone = "info"; step = "reject"; undo = true; text = t("Propuesta #{{id}} rechazada: no entra nada en el grafo.", { id });
  } else if (!last.until) {
    step = "approved"; undo = true;
    text = llm ? t("Propuesta #{{id}} aprobada.", { id }) : t("Propuesta #{{id}} aprobada: se queda en «Aprobadas» hasta que haya un motor de extracción.", { id });
  } else if (waiting) {
    step = "wait"; undo = true; text = t("Propuesta #{{id}} aprobada: entra en el grafo dentro de {{s}} s.", { id, s });
  } else if (p.data?.status === "ingested") {
    const r = p.data.ingest_report;
    const ents = r ? (r.entities === 1 ? t("1 entidad") : t("{{n}} entidades", { n: r.entities })) : "";
    const facts = r ? (r.edges === 1 ? t("1 hecho") : t("{{n}} hechos", { n: r.edges })) : "";
    step = "ingested"; view = true;
    text = r ? t("Propuesta #{{id}} en el grafo: {{ents}} y {{facts}}.", { id, ents, facts }) : t("Propuesta #{{id}} en el grafo.", { id });
    if (r && r.edges === 0) text += " " + t("No se extrajo ningún hecho: revisa el texto de la propuesta.");
  } else if (p.data?.status === "failed") {
    tone = "danger"; step = "failed"; view = true; text = t("Propuesta #{{id}}: falló la ingesta. {{error}}", { id, error: p.data.ingest_error });
  } else {
    step = "entering"; text = t("Propuesta #{{id}} aprobada: entrando en el grafo…", { id });
  }
  return { tone, text, undo, view, phase: `${last.verb}:${(last.ids ?? [id]).join(",")}:${step}` };
}

/** The last decision on screen, with its way back. It sits in the review footer, under the buttons it answers, when that footer is in
 *  view, and above the work otherwise. It is not a live region: `DecisionLive` speaks for it. */
const RETIRE_MS = 8000;  // a notice with nothing left to do (taken back, or in the graph) goes after this; the live region already said it
function DecisionNotice({ base, graph, last, llm, onUndo, undoing, undoError, onOpen, onClose, openId, compact }: { base: string; graph: string; last: Decision | null; llm: boolean;
  onUndo: (ids: number[]) => void; undoing: boolean; undoError: unknown; onOpen: (id: number) => void; onClose: () => void;
  /** The proposal open beside it: no «Ver la propuesta» for it. */ openId?: number | null;
  /** Docked under the decision buttons: one line, text and links together. */ compact?: boolean }) {
  const { t } = useTranslation();
  const m = useDecisionText(base, graph, last, llm);
  const done = !!m && /:(undone|ingested)$/.test(m.phase);
  useEffect(() => {
    if (!done) return;
    const h = setTimeout(onClose, RETIRE_MS);
    return () => clearTimeout(h);
  }, [done, m?.phase]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!m || !last) return null;
  const links = [
    m.undo && <Btn kind="link" loading={undoing} onClick={() => onUndo(last.ids ?? [last.id])}>{t("Deshacer")}</Btn>,
    m.view && last.id !== openId && <Btn kind="link" onClick={() => onOpen(last.id)}>{t("Ver la propuesta")}</Btn>,
    <Btn kind="link" onClick={onClose}>{t("Cerrar aviso")}</Btn>,
  ].filter(Boolean);
  const row = links.map((l, i) => <Fragment key={i}>{i > 0 && " · "}{l}</Fragment>);
  return (<Notice tone={m.tone}>{compact
    ? <Stack gap={2}><Text size="sm">{m.text} {row}</Text><MutationError error={undoError} /></Stack>
    : <Stack gap={4}><Text size="sm">{m.text}</Text><Text size="sm">{row}</Text><MutationError error={undoError} /></Stack>}</Notice>);
}

/** The screen reader's side of the notice: always mounted, because a live region must exist before it changes, and it speaks each step
 *  of a decision once (decided, entering, in the graph or failed), never the countdown. */
function DecisionLive({ base, graph, last, llm }: { base: string; graph: string; last: Decision | null; llm: boolean }) {
  const { t } = useTranslation();
  const m = useDecisionText(base, graph, last, llm);
  const [said, setSaid] = useState({ phase: "", text: "" });
  if (m && m.phase !== said.phase) setSaid({ phase: m.phase, text: m.undo ? `${m.text} ${t("Se deshace con «Deshacer» o con Z en la cola.")}` : m.text });
  return <div className="ms-sr-only" role="status" aria-live="polite">{m ? said.text : ""}</div>;
}

/** Whether an element is on screen: false while it, or a parent, is `display: none` (the narrow inbox showing the queue). */
function useShown(ref: RefObject<HTMLElement | null>, mounted: boolean) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!mounted || !el) { setShown(false); return; }
    const ro = new ResizeObserver(() => setShown(el.getClientRects().length > 0));
    ro.observe(el);
    return () => ro.disconnect();
  }, [mounted, ref]);
  return shown;
}

/** What to look at before approving a correction: the affected fact as it was, the reason and the text that replaces it. */
function CorrectionDetail({ c, replacement }: { c: Correction; replacement: string }) {
  const { t } = useTranslation();
  return (<Stack gap="xs">
    <Panel withBorder p="sm"><Stack gap={4}>
      <Text size="xs" fw={600}>{t("Hecho que se invalida")}</Text>
      <Text className="ms-prose">{c.fact.fact}</Text>
      <Text size="xs" c="dimmed">{c.fact.source} → <span title={c.fact.name}>{humanRelation(c.fact.name)}</span> → {c.fact.target}{c.fact.valid_at ? ` · ${t("vigente desde {{date}}", { date: fmtDay(c.fact.valid_at) })}` : ""} · <code>{c.fact_uuid}</code></Text>
    </Stack></Panel>
    <Panel withBorder p="sm"><Stack gap={4}>
      <Text size="xs" fw={600}>{t("Motivo")}</Text><Text className="ms-prose">{c.reason}</Text>
    </Stack></Panel>
    <Panel withBorder p="sm"><Stack gap={4}>
      <Text size="xs" fw={600}>{t("Lo que lo sustituye")}</Text>
      {replacement.trim() ? <Text className="ms-prose">{replacement}</Text> : <Text size="xs" c="dimmed">{t("Sin sustituto: solo se invalida el hecho.")}</Text>}
    </Stack></Panel>
  </Stack>);
}

const CLAIM_VERDICT: Record<Claim["verdict"], { label: string; tone: Tone; facts?: string }> = {
  new: { label: T("Nueva"), tone: "neutral" },
  confirms: { label: T("Confirma un hecho vigente"), tone: "success", facts: T("Al aprobarla se registra como confirmación de:") },
  replaces: { label: T("Sustituye hechos"), tone: "warn", facts: T("Al aprobarla, tras ingerirla, se invalidan:") },
  may_replace: { label: T("Parece sustituir"), tone: "neutral", facts: T("Hay otros valores vigentes en esa relación; no se tocan:") },
};

/** The proposal's structured claims (issue 295): each with what the brain knew when it was sent and what approving it does or did. */
function ClaimsDetail({ claims }: { claims: Claim[] }) {
  const { t } = useTranslation();
  return (<Stack gap="xs">
    <Text size="xs" fw={600}>{t("Afirmaciones")}</Text>
    {claims.map((c, i) => {
      const v = CLAIM_VERDICT[c.verdict] ?? CLAIM_VERDICT.new;
      return (<Panel key={i} withBorder p="sm"><Stack gap={4}>
        <Group gap="xs"><Text size="sm">{c.subject} → <span title={c.relation}>{humanRelation(c.relation)}</span> → {c.value}</Text><Pill size="xs" tone={v.tone}>{t(v.label)}</Pill></Group>
        {c.valid_from && <Text size="xs" c="dimmed">{t("vigente desde {{date}}", { date: fmtDay(c.valid_from) })}</Text>}
        {v.facts && c.facts.length > 0 && <>
          <Text size="xs" c="dimmed">{c.applied ? t("Aplicada el {{at}}.", { at: fmt(c.applied.at) }) : t(v.facts)}</Text>
          {c.facts.map((f) => <Text key={f.uuid} size="xs">«{f.fact}» <code>{f.uuid}</code></Text>)}</>}
      </Stack></Panel>);
    })}
  </Stack>);
}

/** Whether what was ingested can be found again: each new fact and its control question (issue 296). */
function SelfTest({ s }: { s: NonNullable<Prop["selftest"]> }) {
  const { t } = useTranslation();
  if (s.skipped) return <Text size="xs" c="dimmed">{t("Sin comprobar si se recupera: este brain ya hizo todas las comprobaciones de esta hora.")}</Text>;
  if (s.error) return <Text size="xs" c="dimmed">{t("No se pudo comprobar si se recupera: {{e}}", { e: s.error })}</Text>;
  if (s.retrievable === null || s.retrievable === undefined) return null;
  if (s.retrievable) return <Text size="xs" c="dimmed">{t("Comprobado: cada hecho nuevo sale al preguntar por él.")}</Text>;
  return (<Notice tone="warn" title={t("Ingerida, pero no se recupera")}><Stack gap={4}>
    {(s.results ?? []).filter((r) => !r.found).map((r) => <Text key={r.fact_uuid} size="xs">«{r.fact}» {t("no sale al preguntar «{{q}}».", { q: r.question })}{r.outranked_by.length ? ` ${t("Salen antes: {{v}}.", { v: r.outranked_by.map((x) => `«${x}»`).join(", ") })}` : ""}</Text>)}
    <Text size="xs" c="dimmed">{t("Para arreglarlo: reescribe el hecho con el nombre con que se pregunta, añade un alias a la entidad o invalida los hechos que lo tapan.")}</Text>
  </Stack></Notice>);
}

/** A proposal as a curator reads it: what it says (or the correction it asks for), its secrets and its life so far. */
function ProposalBody({ d, ops, context, inQueue }: { d: Prop; ops: Ops; context?: ReactNode;
  /** Shown in the review queue, where every proposal is pending: its state and the usual kind (adding) go without saying. */ inQueue?: boolean }) {
  const { t } = useTranslation();
  const paired = pairedFact(d, useRelated(ops, d).data?.facts);  // the fact it is read against: its text marks what it adds
  const marks = !inQueue || d.kind === "correction" || d.confidence !== null;
  return (<Stack gap="sm">
    {marks && <Group gap="xs">{(!inQueue || d.kind === "correction") && <KindPill kind={d.kind} />}{!inQueue && <Pill tone={TONE[d.status]}>{t(LABEL[d.status] ?? d.status)}</Pill>}
      {d.confidence !== null ? <Text size="xs" c="dimmed">{t("Confianza declarada por el autor:")} <span className="ms-data">{fmtNum(d.confidence)}</span></Text>
        : !inQueue && <Text size="xs" c="dimmed">{t("Confianza declarada por el autor:")} {t("no indicada")}</Text>}</Group>}
    {d.purged_at ? <Notice tone="info">{t("El texto de esta propuesta rechazada se purgó el {{d}} por el plazo de retención del brain. Quedan su estado, sus autores y sus fechas.", { d: fmt(d.purged_at) })}</Notice>
      : d.correction ? <CorrectionDetail c={d.correction} replacement={d.body} />
        : paired ? <AddedText d={d} fact={paired} /> : <Text className="ms-prose ms-proposal-text">{d.body}</Text>}
    {!!d.claims?.length && <ClaimsDetail claims={d.claims} />}
    <SecretsNotice found={d.secrets} />
    {context}
    {inQueue && d.status === "pending" && !d.correction ? <Stack gap={4}>
      <Text size="xs" c="dimmed">{t("Enviada por {{who}}", { who: who(d) })} · <span className="ms-data">{fmt(d.created_at)}</span> · {[d.source_description, t(SOURCE[d.source] ?? d.source)].filter(Boolean).join(" · ")}</Text>
      <DeciderView d={d} />
    </Stack> : <Steps label={t("Historia de la propuesta")}>
      <Step title={t("Enviada")} tone="success"><Text size="xs" c="dimmed"><span title={d.author}>{who(d)}</span> · {fmt(d.created_at)}</Text>
        <Text size="xs" c="dimmed">{t("Procedencia:")} {d.source_description || t("no indicada")} · {t(SOURCE[d.source] ?? d.source)}</Text></Step>
      <Step title={t("Revisión")} tone={d.status === "rejected" ? "danger" : d.status === "pending" ? "warn" : "success"}>
        {d.review_kind === "direct" && <Text size="xs" c="dimmed">{t("Aprobada al enviar (el autor es curador o superior) ·")} {fmt(d.reviewed_at)}</Text>}
        {d.review_kind === "webhook" && <Text size="xs" c="dimmed">{t("Aprobada al llegar por un webhook de confianza ·")} {fmt(d.reviewed_at)}</Text>}
        {d.review_kind === "human" && <Text size="xs" c="dimmed">{d.status === "rejected" ? t("Rechazada") : t("Aprobada")} {d.reviewer ? t("por {{who}} ·", { who: d.reviewer }) : t("por un curador ·")} {fmt(d.reviewed_at)}{d.review_note ? ` · «${d.review_note}»` : ""}</Text>}
        <DeciderView d={d} />
        {!d.review_kind && !d.decision && d.status === "pending" && <Text size="xs" c="dimmed">{t("Pendiente de un curador.")}</Text>}
        {!d.review_kind && !d.decision && d.status !== "pending" && d.review_note && <Text size="xs" c="dimmed">{d.review_note}</Text>}
      </Step>
      {d.correction && <Step title={t("Hecho invalidado")} tone={d.correction.reverted_at ? "neutral" : d.correction.applied_at ? "success" : "neutral"}>
        {d.correction.applied_at ? <Text size="xs" c="dimmed">{t("Invalidado con fecha {{date}} · aplicado {{at}}", { date: fmtDay(d.correction.invalid_at), at: fmt(d.correction.applied_at) })}</Text>
          : <Text size="xs" c="dimmed">{t("Se invalidará al aprobarla, con fecha {{date}}.", { date: fmtDay(d.correction.invalid_at) })}</Text>}
        {d.correction.reverted_at && <Text size="xs" c="dimmed">{t("Reactivado después · {{at}}", { at: fmt(d.correction.reverted_at) })}</Text>}
      </Step>}
      {(!d.correction || d.body.trim()) && <Step title={d.correction ? t("Ingesta del sustituto") : t("Ingesta en el grafo")} tone={d.status === "ingested" ? "success" : d.status === "failed" ? "danger" : "neutral"}>
        {d.status === "ingested" && <Group gap="xs"><Text size="xs" c="dimmed">{fmt(d.ingested_at)}</Text>
          {d.episode_uuid && <Btn size="row" kind="link" component={Link} to={`/diario?episodio=${d.episode_uuid}`}>{t("Ver el episodio en Diario")}</Btn>}
          {d.episode_uuid && <CopyBtn value={d.episode_uuid} label={t("Copiar id")} doneLabel={t("Copiado")} />}</Group>}
        {d.status === "ingested" && d.ingest_report && <Text size="xs" c="dimmed">{d.ingest_report.entities === 1 ? t("1 entidad") : t("{{n}} entidades", { n: d.ingest_report.entities })}{d.ingest_report.untyped_entities ? ` (${t("{{n}} sin tipo", { n: d.ingest_report.untyped_entities })})` : ""} · {d.ingest_report.edges === 1 ? t("1 hecho") : t("{{n}} hechos", { n: d.ingest_report.edges })}{d.ingest_report.ontology ? (d.ingest_report.off_ontology.length ? t(" · fuera de la ontología: {{v}}", { v: d.ingest_report.off_ontology.join(", ") }) : t(" · todos dentro de la ontología")) : t(" · sin ontología")}{d.ingest_report.aliased_edges ? t(" · {{aliased_edges}} relaciones normalizadas por alias", { aliased_edges: d.ingest_report.aliased_edges }) : ""}{d.ingest_report.auto_merged?.length ? t(" · fusionadas con su principal: {{v}}", { v: d.ingest_report.auto_merged.join(", ") }) : ""}{d.ingest_report.merge_ambiguous?.length ? t(" · sin fusionar por ambiguas: {{v}}", { v: d.ingest_report.merge_ambiguous.join(", ") }) : ""}</Text>}
        {d.status === "failed" && <Notice tone="danger">{t("Falló:")} {d.ingest_error || t("error sin detalle")}{" "}
          <Btn kind="link" component={Link} to="/trabajos">{t("Ver los trabajos")}</Btn> · <Btn kind="link" component={Link} to="/admin?seccion=llm">{t("Revisar el modelo LLM")}</Btn></Notice>}
        {d.status === "approved" && <Text size="xs" c="dimmed">{t("Pendiente de ingestar.")}</Text>}
        {d.status === "ingested" && d.selftest && <SelfTest s={d.selftest} />}
        {d.status === "pending" && <Text size="xs" c="dimmed">{t("Cuando se apruebe.")}</Text>}
        {d.status === "rejected" && <Text size="xs" c="dimmed">{t("No entra en el grafo.")}</Text>}
      </Step>}
    </Steps>}
  </Stack>);
}

/** What the decider said about a proposal, when it looked at it: its model and threshold, its two answers and its verdict. */
function DeciderView({ d }: { d: Prop }) {
  const { t } = useTranslation();
  if (d.decision?.error) return <Notice tone="warn">{t("Decisor «{{engine}}» no disponible: {{error}}", { engine: d.decision.engine, error: d.decision.error })}</Notice>;
  if (!d.decision) return null;
  return (<Stack gap={2}>
    <Text size="xs" c="dimmed">{t("Decisor «{{engine}}» ({{model}}), umbral {{threshold}}:", { engine: d.decision.engine, model: d.decision.model, threshold: fmtNum(d.decision.threshold) })}</Text>
    <Text size="xs" c="dimmed">{t("· ¿Es factual? {{answer}} (confianza {{prob}})", { answer: d.decision.factual.letter === "A" ? t("sí") : t("no"), prob: fmtNum(d.decision.factual.prob) })}</Text>
    <Text size="xs" c="dimmed">{t("· Acción: {{action}} (confianza {{prob}})", { action: [t("aprobar"), t("revisar"), t("rechazar")][d.decision.action.index], prob: fmtNum(d.decision.action.prob) })}</Text>
    <Text size="xs" fw={600}>{d.decision.verdict === "approve" ? t("Aprobada automáticamente") : t("Derivada a un curador")}: {d.decision.note}</Text></Stack>);
}

/** Everything a screen of this page needs to decide: shared so the queue, the history and one's own proposals act the same way. */
type Ops = {
  base: string; graph: string; isCurator: boolean; llm: boolean; note: string; setNote: (v: string) => void;
  review: UseMutationResult<Prop & { undo_seconds?: number }, Error, { id: number; verb: Verb; note?: string }>;
  undo: UseMutationResult<unknown, Error, number[]>; reactivate: UseMutationResult<unknown, Error, number>; retry: UseMutationResult<unknown, Error, number>;
  setLast: (d: Decision) => void; refresh: () => void; openDetail: (id: number) => void;
  /** The last decision, its notice (for the review footer to dock) and the way to take it back from the keyboard. */
  last: Decision | null; notice: (docked?: { openId: number | null }) => ReactNode; setDocked: (on: boolean) => void; undoLast: () => void;
  /** Bumped by the N key to open the note; whether «Qué pasa al decidir» is unfolded (kept while moving through the queue). */
  noteKey: number; openNote: () => void; explain: boolean; setExplain: (on: boolean) => void;
};

/** What the brain already knows close to a proposal (a recall of its text, facts only), so the curator checks it against something: a
 *  duplicate, a contradiction, or nothing at all, which makes it new knowledge. Only for pending proposals that add knowledge. */
type RelatedFact = { uuid: string; fact: string; name: string; source: string; target: string; source_uuid?: string | null; target_uuid?: string | null;
  valid_at: string | null; invalid_at: string | null; score?: number | null; relevance?: "repeats" | "close" | "related";
  /** More than half of the proposal's words are not in this fact (the API's `mostly_new`). */ mostly_new?: boolean };
/** What the brain already knows close to a pending proposal that adds knowledge: one query, shared by the panel, the decision and the
 *  A key. Opening it also refreshes the verdict the queue ranks by. */
function useRelated(ops: Ops, d?: Prop) {
  const on = ops.isCurator && !!d && d.status === "pending" && !d.correction && !d.purged_at;
  return useQuery({ queryKey: ["proposal", ops.graph, d?.id, "related"], enabled: on, staleTime: 60_000,
    queryFn: () => get<{ facts: RelatedFact[] }>(`${ops.base}/${d!.id}/related`) });
}
/** «duplicate» when a current fact says nearly the same, «stale» when a close one stopped being true (as the API decides); with the
 *  fact that makes it so, for the confirmation to quote. Until the facts arrive, the verdict stored with the proposal. */
type Known = { verdict: "duplicate" | "stale"; fact?: RelatedFact } | null;
/** The fact a proposal is read against: the one that makes it known, or else the closest current one. None until the facts arrive. */
function pairedFact(d: Prop, facts?: RelatedFact[]): RelatedFact | undefined {
  if (!facts) return undefined;
  const near = facts.filter((f) => f.relevance === "close" && !f.invalid_at);  // the one it adds least to first
  return knownOf(d, facts)?.fact ?? near.find((f) => !f.mostly_new) ?? near[0];
}
function knownOf(d: Prop | undefined, facts?: RelatedFact[]): Known {
  if (!d || d.status !== "pending" || d.correction) return null;
  if (!facts) return d.related_verdict === "duplicate" || d.related_verdict === "stale" ? { verdict: d.related_verdict } : null;
  const dup = facts.find((f) => f.relevance === "repeats" && !f.invalid_at);
  if (dup) return { verdict: "duplicate", fact: dup };
  // close to something no longer true and saying mostly the same, as the API decides: a mostly new proposal does not put the old fact back
  const old = facts.find((f) => (f.relevance === "repeats" || (f.relevance === "close" && !f.mostly_new)) && f.invalid_at);
  return old ? { verdict: "stale", fact: old } : null;
}
const isKnown = (p: Prop) => p.related_verdict === "duplicate" || p.related_verdict === "stale";
/** A fact quoted inside a sentence: its own final stop goes, so «…» is not followed by a second one. */
const quoted = (fact: string) => fact.replace(/[\s.]+$/, "");
/** Rejecting what the brain already knows: the button that says why, and the note it leaves when the curator wrote none. */
const knownReject = (k: NonNullable<Known>, t: TFunction) => k.verdict === "duplicate" ? t("Rechazar: ya lo sabe") : t("Rechazar: ya no es cierto");
/** The reason alone, for a button that shows it only where there is room for it. */
const knownWhy = (k: NonNullable<Known>, t: TFunction) => k.verdict === "duplicate" ? t("ya lo sabe") : t("ya no es cierto");
const knownNote = (k: NonNullable<Known>, t: TFunction) => k.verdict === "duplicate"
  ? (k.fact ? t("El brain ya lo sabe: «{{fact}}».", { fact: quoted(k.fact.fact) }) : t("El brain ya lo sabe."))
  : (k.fact ? t("Ya no es cierto: «{{fact}}» dejó de serlo el {{date}}.", { fact: quoted(k.fact.fact), date: fmtDay(k.fact.invalid_at) }) : t("Se parece a algo que dejó de ser cierto."));
/** Approving a proposal that adds knowledge waits until the check of what the brain knows answers: before it, nobody can tell a duplicate.
 *  A proposal with a secret to review asks anyway, and a check that failed shows its error instead of holding the decision. */
const isChecking = (d: Prop | undefined, rel: { isPending: boolean }) => !!d && d.status === "pending" && !d.correction && !d.purged_at && !flagged(d) && rel.isPending;
/** A pending addition never checked against what the brain knows (it arrived without an engine, or the check failed): a batch leaves it
 *  aside, as the API does, until the queue has checked it. */
const isUnchecked = (p: Prop, llm: boolean) => llm && p.status === "pending" && p.kind !== "correction" && !p.purged_at && !p.related_verdict;
/** One fact the brain knows: its text (struck through when no longer true) with how close it is, then who it joins and its dates. */
function FactLine({ f }: { f: RelatedFact }) {
  const { t } = useTranslation();
  return (<Stack gap={2}>
    <Group gap={6} wrap="nowrap" align="flex-start">
      <Text size="sm" className={f.invalid_at ? "ms-fact-old" : undefined}>{f.fact}</Text>
      {f.invalid_at && f.relevance !== "related" ? <Pill size="xs" tone="danger">{t("Ya no es cierto")}</Pill>
        : f.relevance === "repeats" ? <Pill size="xs" tone="neutral">{t("Casi igual")}</Pill>
        : f.relevance === "close" && !f.mostly_new ? <Pill size="xs" tone="neutral">{t("Muy parecido")}</Pill> : null}
    </Group>
    <Text size="xs" c="dimmed">
      {f.source_uuid ? <Link to={`/entidad/${f.source_uuid}`}>{f.source}</Link> : f.source} → <span title={f.name}>{humanRelation(f.name)}</span> → {f.target_uuid ? <Link to={`/entidad/${f.target_uuid}`}>{f.target}</Link> : f.target}
      {f.valid_at ? ` · ${t("vigente desde {{date}}", { date: fmtDay(f.valid_at) })}` : ""}{f.invalid_at ? ` · ${t("ya no es cierto: invalidado el {{date}}", { date: fmtDay(f.invalid_at) })}` : ""}
      {f.score != null && <> · {t("similitud")} <span className="ms-data">{fmtNum(f.score)}</span></>}
    </Text>
  </Stack>);
}

/** The proposal's text with what it adds to a fact marked: its words (four letters or more, as the API counts them) the fact does not
 *  have. `added` says how many, to explain the marks only when there are some. */
// A word as the API counts it (`api/mimirsynth/proposals.py`: _WORD, STOP, STEM_ENDS, _stem; keep them together): an identifier
// (pve-norte-02, nas01.lab) is one word; a word of content is four letters or more, or anything with a digit, and not one of the words
// that say nothing about the content; words are compared without accents and by a light stem («replica», «replicar»).
const STOP_WORDS = `como para desde entre sobre pero tras hasta cuando donde porque aunque mientras según durante este esta estos estas esos esas aquel
aquella todo toda todos todas otro otra otros otras cada mucho mucha muchos muchas poco poca algo nada también tampoco solo sólo ahora
antes después luego aquí allí allá está están estaba estaban será serán sido siendo había habían tiene tienen tenía puede pueden hace
hacen sigue siguen queda quedan mismo misma mismos mismas their there these those this that with from have been were into than then also some when where which
what about will would should could while after before other more most only such very`;
const fold = (w: string) => w.toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
const STOP = new Set(STOP_WORDS.split(/\s+/).map(fold));
const STEM_ENDS = ["aciones", "acion", "amente", "mente", "ando", "iendo", "ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida", "an", "en",
  "ar", "er", "ir", "es", "s", "a", "o", "e"];
const stem = (w: string) => {
  if (!/^\p{L}+$/u.test(w)) return w;  // an identifier or a number stays as it is
  for (;;) {
    const end = STEM_ENDS.find((e) => w.endsWith(e) && w.length - e.length >= 4);
    if (!end) return w;
    w = w.slice(0, -end.length);
  }
};
/** The word as it is compared, or null when it is not a word of content. */
const wordKey = (raw: string) => { const w = fold(raw); return (w.length >= 4 || /\d/.test(w)) && !STOP.has(w) ? stem(w) : null; };
const WORD = /([\p{L}\p{N}_](?:[\p{L}\p{N}_.-]*[\p{L}\p{N}_])?)/u;
const words = (text: string) => text.match(new RegExp(WORD.source, "gu")) ?? [];
/** The proposal's text read against a fact: the words it adds, each once, and the text with every word it adds marked. Always what it
 *  adds, so a mark means one thing; how much of it is new is the API's word (`mostly_new`), said as a label. */
function addedTo(text: string, fact: string) {
  const have = new Set(words(fact).map(wordKey).filter(Boolean));
  const parts = text.split(WORD);  // the words at odd positions, what lies between them at even ones
  const adds = (w: string) => { const k = wordKey(w); return k !== null && !have.has(k); };
  const added = new Map<string, string>();  // each word it adds once, as it is written
  for (const w of words(text)) if (adds(w) && !added.has(wordKey(w)!)) added.set(wordKey(w)!, w);
  return { words: [...added.values()], node: <>{parts.map((p, i) => i % 2 === 1 && adds(p) ? <mark key={i} className="ms-added">{p}</mark> : p)}</> };
}

/** The proposal's text read against the fact the brain already says (below, in «Lo que dice el brain»): what it adds marked, with the
 *  legend right above it, and a screen reader told the words. */
function AddedText({ d, fact }: { d: Prop; fact: RelatedFact }) {
  const { t } = useTranslation();
  const a = addedTo(d.body, fact.fact);
  return (<Stack gap={6}>
    <Group gap={8} className="ms-added-legend">
      {a.words.length === 0 ? <Text size="xs" c="dimmed">{fact.invalid_at ? t("El texto repite lo que dice el brain, abajo, y eso ya no es cierto.")
        : t("El texto no añade ninguna palabra de contenido a lo que dice el brain, abajo.")}</Text>
        : <>{fact.mostly_new && <Pill tone="neutral">{t("Mayormente nuevo")}</Pill>}
          <Text size="xs" c="dimmed"><mark className="ms-added">{t("Subrayado")}</mark>{" "}{t("lo que añade a lo que dice el brain, abajo.")}
            <span className="ms-sr">{" "}{t("Añade: {{words}}.", { words: a.words.join(", ") })}</span></Text></>}
    </Group>
    <Text className="ms-prose ms-proposal-text">{a.node}</Text>
  </Stack>);
}

/** What the brain already knows close to a pending proposal that adds knowledge. When it is a likely duplicate, close to something no
 *  longer true, or very close to a current fact, the proposal and that fact are set side by side, with what the proposal adds marked, to
 *  read one against the other. Other very similar facts follow; facts that are only related stay folded, so they do not read as evidence. */
function RelatedFacts({ d, ops }: { d: Prop; ops: Ops }) {
  const { t } = useTranslation();
  const q = useRelated(ops, d);
  const [more, setMore] = useState(false);
  useEffect(() => setMore(false), [d.id]);
  const facts = q.data?.facts ?? [];
  const known = q.data ? knownOf(d, facts) : null;
  const paired = pairedFact(d, q.data?.facts);
  const close = facts.filter((f) => (f.relevance === "repeats" || f.relevance === "close") && f.uuid !== paired?.uuid);
  const related = facts.filter((f) => f.relevance === "related");
  // the one line to read first. A contradiction cannot be told from the text alone: the closest facts are there to check it.
  const verdict = known?.verdict === "duplicate" ? { icon: "alert" as const, text: t("Posible duplicado: el brain ya dice algo casi igual.") }
    : known?.verdict === "stale" ? { icon: "alert" as const, text: t("Se parece a algo que dejó de ser cierto: comprueba que la propuesta no lo vuelve a dar por bueno.") }
      : [paired, ...close].some((f) => f && !f.mostly_new) ? { icon: "info" as const, text: t("Muy parecido a algo que el brain ya sabe: comprueba qué añade la propuesta.") }
        : paired ? { icon: "info" as const, text: t("Mayormente nuevo: comparte el tema con algo que el brain ya sabe, y casi todo lo que dice es nuevo.") }
        : related.length ? { icon: "info" as const, text: t("Nada casi igual en el brain: sería conocimiento nuevo.") } : null;
  return (<section className="ms-related" aria-labelledby={`ms-related-${d.id}`}><Stack gap={8}>
    <Text component="h3" id={`ms-related-${d.id}`} className="ms-section-title">{t("Lo que el brain ya sabe")}</Text>
    <MutationError error={q.error} />
    {!q.data && !q.error && <EmptyState>{t("Buscando lo relacionado…")}</EmptyState>}
    {q.data && facts.length === 0 && <Text size="xs" c="dimmed">{t("Nada parecido en el brain: sería conocimiento nuevo.")}</Text>}
    {verdict && (known ? <Notice tone="warn">{verdict.text}</Notice>
      : <Group gap={6} wrap="nowrap" align="flex-start"><Icon name={verdict.icon} size={16} /><Text size="sm" fw={600}>{verdict.text}</Text></Group>)}
    {paired && <div className="ms-pair">
      <Text size="xs" fw={600} c="dimmed">{t("Lo que dice el brain")}</Text>
      <FactLine f={paired} />
    </div>}
    {close.map((f) => <FactLine key={f.uuid} f={f} />)}
    {related.length > 0 && <Group><Btn kind="link" className="ms-hit" icon={more ? "chevronDown" : "chevronRight"} aria-expanded={more} aria-controls={`ms-rel-${d.id}`}
      onClick={() => setMore(!more)}>{related.length === 1 ? t("1 hecho solo relacionado") : t("{{n}} hechos solo relacionados", { n: related.length })}</Btn></Group>}
    {related.length > 0 && <Stack gap={8} id={`ms-rel-${d.id}`} className="ms-fold" hidden={!more}>{related.map((f) => <FactLine key={f.uuid} f={f} />)}</Stack>}
  </Stack></section>);
}

/** The decision on a pending proposal: a note, what each button will do, and Reject / Approve (each with its own progress).
 *  With secrets flagged for review, Approve becomes «Mask and approve», behind a confirmation that names the kinds of secret; `masking`
 *  lets the queue open that confirmation from its A shortcut. */
function DecisionBlock({ d, ops, onDecided, masking, onMasking, waiting, onApprove }: { d: Prop; ops: Ops; onDecided?: () => void; masking?: boolean; onMasking?: (on: boolean) => void;
  /** The whole proposal is still loading: the buttons stay where they are, disabled. */ waiting?: boolean;
  /** The queue's way to approve, the same as its A key: it asks first when it must and moves on to the next proposal. */ onApprove?: () => void }) {
  const { t } = useTranslation();
  const { review } = ops;
  const [ownMasking, setOwnMasking] = useState(false);
  const askMask = onMasking ?? setOwnMasking;
  const secret = flagged(d);
  const rel = useRelated(ops, d);
  const known = knownOf(d, rel.data?.facts);
  const checking = isChecking(d, rel);
  const asks = secret || !!known;  // approving asks first: to mask what was flagged, or because the brain already knows it
  const kinds = [...new Set((d.secrets ?? []).filter((f) => f.action === "flagged").map((f) => t(f.label)))].join(", ");
  const approving = review.isPending && review.variables?.verb !== "reject";
  const decide = (verb: Verb, note?: string) => review.mutateAsync({ id: d.id, verb, note }).then(() => onDecided?.());
  const rejectKnown = known && !secret ? () => decide("reject", ops.note || knownNote(known, t)) : null;  // with its reason as the note
  const approve = onApprove ?? (() => { if (!checking) { if (asks) askMask(true); else decide("approve").catch(() => {}); } });
  // the note is optional: it opens on «+ Nota» (or N in the queue) and stays open while it has text; what each button does is one fold
  // away, except what must be read before approving (a correction invalidates a fact; flagged secrets get masked)
  const noteId = `ms-note-${d.id}`;
  const [noteOpen, setNoteOpen] = useState(false);
  useEffect(() => setNoteOpen(false), [d.id]);
  const [focusNote, setFocusNote] = useState(0);
  useEffect(() => { if (focusNote) document.getElementById(noteId)?.focus(); }, [focusNote]);  // eslint-disable-line react-hooks/exhaustive-deps
  const openNote = () => { setNoteOpen(true); setFocusNote((k) => k + 1); };  // focused once it is rendered
  const seenNoteKey = useRef(ops.noteKey);
  useEffect(() => { if (ops.noteKey !== seenNoteKey.current) { seenNoteKey.current = ops.noteKey; openNote(); } }, [ops.noteKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  const showNote = noteOpen || !!ops.note;
  return (<Stack gap="xs">
    {showNote && <TextArea id={noteId} autosize minRows={1} maxRows={4} label={t("Nota (opcional)")} value={ops.note} onChange={(e) => ops.setNote(e.currentTarget.value)}
      description={<span className="ms-inbox-keys"><kbd>{t("Ctrl")}</kbd>+<kbd>{t("Intro")}</kbd> {t("aprueba")} · <kbd>{t("Esc")}</kbd> {t("sale de la nota")}</span>}
      onKeyDown={(e) => {  // the keyboard loop goes on from the note: Esc back to the proposal, Ctrl+Enter approves as A does
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); e.currentTarget.blur(); document.getElementById(`ms-title-${d.id}`)?.focus(); }
        else if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !waiting && !review.isPending) { e.preventDefault(); approve(); }
      }} />}
    {(secret || d.correction) && <Stack gap={2}>
      {secret && <Text size="xs" c="dimmed">{t("Antes de aprobar, lo marcado como secreto ({{kinds}}) se tapa en el título y el texto.", { kinds })}</Text>}
      {d.correction && <Text size="xs" c="dimmed">{t("Al aprobar, el hecho se invalida con fecha {{date}}; se puede reactivar después.", { date: fmtDay(d.correction.invalid_at) })}</Text>}
    </Stack>}
    <MutationError error={review.error} />
    <Group justify="space-between" gap="xs">
      <Group gap="xs">
        {!showNote && <Btn kind="link" icon="plus" className="ms-hit" onClick={openNote}>{t("Nota")}</Btn>}
        <Btn kind="link" className="ms-hit" icon={ops.explain ? "chevronDown" : "chevronRight"} aria-expanded={ops.explain} aria-controls={`ms-why-${d.id}`}
          onClick={() => ops.setExplain(!ops.explain)}>{t("Qué pasa al decidir")}</Btn>
      </Group>
      <Group gap="xs" className="ms-decide">
        <Btn kind="danger" loading={review.isPending && review.variables?.verb === "reject"} disabled={waiting || (review.isPending && review.variables?.verb !== "reject")}
          aria-label={known && !secret ? knownReject(known, t) : undefined}
          onClick={() => (rejectKnown ? rejectKnown() : decide("reject")).catch(() => {})} icon="close">{t("Rechazar")}{known && !secret && <span className="ms-reject-why">: {knownWhy(known, t)}</span>}</Btn>
        <Btn kind="primary" loading={approving} disabled={waiting || (review.isPending && !approving) || (checking && !onApprove)} title={checking ? t("Antes de aprobar, se comprueba lo que el brain ya sabe") : undefined}
          aria-label={checking ? `${secret ? t("Enmascarar y aprobar") : t("Aprobar")}: ${t("Antes de aprobar, se comprueba lo que el brain ya sabe")}` : undefined}
          onClick={approve} icon={checking ? undefined : secret ? "lock" : "check"} leftSection={checking ? <Loader size={14} color="currentColor" /> : undefined}>{secret ? t("Enmascarar y aprobar") : t("Aprobar")}</Btn>
      </Group>
    </Group>
    <Stack gap={2} id={`ms-why-${d.id}`} className="ms-fold" hidden={!ops.explain}>
      {!d.correction && <Text size="xs" c="dimmed">{ops.llm
        ? t("Al aprobar, el texto entra en el brain como un episodio y el modelo extrae de él entidades y hechos. Tendrás unos segundos para deshacerlo.")
        : t("Al aprobar, se queda en «Aprobadas» hasta que haya un motor de extracción.")}</Text>}
      <Text size="xs" c="dimmed">{t("Al rechazar, no entra nada en el grafo y se puede reabrir después.")}</Text>
    </Stack>
    {!secret && known && <ConfirmDialog opened={onMasking ? !!masking : ownMasking} onClose={() => askMask(false)} tone="primary" warn
      alt={{ label: knownReject(known, t), icon: "close", onConfirm: () => decide("reject", ops.note || knownNote(known, t)) }}
      title={known.verdict === "duplicate" ? t("¿Aprobar un posible duplicado?") : t("¿Aprobar algo parecido a un hecho que ya no es cierto?")}
      warning={known.verdict === "duplicate"
        ? (known.fact ? t("El brain ya dice algo casi igual: «{{fact}}». Si la apruebas, el grafo tendrá lo mismo dos veces.", { fact: quoted(known.fact.fact) })
          : t("El brain ya dice algo casi igual. Si la apruebas, el grafo tendrá lo mismo dos veces."))
        : (known.fact ? t("Se parece a «{{fact}}», que dejó de ser cierto el {{date}}. Apruébala solo si vuelve a ser cierto.", { fact: quoted(known.fact.fact), date: fmtDay(known.fact.invalid_at) })
          : t("Se parece a algo que dejó de ser cierto. Apruébala solo si vuelve a ser cierto."))}
      subject={<><span className="ms-data">#{d.id}</span> · {d.name}</>}
      action={t("Aprobar igualmente")} onConfirm={() => decide("approve")} />}
    <ConfirmDialog opened={secret && (onMasking ? !!masking : ownMasking)} onClose={() => askMask(false)} tone="primary"
      title={t("¿Enmascarar y aprobar la propuesta #{{id}}?", { id: d.id })}
      warning={t("Se tapa lo marcado como secreto ({{kinds}}) en el título y el texto, y después se aprueba. El valor original no se guarda: aunque deshagas la aprobación, no vuelve.", { kinds })}
      action={t("Enmascarar y aprobar")} onConfirm={() => decide("mask-and-approve")} />
  </Stack>);
}

/** The actions on a decided proposal: retry or start its ingestion, reopen or undo the approval, reactivate a corrected fact. */
function AfterActions({ d, ops }: { d: Prop; ops: Ops }) {
  const { t } = useTranslation();
  const { retry, undo, reactivate, review } = ops;
  if (!ops.isCurator) return null;
  return (<>
    {(d.status === "failed" || d.status === "approved") && <Group justify="flex-end">
      <MutationError error={retry.error} />
      {d.status === "failed" && <MutationError error={review.error} />}
      {d.status === "failed" && <Btn kind="secondary" loading={review.isPending} disabled={retry.isPending} onClick={() => review.mutate({ id: d.id, verb: "reject" })}>{t("Rechazar")}</Btn>}
      <Btn kind="primary" disabled={review.isPending} loading={retry.isPending} onClick={() => retry.mutate(d.id)}>{d.status === "failed" ? t("Reintentar ingesta") : t("Ingerir ahora")}</Btn></Group>}
    {((d.status === "rejected" && !d.purged_at) || (d.status === "approved" && d.kind !== "correction")) && <Group justify="flex-end">
      <MutationError error={undo.error} />
      <Btn kind="secondary" loading={undo.isPending} onClick={() => undo.mutate([d.id])} icon="undo">{d.status === "rejected" ? t("Reabrir") : t("Deshacer la aprobación")}</Btn></Group>}
    {d.correction?.applied_at && !d.correction.reverted_at && <Group justify="flex-end">
      <MutationError error={reactivate.error} />
      <Btn kind="secondary" loading={reactivate.isPending} onClick={() => reactivate.mutate(d.id)} icon="undo">{t("Reactivar el hecho")}</Btn></Group>}
  </>);
}

/** A proposal opened from a table (the history, one's own): its detail and what can still be done with it. */
function ProposalModal({ open, onClose, ops }: { open: number | null; onClose: () => void; ops: Ops }) {
  const { t } = useTranslation();
  const detail = useQuery({ queryKey: ["proposal", ops.graph, open], enabled: open !== null, queryFn: () => get<Prop>(`${ops.base}/${open}`) });
  const d = detail.data;
  return (
    <Modal opened={open !== null} onClose={onClose} title={d ? `#${d.id} · ${d.purged_at ? t("(texto purgado)") : d.name}` : t("Propuesta")} size="lg" centered>
      <MutationError error={detail.error} />
      {d && <Stack gap="sm">
        <ProposalBody d={d} ops={ops} context={ops.isCurator && d.status === "pending" && !d.correction ? <RelatedFacts d={d} ops={ops} /> : undefined} />
        <AfterActions d={d} ops={ops} />
        {ops.isCurator && d.status === "pending" && <DecisionBlock d={d} ops={ops} onDecided={onClose} />}
      </Stack>}
    </Modal>
  );
}

/** A server-paged table of proposals with its own filters: the review history («Decididas») or one's own proposals (`mine`). */
function HistoryTable({ ops, mine, statuses, first, initialStatus, initialKind, lead }: { ops: Ops; mine: boolean; statuses: string[]; first: { value: string; label: string; countKey: string };
  initialStatus?: string; initialKind?: string; /** Goes first on the row of filters. */ lead?: ReactNode }) {
  const { t } = useTranslation();
  const view = useProposalsView();
  const [status, setStatusRaw] = useState(initialStatus && statuses.includes(initialStatus) ? initialStatus : first.value);
  const [kind, setKindRaw] = useState(initialKind ?? "all");
  const setStatus = (s: string) => { setStatusRaw(s); view.setPage((p) => ({ ...p, offset: 0 })); };
  const setKind = (k: string) => { setKindRaw(k); view.setPage((p) => ({ ...p, offset: 0 })); };
  const { sent, sort, page } = view;
  const list = useQuery({ queryKey: ["proposals", ops.graph, mine ? "mine" : "all", status, kind, sent.q, sent.author, sort?.key, sort?.dir, page.offset, page.limit], placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some((p) => p.status === "approved") ? 3000 : false),  // an approved row becomes ingested or failed on its own
    queryFn: () => get<PropList>(ops.base, { status: status === "all" ? undefined : status, kind: kind === "all" ? undefined : kind, q: sent.q || undefined, author: sent.author || undefined,
      sort: sort?.key, order: sort?.dir, limit: page.limit, offset: page.offset, mine: mine || undefined }) });
  const cnt = useQuery({ queryKey: ["proposals", ops.graph, "counts", kind, mine], refetchInterval: 15000,
    queryFn: () => get<Counts>(`${ops.base}/counts`, { kind: kind === "all" ? undefined : kind, mine: mine || undefined }) });
  // the kind counts never depend on the kind chosen, only on the state: they come from the unfiltered counts
  const all = useQuery({ queryKey: ["proposals", ops.graph, "counts", "all", mine], refetchInterval: 15000,
    queryFn: () => get<Counts>(`${ops.base}/counts`, { mine: mine || undefined }) });
  const counts = cnt.data ?? {};
  const emptyAll = mine ? t("Aún no has enviado ninguna propuesta. Lo que envíes aparecerá aquí, con su estado.") : t("Aún no se ha decidido ninguna propuesta.");
  if (all.data && all.data.all === 0 && !view.active)  // nothing yet: no filters over an empty table, just say so
    return <EmptyState>{emptyAll}</EmptyState>;
  return (<>
    <MutationError error={list.error} />
    <ProposalsTable data={list.data} view={view} status={status} onStatus={setStatus} kind={kind} onKind={setKind} kindsFrom={all.data} onOpen={ops.openDetail} emptyAll={emptyAll} label={mine ? t("Mis propuestas") : t("Propuestas decididas")} lead={lead}
      statuses={[{ value: first.value, label: first.label, count: cnt.data ? counts[first.countKey] ?? 0 : undefined }, ...statuses.map((k) => ({ value: k, label: t(PLURAL[k]), count: cnt.data ? counts[k] ?? 0 : undefined }))]} />
  </>);
}

/** «To review»: the pending queue, riskiest and oldest first, beside the open proposal; J/K move, A/R decide and the next one opens;
 *  several can be checked and decided at once (approving skips corrections and secrets to review, which go one at a time). */
function ReviewTab({ ops, initialKind, onDecided }: { ops: Ops; initialKind?: string; /** Goes to the decided ones (their own tab). */ onDecided: () => void }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState(initialKind ?? "all");
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const cnt = useQuery({ queryKey: ["proposals", ops.graph, "counts", kind, false], refetchInterval: 15000, queryFn: () => get<Counts>(`${ops.base}/counts`, { kind: kind === "all" ? undefined : kind }) });
  const queue = useQuery({ queryKey: ["proposals", ops.graph, "queue", kind, offset], placeholderData: keepPreviousData, refetchInterval: 15000,
    queryFn: () => get<PropList>(ops.base, { status: "pending", kind: kind === "all" ? undefined : kind, sort: "risk", order: "asc", limit, offset }) });
  const items = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const [active, setActive] = useState<number | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  useEffect(() => {  // the open one stays open while it is in the queue; otherwise the first one opens
    if (!items.length) { setActive(null); return; }
    if (active === null || !items.some((p) => p.id === active)) setActive(items[0].id);
    setChecked((c) => new Set([...c].filter((id) => items.some((p) => p.id === id))));  // nothing hidden stays selected
  }, [items]);  // eslint-disable-line react-hooks/exhaustive-deps
  // the open one shows at once from its queue row (its text cut at 300 characters) while the whole proposal loads, so moving through
  // the queue never blanks the detail or unmounts the decision
  const detail = useQuery({ queryKey: ["proposal", ops.graph, active], enabled: active !== null, queryFn: () => get<Prop>(`${ops.base}/${active}`),
    placeholderData: () => items.find((p) => p.id === active) });
  // a cached copy can lag behind the queue (a proposal reopened by an undo still cached as rejected): the queue row wins until it reloads
  const row = items.find((p) => p.id === active);
  const stale = !!row && !!detail.data && detail.data.id === active && detail.data.status !== row.status;
  const d = stale ? row : detail.data && detail.data.id === active ? detail.data : undefined;
  // shown from its queue row: deciding waits only when the row cut the text (300 characters), since the rest (secrets, kind, what the
  // brain knows) is all in the row
  const partial = (detail.isPlaceholderData || stale) && (row?.body.length ?? 0) >= 300;
  const listRef = useRef<HTMLDivElement>(null);
  // where the focus goes once the proposal it is about is on screen: its title after a decision, so a button that stays where it was
  // is never pressed again by accident; after an undo, the queue entry (or the title when the queue is hidden, on a narrow screen)
  const [focusTo, setFocusTo] = useState<"title" | "undone" | null>(null);
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);
  const [batch, setBatch] = useState<{ verb: "approve" | "reject"; items: Prop[] }>({ verb: "approve", items: [] });  // what the dialog shows: kept while it closes
  const ask = (verb: "approve" | "reject") => { setBatch({ verb, items: selected }); setConfirm(verb); };
  const [masking, setMasking] = useState(false);
  const actions = useRef<HTMLDivElement>(null);
  const footer = active !== null;
  const shown = useShown(actions, footer);
  useEffect(() => { ops.setDocked(shown); }, [shown]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => ops.setDocked(false), []);  // eslint-disable-line react-hooks/exhaustive-deps
  const [focusKey, setFocusKey] = useState(0);
  const handled = useRef<Decision | null>(null);
  const [bulkNote, setBulkNote] = useState("");
  const selected = items.filter((p) => checked.has(p.id));
  // never approved in a batch: decided one at a time (what is very close to a current fact too: it is read before it is approved)
  const oneByOne = (p: Prop) => p.kind === "correction" || flagged(p) || isKnown(p) || p.related_verdict === "similar" || isUnchecked(p, ops.llm);
  const goes = batch.verb === "approve" ? batch.items.filter((p) => !oneByOne(p)) : batch.items;
  const stays = batch.items.filter((p) => !goes.includes(p));
  const [showGoes, setShowGoes] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (confirm === null) setShowGoes(false); }, [confirm]);
  const bulk = useMutation({ mutationFn: ({ verb, ids }: { verb: "approve" | "reject"; ids: number[] }) => send<{ done: number[]; skipped: { id: number; reason: string }[]; undo_seconds?: number }>("POST", `${ops.base}/bulk`,
      { verb, ids, note: bulkNote }),
    onSuccess: (r, { verb }) => {
      ops.setLast({ id: r.done[0] ?? 0, ids: r.done, skipped: r.skipped.length, verb, until: r.undo_seconds ? Date.now() + r.undo_seconds * 1000 : null });
      setChecked(new Set(r.skipped.map((s) => s.id)));  // what was left out stays selected, to decide one at a time
      setBulkNote(""); ops.refresh();
    } });
  const open = (id: number) => { setActive(id); setShowDetail(true); ops.setNote(""); };
  const [moved, setMoved] = useState("");  // what J/K opened, for a screen reader: the focus stays where it was, so nothing else says it
  const move = (step: number) => {
    const i = items.findIndex((p) => p.id === active); const next = items[i + step];
    if (!next) return;
    open(next.id);
    setMoved(`#${next.id} · ${next.purged_at ? t("(texto purgado)") : next.name} (${t("{{i}} de {{n}}", { i: i + step + 1, n: items.length })})`);
  };
  const back = () => { setShowDetail(false); setFocusKey((k) => k + 1); };  // back to the queue, on the entry that was open
  const pos = items.findIndex((p) => p.id === active);  // where the open one is in this page of the queue
  const advance = (id: number) => {  // after a decision the next one opens, so the curator never goes back to the list
    const i = items.findIndex((p) => p.id === id);
    const next = items[i + 1] ?? items[i - 1];
    if (next && !items[i + 1]) setMoved(t("Era la última de la cola: se abre la anterior, #{{id}}.", { id: next.purged_at ? next.id : `${next.id} «${next.name}»` }));
    if (next) { setActive(next.id); ops.setNote(""); setFocusTo("title"); } else setShowDetail(false);
  };
  useEffect(() => {
    if (!focusTo || !d) return;
    if (focusTo === "undone" && listRef.current?.getClientRects().length) setFocusKey((k) => k + 1);
    else document.getElementById(`ms-title-${d.id}`)?.focus();
    setFocusTo(null);
  }, [focusTo, d?.id]);  // eslint-disable-line react-hooks/exhaustive-deps
  const detailRef = useRef<HTMLDivElement>(null);
  const inboxRef = useRef<HTMLDivElement>(null);  // the queue and the open proposal: where the single-key shortcuts act
  useEffect(() => {  // one pane at a time (the queue hidden): the proposal just opened is read from its title, not from mid-page
    if (!showDetail || active === null || listRef.current?.getClientRects().length) return;
    detailRef.current?.scrollIntoView({ block: "start" });
    document.getElementById(`ms-title-${active}`)?.focus({ preventScroll: true });  // the entry that had the focus is hidden now
  }, [showDetail, active]);  // eslint-disable-line react-hooks/exhaustive-deps
  const related = useRelated(ops, d);
  const decide = (verb: "approve" | "reject") => {
    if (!d || d.status !== "pending" || ops.review.isPending || partial) return;
    if (!actions.current?.getClientRects().length) return;  // narrow layout showing the queue: nothing is decided without being seen
    if (verb === "approve" && isChecking(d, related)) { setHeld(d.id); return; }  // approves (or asks) once the brain has answered
    if (verb === "approve" && (flagged(d) || knownOf(d, related.data?.facts))) {  // the same confirmation as its button
      // opened by a key, nothing has the focus: the title takes it first, so the dialog gives it back there when it closes
      if (!document.activeElement || document.activeElement === document.body) document.getElementById(`ms-title-${d.id}`)?.focus();
      setMasking(true); return;
    }
    const k = verb === "reject" && !flagged(d) ? knownOf(d, related.data?.facts) : null;  // rejecting what the brain knows says why
    ops.review.mutate({ id: d.id, verb, note: k && !ops.note ? knownNote(k, t) : undefined }, { onSuccess: () => advance(d.id) });
  };
  const [held, setHeld] = useState<number | null>(null);
  const checking = isChecking(d, related);
  useEffect(() => {  // an approval asked for while the check ran goes on once it answers, only for the proposal it was asked for
    if (held === null) return;
    if (held !== d?.id) setHeld(null);
    else if (!checking) { setHeld(null); decide("approve"); }
  }, [held, checking, d?.id]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // after an undo the proposal is back in the queue: it opens there and the focus returns to it, not to the page
    const l = ops.last;
    if (!l || l.verb !== "undone" || handled.current === l) return;
    const id = (l.ids ?? [l.id]).find((i) => items.some((p) => p.id === i));
    if (id === undefined) return;  // not back yet: the queue is refetching
    handled.current = l;
    // it opens again; on a narrow screen with its detail, so the notice docked under its buttons stays in view
    setActive(id); setShowDetail(true); setFocusTo("undone"); ops.setNote("");
  }, [ops.last, items]);  // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (id: number | null, on?: boolean) => {
    if (id === null) return;
    setChecked((c) => { const n = new Set(c); (on ?? !n.has(id)) ? n.add(id) : n.delete(id); return n; });
  };
  useShortcuts({ j: () => move(1), k: () => move(-1), a: () => decide("approve"), r: () => decide("reject"), x: () => toggle(focusedQueueItem() ?? active), z: () => ops.undoLast(), n: () => { if (d?.status === "pending" && actions.current?.getClientRects().length) ops.openNote(); } }, confirm === null && !masking, inboxRef);
  const counts = cnt.data ?? {};
  const pendingFixes = counts.corrections_pending ?? 0;
  const queueItems: QueueItem[] = items.map((p) => ({
    id: p.id, label: p.purged_at ? t("(texto purgado)") : p.name, title: <>{p.purged_at ? t("(texto purgado)") : p.name}</>, preview: p.correction ? p.correction.reason : p.body,
    tags: <>{p.kind === "correction" && <KindPill kind={p.kind} />}<SecretsPill found={p.secrets} />
      {p.related_verdict === "duplicate" && <Pill size="xs" tone="warn" title={t("El brain ya dice algo casi igual")}><span className="ms-pill-row"><Icon name="copy" size={12} />{t("Posible duplicado")}</span></Pill>}
      {p.related_verdict === "stale" && <Pill size="xs" tone="warn" title={t("Se parece a algo que dejó de ser cierto")}><span className="ms-pill-row"><Icon name="timeline" size={12} />{t("Posiblemente ya no es cierto")}</span></Pill>}
      {p.related_verdict === "similar" && <Pill size="xs" tone="neutral" title={t("Muy parecido a algo que el brain ya sabe: revisa qué añade")}><span className="ms-pill-row"><Icon name="search" size={12} />{t("Muy parecido")}</span></Pill>}
      {p.confidence !== null && p.confidence < LOW_CONFIDENCE && <Pill size="xs" tone="neutral"><span className="ms-pill-row"><Icon name="info" size={12} />{t("confianza {{c}}", { c: fmtNum(p.confidence) })}</span></Pill>}
      {p.decision && !p.decision.error && <Pill size="xs" tone="alt" title={[p.decision.note, p.decision.action?.prob != null ? t("seguridad del decisor: {{p}}", { p: fmtNum(p.decision.action.prob) }) : ""].filter(Boolean).join(" · ")}>{t("el decisor dudó")}</Pill>}</>,
    meta: <><span className="ms-queue-author" title={p.author}>{who(p)}</span><span className="ms-queue-age" title={fmt(p.created_at)}>{waited(p.created_at)}</span></>,
  }));
  const kinds = kindCounts(cnt.data, "pending");
  return (<>
    {(kind !== "all" || (!!kinds.memory && !!kinds.correction)) && <div className="ms-filter-row ms-review-filter">  {/* only when there is something to tell apart */}
      <Segments label={t("Tipo")} value={kind} onChange={(k) => { setKind(k); setOffset(0); }}
        data={[{ value: "all", label: t("Todas"), count: kinds.all }, { value: "memory", label: t("Añaden"), count: kinds.memory },
          { value: "correction", label: t("Corrigen"), count: kinds.correction }]} />
    </div>}
      {pendingFixes > 0 && kind !== "correction" && <Notice tone="warn" title={t("Correcciones pendientes: {{n}}", { n: pendingFixes })}>
        {t("Cada una invalida un hecho del grafo y solo la decide una persona.")}{" "}
        <Btn kind="link" onClick={() => { setKind("correction"); setOffset(0); }}>{t("Ver solo las correcciones pendientes")}</Btn></Notice>}
      <MutationError error={queue.error} />
      {queue.data && items.length === 0
        ? <EmptyState>{t("No queda nada por revisar.")}{" "}<Btn kind="link" onClick={onDecided}>{t("Ver las decididas")}</Btn></EmptyState>
        : <InboxLayout showDetail={showDetail} detailLabelledBy={d ? `ms-title-${d.id}` : undefined} listLabelledBy="ms-queue-heading" scopeRef={inboxRef}
          skip={active !== null ? { label: t("Ir a la propuesta abierta"), onSkip: () => { setShowDetail(true); setFocusTo("title"); } } : undefined}
          list={<>
            <h2 id="ms-queue-heading" className="ms-sr-only">{t("Cola de propuestas pendientes")}</h2>
            <div className="ms-inbox-bar" ref={barRef}>
              {selected.length > 0 ? <>
                <Text size="sm" fw={600} className="ms-inbox-bar-what" title={selected.some(oneByOne) ? (selected.filter(oneByOne).length === 1 ? t("1 se decide aparte: una corrección, un secreto por revisar, algo que el brain ya sabe, tiene muy parecido o aún no ha comprobado.")
                  : t("{{k}} se deciden una a una: correcciones, secretos por revisar, lo que el brain ya sabe, tiene muy parecido o aún no ha comprobado.", { k: selected.filter(oneByOne).length })) : undefined}>
                  {selected.length === 1 ? t("1 seleccionada") : t("{{n}} seleccionadas", { n: selected.length })}{selected.some(oneByOne) && <span className="ms-inbox-bar-aside"> · {t("{{k}} aparte", { k: selected.filter(oneByOne).length })}</span>}</Text>
                <Btn size="row" onClick={() => ask("approve")}>{t("Aprobar")}</Btn>
                <Btn size="row" kind="danger" onClick={() => ask("reject")}>{t("Rechazar")}</Btn>
                <IconButton icon="close" label={t("Quitar la selección")} onClick={() => { setChecked(new Set()); setTimeout(() => barRef.current?.querySelector("button")?.focus()); }} />
              </> : <>
                <Text size="sm" c="dimmed">{t("Por riesgo y antigüedad")}</Text>
                <Btn size="row" kind="ghost" onClick={() => setChecked(new Set(items.map((p) => p.id)))}>{t("Seleccionar todas")}</Btn>
              </>}
            </div>
            <div className="ms-sr-only" role="status" aria-live="polite">{moved}</div>
            <div className="ms-inbox-scroll" ref={listRef}>
              <QueueList items={queueItems} activeId={active} focusKey={focusKey} onActivate={open} onMove={(id) => { setActive(id); ops.setNote(""); }} checked={checked} onCheck={(id, on) => toggle(id, on)} label={t("Cola de propuestas pendientes")} />
            </div>
            {(queue.data?.total ?? 0) > limit && <Pager total={queue.data?.total ?? 0} offset={offset} limit={limit} onChange={(p) => setOffset(p.offset)} />}
          </>}
          detail={<>
            <div className="ms-inbox-body" ref={detailRef}>
              <div className="ms-inbox-nav">
                <Btn size="row" kind="ghost" icon="back" className="ms-hit" onClick={back}>{t("Volver a la cola")}</Btn>
                {pos >= 0 && <Group gap={6} wrap="nowrap">
                  <Text size="xs" c="dimmed" className="ms-data">{t("{{i}} de {{n}}", { i: offset + pos + 1, n: queue.data?.total ?? items.length })}</Text>
                  <IconButton icon="chevronLeft" label={t("Anterior")} onClick={() => move(-1)} disabled={pos <= 0} />
                  <IconButton icon="chevronRight" label={t("Siguiente")} onClick={() => move(1)} disabled={pos >= items.length - 1} />
                </Group>}
              </div>
              <MutationError error={detail.error} />
              {d ? <><Text component="h2" id={`ms-title-${d.id}`} tabIndex={-1} className="ms-detail-title">#{d.id} · {d.purged_at ? t("(texto purgado)") : d.name}</Text><ProposalBody d={d} ops={ops} inQueue context={d.status === "pending" && !d.correction ? <RelatedFacts d={d} ops={ops} /> : undefined} /></>
                : <EmptyState>{t("Cargando…")}</EmptyState>}
            </div>
            {footer && <div className="ms-inbox-actions" ref={actions}>
              {shown && ops.notice({ openId: active })}
              {d && d.status === "pending" && <><DecisionBlock d={d} ops={ops} onDecided={() => advance(d.id)} masking={masking} onMasking={setMasking} waiting={partial} onApprove={() => decide("approve")} />
              <Text className="ms-inbox-keys" title={t("Actúan con el foco en la cola o en la propuesta abierta.")}>{t("Atajos:")} <kbd>J</kbd>/<kbd>K</kbd> {t("moverse")} · <kbd>A</kbd> {flagged(d) ? t("enmascarar y aprobar") : t("aprobar")} · <kbd>R</kbd> {t("rechazar")} · <kbd>X</kbd> {t("seleccionar")} · <kbd>N</kbd> {t("nota")} · <kbd>Z</kbd> {t("deshacer")}</Text></>}
            </div>}
          </>} />}
    <ConfirmDialog opened={confirm !== null} onClose={() => setConfirm(null)} tone={batch.verb === "approve" ? "primary" : "danger"}
      title={batch.verb === "approve"
        ? (stays.length ? t("¿Aprobar {{n}} de {{total}}?", { n: goes.length, total: batch.items.length }) : goes.length === 1 ? t("¿Aprobar 1 propuesta?") : t("¿Aprobar {{n}} propuestas?", { n: goes.length }))
        : goes.length === 1 ? t("¿Rechazar 1 propuesta?") : t("¿Rechazar {{n}} propuestas?", { n: goes.length })}
      warning={batch.verb === "approve"
        ? <>{t("Entran en el grafo dentro de unos segundos, con la opción de deshacerlo mientras tanto.")}{stays.length === 1 ? " " + t("1 no se aprueba así (una corrección, un secreto por revisar, algo que el brain ya sabe, tiene muy parecido o aún no ha comprobado): se queda seleccionada para decidirla aparte.")
          : stays.length ? " " + t("{{k}} no se aprueban así (correcciones, secretos por revisar, lo que el brain ya sabe, tiene muy parecido o aún no ha comprobado): se quedan seleccionadas para decidirlas una a una.", { k: stays.length }) : ""}</>
        : t("No entra nada en el grafo; se pueden reabrir después.")}
      subject={<Stack gap={6}>
        {goes.length > 3 && <Group><Btn kind="link" className="ms-hit" icon={showGoes ? "chevronDown" : "chevronRight"} aria-expanded={showGoes} aria-controls="ms-batch-goes"
          onClick={() => setShowGoes(!showGoes)}>{batch.verb === "approve" ? t("Ver cuáles se aprueban ({{n}})", { n: goes.length }) : t("Ver cuáles se rechazan ({{n}})", { n: goes.length })}</Btn></Group>}
        {goes.length > 0 && <ul className="ms-batch-list" id="ms-batch-goes" hidden={goes.length > 3 && !showGoes} aria-label={batch.verb === "approve" ? t("Se aprueban") : t("Se rechazan")}>
          {goes.map((p) => <li key={p.id}><span className="ms-data">#{p.id}</span> {p.purged_at ? t("(texto purgado)") : p.name}</li>)}</ul>}
        {stays.length > 0 && <><Text size="xs" c="dimmed">{t("Se quedan para decidirlas aparte:")}</Text>
          <ul className="ms-batch-list" data-muted="">{stays.map((p) => <li key={p.id}><span className="ms-data">#{p.id}</span> {p.purged_at ? t("(texto purgado)") : p.name}</li>)}</ul></>}
      </Stack>}
      action={batch.verb === "approve" ? t("Aprobar {{n}}", { n: goes.length }) : t("Rechazar {{n}}", { n: goes.length })}
      disabled={goes.length === 0}
      onConfirm={() => bulk.mutateAsync({ verb: batch.verb, ids: batch.items.map((p) => p.id) })}>
      <TextArea size="xs" autosize minRows={2} label={t("Nota para todas (opcional)")} value={bulkNote} onChange={(e) => setBulkNote(e.currentTarget.value)} />
    </ConfirmDialog>
  </>);
}

/** «My proposals»: the form to propose (folds away) and what one has sent, in every state. */
function MineTab({ ops, isCurator }: { ops: Ops; isCurator: boolean }) {
  const { t } = useTranslation();
  const [formOpen, setFormOpen] = useState(true);
  const [name, setName] = useState(""); const [body, setBody] = useState(""); const [conf, setConf] = useState<number | string>("");
  const [sentProp, setSentProp] = useState<Prop | null>(null);  // the last one sent, so its author sees what happened to it
  const submit = useMutation({ mutationFn: () => send<Prop>("POST", ops.base, { name, body, confidence: conf === "" ? undefined : Number(conf) }),
    onMutate: () => setSentProp(null),
    onSuccess: (p) => { setName(""); setBody(""); setConf(""); setSentProp(p); ops.refresh(); } });
  return (<>
    <Group justify="space-between">
      <Text component="h2" fw={600} size="md" m={0}>{t("Nueva propuesta")}</Text>
      <Btn size="row" kind="ghost" onClick={() => setFormOpen((o) => !o)}>{formOpen ? t("Ocultar el formulario") : t("Mostrar el formulario")}</Btn>
    </Group>
    {formOpen && <Panel withBorder p="sm"><Stack gap="xs">
      <TextField size="xs" label={t("Título")} placeholder={t("De qué trata, en pocas palabras")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextArea size="xs" autosize minRows={3} label={t("Contenido")} placeholder={t("Qué ha pasado o qué hay que recordar, con fecha y nombres exactos.")} value={body} onChange={(e) => setBody(e.currentTarget.value)} />
      {isCurator && <Text size="xs" c="dimmed">{t("Eres curador: lo que crees aquí se aprueba sin pasar por la cola y entra en el grafo. Si el detector marca un secreto, espera a un curador como cualquier otra.")}</Text>}
      <Group align="flex-end">
        <NumberField size="xs" label={t("Confianza (0–1, opcional)")} min={0} max={1} step={0.1} decimalScale={2} value={conf} onChange={setConf} w={170} hideControls />
        <Btn kind="primary" disabled={!name || !body} loading={submit.isPending} onClick={() => submit.mutate()} icon="plus">{isCurator ? t("Crear y aprobar") : t("Proponer")}</Btn>
      </Group>
      <MutationError error={submit.error} />
      {sentProp && <Notice tone="success">{sentProp.status === "pending"
        ? t("Propuesta #{{id}} enviada: queda pendiente de un curador.", { id: sentProp.id })
        : t("Propuesta #{{id}} creada y aprobada.", { id: sentProp.id })}</Notice>}
      {sentProp && <SecretsNotice found={sentProp.secrets} />}
    </Stack></Panel>}
    <HistoryTable ops={ops} mine={true} statuses={["pending", "approved", "ingested", "rejected", "failed"]} first={{ value: "all", label: t("Todas"), countKey: "all" }} />
  </>);
}

export default function Proposals({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isCurator = ["curator", "admin", "owner"].includes(role);
  const [sp] = useSearchParams();   // ?estado=…&tipo=…: the links of «Needs your attention» and of the summary open the right view, filtered
  const estado = sp.get("estado");
  // without ?tab=, ?estado=decided (an older link) opens the decided ones; choosing a tab drops it
  const [chosen, setTab] = useTabParam("revisar", "tab", ["estado"]);
  const tab = sp.get("tab") ? chosen : estado && estado !== "pending" ? "decididas" : "revisar";
  const base = `brains/${graph}/proposals`;
  const ai = useQuery({ queryKey: ["ai-status"], refetchInterval: 60000, queryFn: () => get<Record<string, { configured: boolean }>>("ai-status") });
  const pendingCount = useQuery({ queryKey: ["proposals", graph, "counts", "all", false], enabled: isCurator, refetchInterval: 15000, queryFn: () => get<Counts>(`${base}/counts`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["proposals", graph] }); qc.invalidateQueries({ queryKey: ["proposal", graph] }); };
  const [note, setNote] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [last, setLast] = useState<Decision | null>(null);
  const [docked, setDocked] = useState(false);
  const [noteKey, setNoteKey] = useState(0);
  const [explain, setExplain] = useState(false);
  const undo = useMutation({ mutationFn: (ids: number[]) => Promise.all(ids.map((id) => send("POST", `${base}/${id}/undo`))),
    onSuccess: (_, ids) => { setLast((prev) => ({ id: ids[0], ids: ids.length > 1 ? ids : undefined, verb: "undone", until: null, name: ids.length === 1 && prev?.id === ids[0] ? prev.name : undefined })); refresh(); } });
  const review = useMutation({ mutationFn: (a: { id: number; verb: Verb; note?: string }) => send<Prop & { undo_seconds?: number }>("POST", `${base}/${a.id}/${a.verb}`, { note: a.note ?? note }),
    onMutate: () => undo.reset(),
    onSuccess: (r, a) => { setNote(""); setLast({ id: a.id, verb: a.verb === "reject" ? "reject" : "approve", until: r.undo_seconds ? Date.now() + r.undo_seconds * 1000 : null, name: r.purged_at ? undefined : r.name }); refresh(); } });
  const reactivate = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/reactivate`), onSuccess: refresh });
  const retry = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/ingest`), onSuccess: () => { setOpen(null); setTimeout(refresh, 8000); refresh(); } });
  const llm = !!ai.data?.llm.configured;
  const notice = (docked?: { openId: number | null }) => <DecisionNotice base={base} graph={graph} last={last} llm={llm} onUndo={(ids) => undo.mutate(ids)} undoing={undo.isPending}
    openId={docked?.openId} compact={!!docked}
    undoError={last && last.verb !== "undone" ? undo.error : null} onOpen={(id) => { setOpen(id); setNote(""); }} onClose={() => { setLast(null); undo.reset(); }} />;
  const ops: Ops = { base, graph, isCurator, llm, note, setNote, review, undo, reactivate, retry, setLast, refresh,
    openDetail: (id) => { setOpen(id); setNote(""); }, last, notice, setDocked, noteKey, openNote: () => setNoteKey((k) => k + 1), explain, setExplain,
    undoLast: () => { if (last && undoable(last) && !undo.isPending) undo.mutate(last.ids ?? [last.id]); } };
  if (role === "reader") return <Page><PageHeader title={t("Propuestas")} description={<>{t("Con rol de lector no puedes proponer ni ver propuestas. Pide rol de colaborador a un administrador del brain.")}</>} /></Page>;
  return (
    <Page>
      <PageHeader title={t("Propuestas")} description={<>{t("Lo que envían colaboradores y agentes espera aquí a que un curador lo apruebe.")}</>} />
      {ai.data && !ai.data.llm.configured && <Notice tone="warn" title={t("Sin motor LLM configurado")}>{t("Las propuestas aprobadas no se ingieren al grafo y se quedan en «Aprobadas». Un administrador debe configurarlo en Administración → Proveedores IA.")}{" "}
        <Btn kind="link" component={Link} to="/admin?seccion=llm">{t("Ir a Modelo LLM")}</Btn></Notice>}
      {ai.data && ai.data.llm.configured && !ai.data.decider.configured && <Notice>{t("Sin decisor: las propuestas de colaboradores esperan siempre a un curador.")}</Notice>}
      <DecisionLive base={base} graph={graph} last={last} llm={llm} />
      {!docked && notice()}
      {isCurator
        ? <Tabs value={tab} onChange={(v) => setTab(v)} keepMounted={false} className="ms-tabs-fill">
            <Tabs.List>
              <Tabs.Tab value="revisar">{t("Por revisar")}{tab !== "revisar" && pendingCount.data ? ` (${pendingCount.data.pending ?? 0})` : ""}</Tabs.Tab>
              <Tabs.Tab value="categorias">{t("Por categorías")}</Tabs.Tab>
              <Tabs.Tab value="decididas">{t("Decididas")}</Tabs.Tab>
              <Tabs.Tab value="mias">{t("Mis propuestas")}</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="revisar" pt="sm" className="ms-tabpanel-col">
              <ReviewTab ops={ops} initialKind={sp.get("tipo") ?? undefined} onDecided={() => setTab("decididas")} />
            </Tabs.Panel>
            <Tabs.Panel value="categorias" pt="sm" className="ms-tabpanel-col"><ProposalCategories graph={graph} isAdmin={["admin", "owner"].includes(role)} /></Tabs.Panel>
            <Tabs.Panel value="decididas" pt="sm" className="ms-tabpanel-col">
              <HistoryTable ops={ops} mine={false} statuses={["approved", "ingested", "rejected", "failed"]} initialKind={sp.get("tipo") ?? undefined}
                first={{ value: "decided", label: t("Todas"), countKey: "decided" }} />
            </Tabs.Panel>
            <Tabs.Panel value="mias" pt="sm" className="ms-tabpanel-col"><MineTab ops={ops} isCurator={isCurator} /></Tabs.Panel>
          </Tabs>
        : <MineTab ops={ops} isCurator={isCurator} />}
      <ProposalModal open={open} onClose={() => setOpen(null)} ops={ops} />
    </Page>
  );
}
