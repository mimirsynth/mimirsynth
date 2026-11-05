import { T, locale } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { Btn, ClearFilters, ConfirmDialog, Icon, ColHead, CopyBtn, DataTable, EmptyState, FillArea, InboxLayout, Modal, MutationError, Notice, NumberField, Page, PageHeader, Pager, Panel,
  Pill, QueueList, RowOpen, Segments, Steps, Step, Tabs, TextArea, TextField, Tone, rowOpen, useServerTableView, useShortcuts, useTabParam, type QueueItem } from "../ui";
import { SecretsNotice, type SecretFinding } from "./Secrets";
import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fmt, get, send } from "../api";

type Prop = { id: number; name: string; body: string; source: string; source_description: string; confidence: number | null; status: string; author: string;
  created_at: string; reviewed_at: string | null; ingest_report?: { entities: number; edges: number; ontology: boolean; off_ontology: string[]; untyped_entities: number; aliased_edges?: number; auto_merged?: string[]; merge_ambiguous?: string[] } | null; review_note: string; review_kind: string; decision: any; ingest_error: string; episode_uuid: string | null; ingested_at: string | null; purged_at?: string | null; secrets?: SecretFinding[];
  kind?: string; correction?: Correction | null; secrets_notice?: string };
/** Correction of a fact: the fact as it was when proposed, the reason and, once applied, when (and whether it was undone). */
type Correction = { fact_uuid: string; fact: { fact: string; source: string; target: string; name: string; valid_at: string | null }; reason: string;
  invalid_at: string; applied_at?: string; reverted_at?: string };
const TONE: Record<string, Tone> = { pending: "warn", approved: "success", rejected: "neutral", ingested: "alt", failed: "danger" };
const LABEL: Record<string, string> = { pending: "pendiente", approved: "aprobada", rejected: "rechazada", ingested: "ingerida", failed: "fallida" };
const SOURCE: Record<string, string> = { text: T("texto"), message: T("conversación"), json: T("JSON") };
const LOW_CONFIDENCE = 0.6;  // the same threshold as the review queue's risk order in the API
const flagged = (p: Prop) => !!p.secrets?.some((f) => f.action === "flagged");

/** What a proposal does: adds knowledge or invalidates a fact. A correction is the delicate one, so it differs by icon, text and a filled look, not only by colour. */
function KindPill({ kind }: { kind?: string }) {
  const { t } = useTranslation();
  return kind === "correction"
    ? <Pill size="xs" tone="warn" strong title={t("Invalida un hecho del grafo")}><Group gap={4} wrap="nowrap"><Icon name="undo" size={12} />{t("Corrige")}</Group></Pill>
    : <Pill size="xs" tone="neutral" title={t("Añade conocimiento al grafo")}><Group gap={4} wrap="nowrap"><Icon name="plus" size={12} />{t("Añade")}</Group></Pill>;
}

/** Marker in the list for a proposal the secret detector touched: masked (already safe) or flagged (a person must look). Text and icon, not only colour. */
function SecretsPill({ found }: { found?: SecretFinding[] }) {
  const { t } = useTranslation();
  if (!found?.length) return null;
  const isFlagged = found.some((f) => f.action === "flagged");
  return <Pill size="xs" tone={isFlagged ? "warn" : "neutral"} title={[...new Set(found.map((f) => t(f.label)))].join(", ")}>
    <Group gap={4} wrap="nowrap"><Icon name="lock" size={12} />{isFlagged ? t("Secreto por revisar") : t("Secreto enmascarado")}</Group></Pill>;
}

/** How long a proposal has been waiting, in the interface language («hace 3 h»). */
function waited(iso: string): string {
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto", style: "short" });
  for (const [unit, secs] of [["day", 86400], ["hour", 3600], ["minute", 60]] as const) if (Math.abs(s) >= secs) return rtf.format(Math.round(s / secs), unit);
  return rtf.format(0, "minute");
}

type PropList = { total: number; limit: number; offset: number; authors: { id: number; name: string }[]; items: Prop[] };
type Counts = Record<string, number> & { kinds?: Record<string, number>; corrections_pending?: number };
const PLURAL: Record<string, string> = { pending: T("Pendientes"), approved: T("Aprobadas"), rejected: T("Rechazadas"), failed: T("Fallidas"), ingested: T("Ingeridas") };
type View = ReturnType<typeof useProposalsView>;
const useProposalsView = () => useServerTableView({ q: "", author: "" }, { debounced: ["q"], firstDir: { name: "asc", author: "asc" } });

/** Estado, filtros, orden y página se resuelven en el servidor (#88): con muchas propuestas se llega a todas y los filtros abarcan el conjunto entero.
 *  Devuelve hijos directos de la página: así solo la tabla (`FillArea`) se desplaza. `statuses` are the state segments it offers, the first one being «all of them». */
function ProposalsTable({ data, view, status, onStatus, statuses, kind, onKind, counts, onOpen }: { data?: PropList; view: View; status: string; onStatus: (s: string) => void;
  statuses: { value: string; label: string; count: number }[]; kind: string; onKind: (k: string) => void; counts: Counts; onOpen: (id: number) => void }) {
  const { t } = useTranslation();
  const { f, setFilter, sortProps, page, setPage, active, clear } = view;
  const rows = data?.items ?? [];
  return (<>
    <Segments label={t("Estado")} value={status} onChange={onStatus} data={statuses} />
    <Segments label={t("Tipo")} value={kind} onChange={onKind}
      data={[{ value: "all", label: t("Todas") }, { value: "memory", label: t("Añaden"), count: counts.kinds?.memory ?? 0 }, { value: "correction", label: t("Corrigen"), count: counts.kinds?.correction ?? 0 }]} />
    <ClearFilters active={active} onClear={clear} />
    <FillArea><DataTable fz="sm">
      <DataTable.Thead><DataTable.Tr>
        <ColHead sort={sortProps("id")}>#</ColHead>
        <ColHead>{t("Tipo")}</ColHead>
        <ColHead sort={sortProps("name")} filter={{ kind: "text", value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Título…") }}>{t("Título")}</ColHead>
        <ColHead sort={sortProps("author")} filter={{ kind: "select", value: f.author, onChange: (v) => setFilter({ author: v }), allLabel: t("Todos los autores"), options: (data?.authors ?? []).map((a) => ({ value: String(a.id), label: a.name })) }}>{t("Autor")}</ColHead>
        <ColHead sort={sortProps("conf")}>{t("Confianza")}</ColHead>
        <ColHead>{t("Estado")}</ColHead>
        <ColHead sort={sortProps("at")}>{t("Enviada")}</ColHead>
      </DataTable.Tr></DataTable.Thead>
      <DataTable.Tbody>
        {rows.map((p) => (
          <DataTable.Tr key={p.id} {...rowOpen(() => onOpen(p.id))}>
            <DataTable.Td className="ms-data">#{p.id}</DataTable.Td><DataTable.Td><KindPill kind={p.kind} /></DataTable.Td>
            <DataTable.Td><Group gap="xs" wrap="nowrap"><RowOpen onOpen={() => onOpen(p.id)}>{p.purged_at ? t("(texto purgado)") : p.name}</RowOpen><SecretsPill found={p.secrets} /></Group></DataTable.Td><DataTable.Td>{p.author}</DataTable.Td><DataTable.Td>{p.confidence ?? "—"}</DataTable.Td>
            <DataTable.Td><Pill size="sm" tone={TONE[p.status]}>{t(LABEL[p.status] ?? p.status)}</Pill></DataTable.Td><DataTable.Td>{fmt(p.created_at)}</DataTable.Td>
          </DataTable.Tr>))}
        {data && rows.length === 0 && <DataTable.Tr><DataTable.Td colSpan={7}><EmptyState>{active ? t("Ninguna propuesta coincide con los filtros.") : t("No hay propuestas en este estado.")}</EmptyState></DataTable.Td></DataTable.Tr>}
      </DataTable.Tbody>
    </DataTable></FillArea>
    <Pager total={data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />
  </>);
}

/** The last decision taken here, said above the work, in a live region: what happened, what happens next, and the way back.
 *  An approval waits `undo_seconds` before ingestion; after that a single one is followed until it is ingested or failed. `ids` when it was
 *  a decision on several at once (`skipped`: how many of the selected ones were left to decide one at a time). */
type Decision = { id: number; ids?: number[]; skipped?: number; verb: "approve" | "reject" | "undone"; until: number | null };
function DecisionNotice({ base, graph, last, llm, onUndo, undoing, undoError, onOpen, onClose }: { base: string; graph: string; last: Decision | null; llm: boolean;
  onUndo: (ids: number[]) => void; undoing: boolean; undoError: unknown; onOpen: (id: number) => void; onClose: () => void }) {
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
  const id = last.id;
  const ids = last.ids ?? [id];
  const n = ids.length;
  const s = last.until ? Math.max(1, Math.ceil((last.until - now) / 1000)) : 0;
  const undo = <Btn kind="link" loading={undoing} onClick={() => onUndo(ids)}>{t("Deshacer")}</Btn>;
  const view = <Btn kind="link" onClick={() => onOpen(id)}>{t("Ver la propuesta")}</Btn>;
  const close = <Btn kind="link" onClick={onClose}>{t("Cerrar aviso")}</Btn>;
  let tone: "success" | "danger" | "info" = "success";
  let text: string;
  let actions = <>{close}</>;
  if (many) {
    if (n === 0) { tone = "info"; text = t("No se ha decidido ninguna: las seleccionadas se deciden una a una."); }
    else if (last.verb === "undone") { tone = "info"; text = t("{{n}} propuestas otra vez pendientes.", { n }); }
    else if (last.verb === "reject") { text = t("{{n}} propuestas rechazadas: no entra nada en el grafo.", { n }); actions = <>{undo} · {close}</>; }
    else if (waiting) { text = t("{{n}} propuestas aprobadas: entran en el grafo dentro de {{s}} s.", { n, s }); actions = <>{undo} · {close}</>; }
    else text = last.until ? t("{{n}} propuestas aprobadas: entrando en el grafo. El resultado de cada una está en «Decididas».", { n }) : t("{{n}} propuestas aprobadas.", { n });
    if (last.skipped === 1) text += " " + t("1 se queda para decidirla aparte (una corrección, un secreto por revisar o ya decidida).");
    else if (last.skipped) text += " " + t("{{k}} se quedan para decidirlas una a una (correcciones, secretos por revisar o ya decididas).", { k: last.skipped });
  } else if (last.verb === "undone") {
    tone = "info"; text = t("Propuesta #{{id}} otra vez pendiente.", { id }); actions = <>{view} · {close}</>;
  } else if (last.verb === "reject") {
    text = t("Propuesta #{{id}} rechazada: no entra nada en el grafo.", { id }); actions = <>{undo} · {close}</>;
  } else if (!last.until) {
    text = llm ? t("Propuesta #{{id}} aprobada.", { id }) : t("Propuesta #{{id}} aprobada: se queda en «Aprobadas» hasta que haya un motor de extracción.", { id });
    actions = <>{undo} · {close}</>;
  } else if (waiting) {
    text = t("Propuesta #{{id}} aprobada: entra en el grafo dentro de {{s}} s.", { id, s });
    actions = <>{undo} · {close}</>;
  } else if (p.data?.status === "ingested") {
    const r = p.data.ingest_report;
    const ents = r ? (r.entities === 1 ? t("1 entidad") : t("{{n}} entidades", { n: r.entities })) : "";
    const facts = r ? (r.edges === 1 ? t("1 hecho") : t("{{n}} hechos", { n: r.edges })) : "";
    text = r ? t("Propuesta #{{id}} en el grafo: {{ents}} y {{facts}}.", { id, ents, facts }) : t("Propuesta #{{id}} en el grafo.", { id });
    if (r && r.edges === 0) text += " " + t("No se extrajo ningún hecho: revisa el texto de la propuesta.");
    actions = <>{view} · {close}</>;
  } else if (p.data?.status === "failed") {
    tone = "danger"; text = t("Propuesta #{{id}}: falló la ingesta. {{error}}", { id, error: p.data.ingest_error }); actions = <>{view} · {close}</>;
  } else {
    text = t("Propuesta #{{id}} aprobada: entrando en el grafo…", { id });
  }
  return (<Notice tone={tone}><Stack gap={4}><Text size="sm">{text}</Text><Text size="sm">{actions}</Text><MutationError error={undoError} /></Stack></Notice>);
}

/** What to look at before approving a correction: the affected fact as it was, the reason and the text that replaces it. */
function CorrectionDetail({ c, replacement }: { c: Correction; replacement: string }) {
  const { t } = useTranslation();
  return (<Stack gap="xs">
    <Panel withBorder p="sm"><Stack gap={4}>
      <Text size="xs" fw={600}>{t("Hecho que se invalida")}</Text>
      <Text className="ms-prose">{c.fact.fact}</Text>
      <Text size="xs" c="dimmed">{c.fact.source} → {c.fact.name} → {c.fact.target}{c.fact.valid_at ? ` · ${t("vigente desde {{date}}", { date: c.fact.valid_at.slice(0, 10) })}` : ""} · <code>{c.fact_uuid}</code></Text>
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

/** A proposal as a curator reads it: what it says (or the correction it asks for), its secrets and its life so far. */
function ProposalBody({ d, context }: { d: Prop; context?: ReactNode }) {
  const { t } = useTranslation();
  return (<Stack gap="sm">
    <Group gap="xs"><KindPill kind={d.kind} /><Pill tone={TONE[d.status]}>{t(LABEL[d.status] ?? d.status)}</Pill>
      <Text size="xs" c="dimmed">{t("Confianza declarada por el autor:")} {d.confidence ?? t("no indicada")}</Text></Group>
    {d.purged_at ? <Notice tone="info">{t("El texto de esta propuesta rechazada se purgó el {{d}} por el plazo de retención del brain. Quedan su estado, sus autores y sus fechas.", { d: fmt(d.purged_at) })}</Notice>
      : d.correction ? <CorrectionDetail c={d.correction} replacement={d.body} /> : <Panel withBorder p="sm"><Text className="ms-prose">{d.body}</Text></Panel>}
    <SecretsNotice found={d.secrets} />
    {context}
    <Steps>
      <Step title={t("Enviada")} tone="success"><Text size="xs" c="dimmed">{d.author} · {fmt(d.created_at)}</Text>
        <Text size="xs" c="dimmed">{t("Procedencia:")} {d.source_description || t("no indicada")} · {t(SOURCE[d.source] ?? d.source)}</Text></Step>
      <Step title={t("Revisión")} tone={d.status === "rejected" ? "danger" : d.status === "pending" ? "warn" : "success"}>
        {d.review_kind === "direct" && <Text size="xs" c="dimmed">{t("Aprobada al enviar (el autor es curador o superior) ·")} {fmt(d.reviewed_at)}</Text>}
        {d.review_kind === "webhook" && <Text size="xs" c="dimmed">{t("Aprobada al llegar por un webhook de confianza ·")} {fmt(d.reviewed_at)}</Text>}
        {d.review_kind === "human" && <Text size="xs" c="dimmed">{d.status === "rejected" ? t("Rechazada") : t("Aprobada")} {t("por un curador ·")} {fmt(d.reviewed_at)}{d.review_note ? ` · «${d.review_note}»` : ""}</Text>}
        {d.decision && !d.decision.error && <Stack gap={2}>
          <Text size="xs" c="dimmed">{t("Decisor «{{engine}}» ({{model}}), umbral {{threshold}}:", { engine: d.decision.engine, model: d.decision.model, threshold: d.decision.threshold })}</Text>
          <Text size="xs" c="dimmed">{t("· ¿Es factual? {{answer}} (confianza {{prob}})", { answer: d.decision.factual.letter === "A" ? t("sí") : t("no"), prob: d.decision.factual.prob })}</Text>
          <Text size="xs" c="dimmed">{t("· Acción: {{action}} (confianza {{prob}})", { action: [t("aprobar"), t("revisar"), t("rechazar")][d.decision.action.index], prob: d.decision.action.prob })}</Text>
          <Text size="xs" fw={600}>{d.decision.verdict === "approve" ? t("Aprobada automáticamente") : t("Derivada a un curador")}: {d.decision.note}</Text></Stack>}
        {d.decision?.error && <Notice tone="warn">{t("Decisor «{{engine}}» no disponible: {{error}}", { engine: d.decision.engine, error: d.decision.error })}</Notice>}
        {!d.review_kind && !d.decision && d.status === "pending" && <Text size="xs" c="dimmed">{t("Pendiente de un curador.")}</Text>}
        {!d.review_kind && !d.decision && d.status !== "pending" && d.review_note && <Text size="xs" c="dimmed">{d.review_note}</Text>}
      </Step>
      {d.correction && <Step title={t("Hecho invalidado")} tone={d.correction.reverted_at ? "neutral" : d.correction.applied_at ? "success" : "neutral"}>
        {d.correction.applied_at ? <Text size="xs" c="dimmed">{t("Invalidado con fecha {{date}} · aplicado {{at}}", { date: d.correction.invalid_at.slice(0, 10), at: fmt(d.correction.applied_at) })}</Text>
          : <Text size="xs" c="dimmed">{t("Se invalidará al aprobarla, con fecha {{date}}.", { date: d.correction.invalid_at.slice(0, 10) })}</Text>}
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
        {(d.status === "pending" || d.status === "rejected") && <Text size="xs" c="dimmed">{t("No aplica.")}</Text>}
      </Step>}
    </Steps>
  </Stack>);
}

/** Everything a screen of this page needs to decide: shared so the queue, the history and one's own proposals act the same way. */
type Ops = {
  base: string; graph: string; isCurator: boolean; llm: boolean; note: string; setNote: (v: string) => void;
  review: UseMutationResult<Prop & { undo_seconds?: number }, Error, { id: number; verb: "approve" | "reject" }>;
  undo: UseMutationResult<unknown, Error, number[]>; reactivate: UseMutationResult<unknown, Error, number>; retry: UseMutationResult<unknown, Error, number>;
  setLast: (d: Decision) => void; refresh: () => void; openDetail: (id: number) => void;
};

/** What the brain already knows close to a proposal (a recall of its text, facts only), so the curator checks it against something: a
 *  duplicate, a contradiction, or nothing at all, which makes it new knowledge. Only for pending proposals that add knowledge. */
type RelatedFact = { uuid: string; fact: string; name: string; source: string; target: string; source_uuid?: string | null; target_uuid?: string | null;
  valid_at: string | null; invalid_at: string | null; score?: number | null };
function RelatedFacts({ d, ops }: { d: Prop; ops: Ops }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["proposal", ops.graph, d.id, "related"], staleTime: 60_000, queryFn: () => get<{ facts: RelatedFact[] }>(`${ops.base}/${d.id}/related`) });
  return (<Panel withBorder p="sm" className="ms-related"><Stack gap={6}>
    <Text size="xs" fw={600}>{t("Lo que el brain ya sabe")}</Text>
    <MutationError error={q.error} />
    {!q.data && !q.error && <EmptyState>{t("Buscando lo relacionado…")}</EmptyState>}
    {q.data && q.data.facts.length === 0 && <Text size="xs" c="dimmed">{t("Nada parecido en el brain: sería conocimiento nuevo.")}</Text>}
    {q.data?.facts.map((f) => (<Stack key={f.uuid} gap={0}>
      <Text size="sm" className={f.invalid_at ? "ms-text-danger" : undefined}>{f.fact}</Text>
      <Text size="xs" c="dimmed">
        {f.source_uuid ? <Link to={`/entidad/${f.source_uuid}`}>{f.source}</Link> : f.source} → {f.name} → {f.target_uuid ? <Link to={`/entidad/${f.target_uuid}`}>{f.target}</Link> : f.target}
        {f.valid_at ? ` · ${t("vigente desde {{date}}", { date: f.valid_at.slice(0, 10) })}` : ""}{f.invalid_at ? ` · ${t("invalidado el {{date}}", { date: f.invalid_at.slice(0, 10) })}` : ""}
      </Text>
    </Stack>))}
    {q.data && q.data.facts.length > 0 && <Text size="xs" c="dimmed">{t("Comprueba si la propuesta repite o contradice alguno de estos hechos.")}</Text>}
  </Stack></Panel>);
}

/** The decision on a pending proposal: a note, what each button will do, and Reject / Approve (each with its own progress). */
function DecisionBlock({ d, ops, onDecided }: { d: Prop; ops: Ops; onDecided?: () => void }) {
  const { t } = useTranslation();
  const { review } = ops;
  const decide = (verb: "approve" | "reject") => review.mutate({ id: d.id, verb }, { onSuccess: () => onDecided?.() });
  return (<Stack gap="xs">
    <TextArea size="xs" autosize minRows={1} maxRows={4} label={t("Nota (opcional)")} value={ops.note} onChange={(e) => ops.setNote(e.currentTarget.value)} />
    <Stack gap={2}>
      <Text size="xs" c="dimmed">{d.correction
        ? t("Al aprobar, el hecho se invalida con fecha {{date}}; se puede reactivar después.", { date: d.correction.invalid_at.slice(0, 10) })
        : ops.llm
          ? t("Al aprobar, el texto entra en el brain como un episodio y el modelo extrae de él entidades y hechos. Tendrás unos segundos para deshacerlo.")
          : t("Al aprobar, se queda en «Aprobadas» hasta que haya un motor de extracción.")}</Text>
      <Text size="xs" c="dimmed">{t("Al rechazar, no entra nada en el grafo y se puede reabrir después.")}</Text>
    </Stack>
    <MutationError error={review.error} />
    <Group justify="flex-end">
      <Btn kind="danger" loading={review.isPending && review.variables?.verb === "reject"} disabled={review.isPending && review.variables?.verb !== "reject"}
        onClick={() => decide("reject")} icon="close">{t("Rechazar")}</Btn>
      <Btn kind="primary" loading={review.isPending && review.variables?.verb === "approve"} disabled={review.isPending && review.variables?.verb !== "approve"}
        onClick={() => decide("approve")} icon="check">{t("Aprobar")}</Btn>
    </Group>
  </Stack>);
}

/** The actions on a decided proposal: retry or start its ingestion, reopen or undo the approval, reactivate a corrected fact. */
function AfterActions({ d, ops }: { d: Prop; ops: Ops }) {
  const { t } = useTranslation();
  const { retry, undo, reactivate } = ops;
  if (!ops.isCurator) return null;
  return (<>
    {(d.status === "failed" || d.status === "approved") && <Group justify="flex-end">
      <MutationError error={retry.error} />
      <Btn kind="primary" loading={retry.isPending} onClick={() => retry.mutate(d.id)}>{d.status === "failed" ? t("Reintentar ingesta") : t("Ingerir ahora")}</Btn></Group>}
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
        <ProposalBody d={d} context={ops.isCurator && d.status === "pending" && !d.correction ? <RelatedFacts d={d} ops={ops} /> : undefined} />
        <AfterActions d={d} ops={ops} />
        {ops.isCurator && d.status === "pending" && <DecisionBlock d={d} ops={ops} onDecided={onClose} />}
      </Stack>}
    </Modal>
  );
}

/** A server-paged table of proposals with its own filters: the review history («Decididas») or one's own proposals (`mine`). */
function HistoryTable({ ops, mine, statuses, first, initialStatus, initialKind }: { ops: Ops; mine: boolean; statuses: string[]; first: { value: string; label: string; countKey: string };
  initialStatus?: string; initialKind?: string }) {
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
  const counts = cnt.data ?? {};
  return (<>
    <MutationError error={list.error} />
    <ProposalsTable data={list.data} view={view} status={status} onStatus={setStatus} kind={kind} onKind={setKind} counts={counts} onOpen={ops.openDetail}
      statuses={[{ value: first.value, label: first.label, count: counts[first.countKey] ?? 0 }, ...statuses.map((k) => ({ value: k, label: t(PLURAL[k]), count: counts[k] ?? 0 }))]} />
  </>);
}

/** «To review»: the pending queue, riskiest and oldest first, beside the open proposal; J/K move, A/R decide and the next one opens;
 *  several can be checked and decided at once (approving skips corrections and secrets to review, which go one at a time). */
function ReviewTab({ ops, initialKind, decidedFirst }: { ops: Ops; initialKind?: string; decidedFirst: boolean }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(decidedFirst ? "decided" : "pending");
  const [kind, setKind] = useState(initialKind ?? "all");
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const cnt = useQuery({ queryKey: ["proposals", ops.graph, "counts", kind, false], refetchInterval: 15000, queryFn: () => get<Counts>(`${ops.base}/counts`, { kind: kind === "all" ? undefined : kind }) });
  const queue = useQuery({ queryKey: ["proposals", ops.graph, "queue", kind, offset], enabled: mode === "pending", placeholderData: keepPreviousData, refetchInterval: 15000,
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
  const detail = useQuery({ queryKey: ["proposal", ops.graph, active], enabled: active !== null, queryFn: () => get<Prop>(`${ops.base}/${active}`) });
  const d = detail.data && detail.data.id === active ? detail.data : undefined;
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);
  const [bulkNote, setBulkNote] = useState("");
  const selected = items.filter((p) => checked.has(p.id));
  const oneByOne = selected.filter((p) => p.kind === "correction" || flagged(p)).length;
  const bulk = useMutation({ mutationFn: (verb: "approve" | "reject") => send<{ done: number[]; skipped: { id: number; reason: string }[]; undo_seconds?: number }>("POST", `${ops.base}/bulk`,
      { verb, ids: selected.map((p) => p.id), note: bulkNote }),
    onSuccess: (r, verb) => {
      ops.setLast({ id: r.done[0] ?? 0, ids: r.done, skipped: r.skipped.length, verb, until: r.undo_seconds ? Date.now() + r.undo_seconds * 1000 : null });
      setChecked(new Set(r.skipped.map((s) => s.id)));  // what was left out stays selected, to decide one at a time
      setBulkNote(""); ops.refresh();
    } });
  const open = (id: number) => { setActive(id); setShowDetail(true); ops.setNote(""); };
  const move = (step: number) => { const i = items.findIndex((p) => p.id === active); const next = items[i + step]; if (next) open(next.id); };
  const advance = (id: number) => {  // after a decision the next one opens, so the curator never goes back to the list
    const i = items.findIndex((p) => p.id === id);
    const next = items[i + 1] ?? items[i - 1];
    if (next) { setActive(next.id); ops.setNote(""); } else setShowDetail(false);
  };
  const decide = (verb: "approve" | "reject") => {
    if (!d || d.status !== "pending" || ops.review.isPending) return;
    ops.review.mutate({ id: d.id, verb }, { onSuccess: () => advance(d.id) });
  };
  const toggle = (id: number | null, on?: boolean) => {
    if (id === null) return;
    setChecked((c) => { const n = new Set(c); (on ?? !n.has(id)) ? n.add(id) : n.delete(id); return n; });
  };
  useShortcuts({ j: () => move(1), k: () => move(-1), a: () => decide("approve"), r: () => decide("reject"), x: () => toggle(active) }, mode === "pending" && confirm === null);
  const counts = cnt.data ?? {};
  const pendingFixes = counts.corrections_pending ?? 0;
  const queueItems: QueueItem[] = items.map((p) => ({
    id: p.id, title: <>{p.purged_at ? t("(texto purgado)") : p.name}</>, preview: p.correction ? p.correction.reason : p.body,
    tags: <>{p.kind === "correction" && <KindPill kind={p.kind} />}<SecretsPill found={p.secrets} />
      {p.confidence !== null && p.confidence < LOW_CONFIDENCE && <Pill size="xs" tone="warn">{t("confianza {{c}}", { c: p.confidence })}</Pill>}
      {p.decision && !p.decision.error && <Pill size="xs" tone="alt" title={p.decision.note}>{t("el decisor dudó · {{p}}", { p: p.decision.action?.prob })}</Pill>}</>,
    meta: <><span>{p.author}</span><span className="ms-data" title={fmt(p.created_at)}>{waited(p.created_at)}</span></>,
  }));
  return (<>
    <Segments label={t("Mostrar")} value={mode} onChange={(m) => setMode(m)}
      data={[{ value: "pending", label: t("Pendientes"), count: counts.pending ?? 0 }, { value: "decided", label: t("Decididas"), count: counts.decided ?? 0 }]} />
    {mode === "decided" ? <HistoryTable ops={ops} mine={false} statuses={["approved", "ingested", "rejected", "failed"]} initialKind={initialKind}
        first={{ value: "decided", label: t("Todas las decididas"), countKey: "decided" }} /> : <>
      <Segments label={t("Tipo")} value={kind} onChange={(k) => { setKind(k); setOffset(0); }}
        data={[{ value: "all", label: t("Todas") }, { value: "memory", label: t("Añaden") }, { value: "correction", label: t("Corrigen"), count: pendingFixes }]} />
      {pendingFixes > 0 && kind !== "correction" && <Notice tone="warn" title={t("Correcciones pendientes: {{n}}", { n: pendingFixes })}>
        {t("Cada una invalida un hecho del grafo y solo la decide una persona.")}{" "}
        <Btn kind="link" onClick={() => { setKind("correction"); setOffset(0); }}>{t("Ver solo las correcciones pendientes")}</Btn></Notice>}
      <MutationError error={queue.error} />
      {queue.data && items.length === 0
        ? <EmptyState>{t("No queda nada por revisar.")}{" "}<Btn kind="link" onClick={() => setMode("decided")}>{t("Ver las decididas")}</Btn></EmptyState>
        : <InboxLayout showDetail={showDetail}
          list={<>
            <div className="ms-inbox-bar">
              {selected.length > 0 ? <>
                <Text size="sm" fw={600}>{t("{{n}} seleccionadas", { n: selected.length })}</Text>
                <Btn size="row" icon="check" onClick={() => setConfirm("approve")}>{t("Aprobar las seleccionadas")}</Btn>
                <Btn size="row" kind="danger" icon="close" onClick={() => setConfirm("reject")}>{t("Rechazar las seleccionadas")}</Btn>
                <Btn size="row" kind="ghost" onClick={() => setChecked(new Set())}>{t("Quitar la selección")}</Btn>
              </> : <>
                <Text size="sm" c="dimmed">{t("Por riesgo y antigüedad")}</Text>
                <Btn size="row" kind="ghost" onClick={() => setChecked(new Set(items.map((p) => p.id)))}>{t("Seleccionar todas")}</Btn>
              </>}
            </div>
            <div className="ms-inbox-scroll">
              <QueueList items={queueItems} activeId={active} onActivate={open} checked={checked} onCheck={(id, on) => toggle(id, on)} label={t("Cola de propuestas pendientes")} />
            </div>
            <Pager total={queue.data?.total ?? 0} offset={offset} limit={limit} onChange={(p) => setOffset(p.offset)} />
          </>}
          detail={<>
            <div className="ms-inbox-body">
              <Btn size="row" kind="ghost" icon="undo" className="ms-inbox-back" onClick={() => setShowDetail(false)}>{t("Volver a la cola")}</Btn>
              <MutationError error={detail.error} />
              {d ? <><Text fw={600}>#{d.id} · {d.purged_at ? t("(texto purgado)") : d.name}</Text><ProposalBody d={d} context={d.status === "pending" && !d.correction ? <RelatedFacts d={d} ops={ops} /> : undefined} /></>
                : <EmptyState>{t("Cargando…")}</EmptyState>}
            </div>
            {d && d.status === "pending" && <div className="ms-inbox-actions">
              <DecisionBlock d={d} ops={ops} onDecided={() => advance(d.id)} />
              <Text className="ms-inbox-keys">{t("Atajos:")} <kbd>J</kbd>/<kbd>K</kbd> {t("moverse")} · <kbd>A</kbd> {t("aprobar")} · <kbd>R</kbd> {t("rechazar")} · <kbd>X</kbd> {t("seleccionar")}</Text>
            </div>}
          </>} />}
    </>}
    <ConfirmDialog opened={confirm !== null} onClose={() => setConfirm(null)} tone={confirm === "approve" ? "primary" : "danger"}
      title={confirm === "approve" ? t("¿Aprobar {{n}} propuestas?", { n: selected.length }) : t("¿Rechazar {{n}} propuestas?", { n: selected.length })}
      warning={confirm === "approve"
        ? <>{t("Entran en el grafo dentro de unos segundos, con la opción de deshacerlo mientras tanto.")}{oneByOne === 1 ? " " + t("1 no se aprueba así (una corrección o un secreto por revisar): se queda seleccionada para decidirla aparte.")
          : oneByOne ? " " + t("{{k}} no se aprueban así (correcciones o secretos por revisar): se quedan seleccionadas para decidirlas una a una.", { k: oneByOne }) : ""}</>
        : t("No entra nada en el grafo; se pueden reabrir después.")}
      action={confirm === "approve" ? t("Aprobar {{n}}", { n: selected.length - oneByOne }) : t("Rechazar {{n}}", { n: selected.length })}
      disabled={confirm === "approve" && selected.length - oneByOne === 0}
      onConfirm={() => bulk.mutateAsync(confirm!)}>
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
      <Text fw={600}>{t("Nueva propuesta")}</Text>
      <Btn size="row" kind="ghost" onClick={() => setFormOpen((o) => !o)}>{formOpen ? t("Ocultar el formulario") : t("Mostrar el formulario")}</Btn>
    </Group>
    {formOpen && <Panel withBorder p="sm"><Stack gap="xs">
      <TextField size="xs" label={t("Título")} placeholder={t("Migración de la base de datos a PostgreSQL 17")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <TextArea size="xs" autosize minRows={3} label={t("Contenido")} placeholder={t("Qué ha pasado o qué hay que recordar, con fecha y nombres exactos.")} value={body} onChange={(e) => setBody(e.currentTarget.value)} />
      <Group align="flex-end">
        <NumberField size="xs" label={t("Confianza (0–1, opcional)")} min={0} max={1} step={0.1} decimalScale={2} value={conf} onChange={setConf} w={170} />
        <Btn kind="primary" disabled={!name || !body} loading={submit.isPending} onClick={() => submit.mutate()} icon="plus">{isCurator ? t("Añadir") : t("Proponer")}</Btn>
      </Group>
      <MutationError error={submit.error} />
      {sentProp && <Notice tone="success">{sentProp.status === "pending"
        ? t("Propuesta #{{id}} enviada: queda pendiente de un curador.", { id: sentProp.id })
        : t("Propuesta #{{id}} añadida y aprobada.", { id: sentProp.id })}</Notice>}
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
  const [tab, setTab] = useTabParam("revisar");
  const base = `brains/${graph}/proposals`;
  const ai = useQuery({ queryKey: ["ai-status"], refetchInterval: 60000, queryFn: () => get<Record<string, { configured: boolean }>>("ai-status") });
  const pendingCount = useQuery({ queryKey: ["proposals", graph, "counts", "all", false], enabled: isCurator, refetchInterval: 15000, queryFn: () => get<Counts>(`${base}/counts`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["proposals", graph] }); qc.invalidateQueries({ queryKey: ["proposal", graph] }); };
  const [note, setNote] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [last, setLast] = useState<Decision | null>(null);
  const undo = useMutation({ mutationFn: (ids: number[]) => Promise.all(ids.map((id) => send("POST", `${base}/${id}/undo`))),
    onSuccess: (_, ids) => { setLast({ id: ids[0], ids: ids.length > 1 ? ids : undefined, verb: "undone", until: null }); refresh(); } });
  const review = useMutation({ mutationFn: (a: { id: number; verb: "approve" | "reject" }) => send<Prop & { undo_seconds?: number }>("POST", `${base}/${a.id}/${a.verb}`, { note }),
    onMutate: () => undo.reset(),
    onSuccess: (r, a) => { setNote(""); setLast({ id: a.id, verb: a.verb, until: r.undo_seconds ? Date.now() + r.undo_seconds * 1000 : null }); refresh(); } });
  const reactivate = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/reactivate`), onSuccess: refresh });
  const retry = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/ingest`), onSuccess: () => { setOpen(null); setTimeout(refresh, 8000); refresh(); } });
  const ops: Ops = { base, graph, isCurator, llm: !!ai.data?.llm.configured, note, setNote, review, undo, reactivate, retry, setLast, refresh,
    openDetail: (id) => { setOpen(id); setNote(""); } };
  if (role === "reader") return <Page><PageHeader title={t("Propuestas")} description={<>{t("Con rol de lector no puedes proponer ni ver propuestas. Pide rol de colaborador a un administrador del brain.")}</>} /></Page>;
  return (
    <Page>
      <PageHeader title={t("Propuestas")} description={<>{t("Cuarentena de aportaciones. Lo que envía un colaborador o un agente no entra al grafo hasta que un curador lo aprueba; las de un curador quedan aprobadas al enviarlas.")}</>} />
      {ai.data && !ai.data.llm.configured && <Notice tone="warn" title={t("Sin motor LLM configurado")}>{t("Las propuestas aprobadas no se ingieren al grafo y se quedan en «Aprobadas». Un administrador debe configurarlo en Administración → Proveedores IA.")}{" "}
        <Btn kind="link" component={Link} to="/admin?seccion=llm">{t("Ir a Modelo LLM")}</Btn></Notice>}
      {ai.data && ai.data.llm.configured && !ai.data.decider.configured && <Notice>{t("Sin decisor: las propuestas de colaboradores esperan siempre a un curador.")}</Notice>}
      <div role="status" aria-live="polite">
        <DecisionNotice base={base} graph={graph} last={last} llm={ops.llm} onUndo={(ids) => undo.mutate(ids)} undoing={undo.isPending}
          undoError={last && last.verb !== "undone" ? undo.error : null} onOpen={ops.openDetail} onClose={() => { setLast(null); undo.reset(); }} />
      </div>
      {isCurator
        ? <Tabs value={tab} onChange={(v) => setTab(v)} keepMounted={false} className="ms-tabs-fill">
            <Tabs.List>
              <Tabs.Tab value="revisar">{t("Por revisar")} ({pendingCount.data?.pending ?? 0})</Tabs.Tab>
              <Tabs.Tab value="mias">{t("Mis propuestas")}</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="revisar" pt="sm" className="ms-tabpanel-col">
              <ReviewTab ops={ops} initialKind={sp.get("tipo") ?? undefined} decidedFirst={!!estado && estado !== "pending"} />
            </Tabs.Panel>
            <Tabs.Panel value="mias" pt="sm" className="ms-tabpanel-col"><MineTab ops={ops} isCurator={isCurator} /></Tabs.Panel>
          </Tabs>
        : <MineTab ops={ops} isCurator={isCurator} />}
      <ProposalModal open={open} onClose={() => setOpen(null)} ops={ops} />
    </Page>
  );
}
