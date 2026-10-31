import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, ClearFilters, Icon, ColHead, CopyBtn, DataTable, FillArea, Modal, Notice, NumberField, Page, Pager, Panel, Pill, Segments, TextArea, TextField, useServerTableView, MutationError, EmptyState, PageHeader, Steps, Step, Tone, rowOpen } from "../ui";
import { SecretsNotice, type SecretFinding } from "./Secrets";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fmt, get, send } from "../api";

type Prop = { id: number; name: string; body: string; source: string; source_description: string; confidence: number | null; status: string; author: string;
  created_at: string; reviewed_at: string | null; ingest_report?: { entities: number; edges: number; ontology: boolean; off_ontology: string[]; untyped_entities: number; aliased_edges?: number; auto_merged?: string[]; merge_ambiguous?: string[] } | null; review_note: string; review_kind: string; decision: any; ingest_error: string; episode_uuid: string | null; ingested_at: string | null; secrets?: SecretFinding[];
  kind?: string; correction?: Correction | null; secrets_notice?: string };
/** Correction of a fact: the fact as it was when proposed, the reason and, once applied, when (and whether it was undone). */
type Correction = { fact_uuid: string; fact: { fact: string; source: string; target: string; name: string; valid_at: string | null }; reason: string;
  invalid_at: string; applied_at?: string; reverted_at?: string };
const TONE: Record<string, Tone> = { pending: "warn", approved: "success", rejected: "neutral", ingested: "alt", failed: "danger" };
const LABEL: Record<string, string> = { pending: "pendiente", approved: "aprobada", rejected: "rechazada", ingested: "ingerida", failed: "fallida" };

/** Marker in the list for a proposal the secret detector touched: masked (already safe) or flagged (a person must look). Text and icon, not only colour. */
function SecretsPill({ found }: { found?: SecretFinding[] }) {
  const { t } = useTranslation();
  if (!found?.length) return null;
  const flagged = found.some((f) => f.action === "flagged");
  return <Pill size="xs" tone={flagged ? "warn" : "neutral"} title={[...new Set(found.map((f) => t(f.label)))].join(", ")}>
    <Group gap={4} wrap="nowrap"><Icon name="lock" size={12} />{flagged ? t("Secreto por revisar") : t("Secreto enmascarado")}</Group></Pill>;
}

type PropList = { total: number; limit: number; offset: number; authors: { id: number; name: string }[]; items: Prop[] };
const STATUSES = ["pending", "approved", "rejected", "failed", "ingested"];
const PLURAL: Record<string, string> = { pending: T("Pendientes"), approved: T("Aprobadas"), rejected: T("Rechazadas"), failed: T("Fallidas"), ingested: T("Ingeridas") };
type View = ReturnType<typeof useProposalsView>;
const useProposalsView = () => useServerTableView({ q: "", author: "" }, { debounced: ["q"], firstDir: { name: "asc", author: "asc" } });

/** Estado, filtros, orden y página se resuelven en el servidor (#88): con muchas propuestas se llega a todas y los filtros abarcan el conjunto entero.
 *  Devuelve hijos directos de la página: así solo la tabla (`FillArea`) se desplaza y el formulario de alta no se encoge. «Todas» = sin filtro de estado. */
function ProposalsTable({ data, view, status, onStatus, counts, onOpen }: { data?: PropList; view: View; status: string; onStatus: (s: string) => void; counts: Record<string, number>; onOpen: (id: number) => void }) {
  const { t } = useTranslation();
  const { f, setFilter, sortProps, page, setPage, active, clear } = view;
  const rows = data?.items ?? [];
  const all = counts.all ?? 0;  // el servidor ya la da; sumar los valores contaba «all» dos veces (#79)
  return (<>
    <Segments label={t("Estado")} value={status} onChange={onStatus}
      data={[{ value: "all", label: t("Todas"), count: all }, ...STATUSES.map((k) => ({ value: k, label: t(PLURAL[k]), count: counts[k] ?? 0 }))]} />
    <ClearFilters active={active} onClear={clear} />
    <FillArea><DataTable fz="sm">
      <DataTable.Thead><DataTable.Tr>
        <ColHead sort={sortProps("name")} filter={{ kind: "text", value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Título…") }}>{t("Título")}</ColHead>
        <ColHead sort={sortProps("author")} filter={{ kind: "select", value: f.author, onChange: (v) => setFilter({ author: v }), allLabel: t("Todos los autores"), options: (data?.authors ?? []).map((a) => ({ value: String(a.id), label: a.name })) }}>{t("Autor")}</ColHead>
        <ColHead sort={sortProps("conf")}>{t("Confianza")}</ColHead>
        <ColHead>{t("Estado")}</ColHead>
        <ColHead sort={sortProps("at")}>{t("Enviada")}</ColHead>
      </DataTable.Tr></DataTable.Thead>
      <DataTable.Tbody>
        {rows.map((p) => (
          <DataTable.Tr key={p.id} {...rowOpen(() => onOpen(p.id))}>
            <DataTable.Td><Group gap="xs" wrap="nowrap">{p.name}<SecretsPill found={p.secrets} /></Group></DataTable.Td><DataTable.Td>{p.author}</DataTable.Td><DataTable.Td>{p.confidence ?? "—"}</DataTable.Td>
            <DataTable.Td><Pill size="sm" tone={TONE[p.status]}>{t(LABEL[p.status] ?? p.status)}</Pill></DataTable.Td><DataTable.Td>{fmt(p.created_at)}</DataTable.Td>
          </DataTable.Tr>))}
        {data && rows.length === 0 && <DataTable.Tr><DataTable.Td colSpan={5}><EmptyState>{active ? t("Ninguna propuesta coincide con los filtros.") : t("No hay propuestas en este estado.")}</EmptyState></DataTable.Td></DataTable.Tr>}
      </DataTable.Tbody>
    </DataTable></FillArea>
    <Pager total={data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />
  </>);
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

export default function Proposals({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isCurator = ["curator", "admin", "owner"].includes(role);
  const canPropose = isCurator || role === "contributor";
  const [status, setStatusRaw] = useState("all");
  const [chose, setChose] = useState(false);
  const view = useProposalsView();
  const setStatus = (s: string) => { setChose(true); setStatusRaw(s); view.setPage((p) => ({ ...p, offset: 0 })); };
  const [open, setOpen] = useState<number | null>(null); const [note, setNote] = useState("");
  const [name, setName] = useState(""); const [body, setBody] = useState(""); const [conf, setConf] = useState<number | string>("");
  const base = `brains/${graph}/proposals`;
  const { sent, sort, page } = view;
  const list = useQuery({ queryKey: ["proposals", graph, status, sent.q, sent.author, sort?.key, sort?.dir, page.offset, page.limit], placeholderData: keepPreviousData,
    queryFn: () => get<PropList>(base, { status: status === "all" ? undefined : status, q: sent.q || undefined, author: sent.author || undefined,
      sort: sort?.key, order: sort?.dir, limit: page.limit, offset: page.offset }) });
  const cnt = useQuery({ queryKey: ["proposals", graph, "counts"], refetchInterval: 15000, queryFn: () => get<Record<string, number>>(`${base}/counts`) });
  // Sin haber elegido nada, la bandeja abre en «Pendientes» si las hay; si no, en «Todas» (un estado vacío no debe esconder el resto).
  useEffect(() => { if (!chose && cnt.data && (cnt.data.pending ?? 0) > 0) setStatusRaw("pending"); }, [cnt.data, chose]);
  const ai = useQuery({ queryKey: ["ai-status"], refetchInterval: 60000, queryFn: () => get<Record<string, { configured: boolean }>>("ai-status") });
  const detail = useQuery({ queryKey: ["proposal", graph, open], enabled: open !== null, queryFn: () => get<Prop>(`${base}/${open}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["proposals", graph] }); qc.invalidateQueries({ queryKey: ["proposal", graph] }); };
  const [sentProp, setSentProp] = useState<Prop | null>(null);  // the last one sent, so its author sees what happened to it
  const submit = useMutation({ mutationFn: () => send<Prop>("POST", base, { name, body, confidence: conf === "" ? undefined : Number(conf) }),
    onMutate: () => setSentProp(null),
    onSuccess: (p) => { setName(""); setBody(""); setConf(""); setSentProp(p); refresh(); } });
  const review = useMutation({ mutationFn: (a: { id: number; verb: "approve" | "reject" }) => send("POST", `${base}/${a.id}/${a.verb}`, { note }),
    onSuccess: () => { setOpen(null); setNote(""); refresh(); } });
  const reactivate = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/reactivate`), onSuccess: refresh });
  const retry = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/ingest`), onSuccess: () => { setOpen(null); setTimeout(refresh, 8000); refresh(); } });
  const d = detail.data;
  if (role === "reader") return <Page><PageHeader title={t("Propuestas")} description={<>{t("Con rol de lector no puedes proponer ni ver propuestas. Pide rol de colaborador a un administrador del brain.")}</>} /></Page>;
  return (
    <Page>
      <PageHeader title={t("Propuestas")} description={<>{t("Cuarentena de aportaciones. Lo que envía un colaborador o un agente no entra al grafo hasta que un curador lo aprueba; las de un curador quedan aprobadas al enviarlas.")}</>} />
      {ai.data && !ai.data.llm.configured && <Notice tone="warn" title={t("Sin motor LLM configurado")}>{t("Las propuestas aprobadas no se ingieren al grafo y se quedan en «Aprobadas». Un administrador debe configurarlo en Administración → Proveedores IA.")}</Notice>}
      {ai.data && ai.data.llm.configured && !ai.data.decider.configured && <Notice>{t("Sin decisor: las propuestas de colaboradores esperan siempre a un curador.")}</Notice>}
      {canPropose && (
        <Panel withBorder p="sm"><Stack gap="xs">
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
        </Stack></Panel>)}
      <MutationError error={list.error} />
      <ProposalsTable data={list.data} view={view} status={status} onStatus={setStatus} counts={cnt.data ?? {}} onOpen={(id) => { setOpen(id); setNote(""); }} />
      <Modal opened={open !== null} onClose={() => setOpen(null)} title={d?.name ?? t("Propuesta")} size="lg" centered>
        {d && <Stack gap="sm">
          <Group gap="xs"><Pill tone={TONE[d.status]}>{t(LABEL[d.status] ?? d.status)}</Pill>
            <Text size="xs" c="dimmed">{t("Confianza declarada por el autor:")} {d.confidence ?? t("no indicada")}</Text></Group>
          {d.correction ? <CorrectionDetail c={d.correction} replacement={d.body} /> : <Panel withBorder p="sm"><Text className="ms-prose">{d.body}</Text></Panel>}
          <SecretsNotice found={d.secrets} />
          <Steps>
            <Step title={t("Enviada")} tone="success"><Text size="xs" c="dimmed">{d.author} · {fmt(d.created_at)}</Text></Step>
            <Step title={t("Revisión")} tone={d.status === "rejected" ? "danger" : d.status === "pending" ? "warn" : "success"}>
              {d.review_kind === "direct" && <Text size="xs" c="dimmed">{t("Aprobada al enviar (el autor es curador o superior) ·")} {fmt(d.reviewed_at)}</Text>}
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
              {d.status === "ingested" && <Group gap="xs"><Text size="xs" c="dimmed">{t("Episodio")} {d.episode_uuid ?? ""} · {fmt(d.ingested_at)}</Text>
                {d.episode_uuid && <CopyBtn value={d.episode_uuid} label={t("Copiar id")} doneLabel={t("Copiado")} />}</Group>}
              {d.status === "ingested" && d.ingest_report && <Text size="xs" c="dimmed">{d.ingest_report.entities} {t("entidades (")}{d.ingest_report.untyped_entities} {t("sin tipo) ·")} {d.ingest_report.edges} {t("hechos")}{d.ingest_report.ontology ? (d.ingest_report.off_ontology.length ? t(" · fuera de la ontología: {{v}}", { v: d.ingest_report.off_ontology.join(", ") }) : t(" · todos dentro de la ontología")) : t(" · sin ontología")}{d.ingest_report.aliased_edges ? t(" · {{aliased_edges}} relaciones normalizadas por alias", { aliased_edges: d.ingest_report.aliased_edges }) : ""}{d.ingest_report.auto_merged?.length ? t(" · fusionadas con su principal: {{v}}", { v: d.ingest_report.auto_merged.join(", ") }) : ""}{d.ingest_report.merge_ambiguous?.length ? t(" · sin fusionar por ambiguas: {{v}}", { v: d.ingest_report.merge_ambiguous.join(", ") }) : ""}</Text>}
              {d.status === "failed" && <Notice tone="danger">{t("Falló:")} {d.ingest_error || t("error sin detalle")}</Notice>}
              {d.status === "approved" && <Text size="xs" c="dimmed">{t("Pendiente de ingestar.")}</Text>}
              {(d.status === "pending" || d.status === "rejected") && <Text size="xs" c="dimmed">{t("No aplica.")}</Text>}
            </Step>}
          </Steps>
          {isCurator && (d.status === "failed" || d.status === "approved") && <Group justify="flex-end">
            <MutationError error={retry.error} />
            <Btn kind="primary" loading={retry.isPending} onClick={() => retry.mutate(d.id)}>{d.status === "failed" ? t("Reintentar ingesta") : t("Ingerir ahora")}</Btn></Group>}
          {isCurator && d.correction?.applied_at && !d.correction.reverted_at && <Group justify="flex-end">
            <MutationError error={reactivate.error} />
            <Btn kind="secondary" loading={reactivate.isPending} onClick={() => reactivate.mutate(d.id)} icon="undo">{t("Reactivar el hecho")}</Btn></Group>}
          {isCurator && d.status === "pending" && <>
            <TextArea size="xs" autosize minRows={2} label={t("Nota (opcional)")} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
            <MutationError error={review.error} />
            <Group justify="flex-end">
              <Btn kind="danger" loading={review.isPending} onClick={() => review.mutate({ id: d.id, verb: "reject" })} icon="close">{t("Rechazar")}</Btn>
              <Btn kind="primary" loading={review.isPending} onClick={() => review.mutate({ id: d.id, verb: "approve" })} icon="check">{t("Aprobar")}</Btn>
            </Group></>}
        </Stack>}
      </Modal>
    </Page>
  );
}
