import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, ClearFilters, ColHead, CopyBtn, DataTable, FillArea, Modal, Notice, NumberField, Page, Panel, Pill, Segments, TextArea, TextField, useTableView, MutationError, EmptyState, PageHeader, Steps, Step, Tone, rowOpen } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fmt, get, send } from "../api";

type Prop = { id: number; name: string; body: string; source: string; source_description: string; confidence: number | null; status: string; author: string;
  created_at: string; reviewed_at: string | null; ingest_report?: { entities: number; edges: number; ontology: boolean; off_ontology: string[]; untyped_entities: number; aliased_edges?: number; auto_merged?: string[]; merge_ambiguous?: string[] } | null; review_note: string; review_kind: string; decision: any; ingest_error: string; episode_uuid: string | null; ingested_at: string | null };
const TONE: Record<string, Tone> = { pending: "warn", approved: "success", rejected: "neutral", ingested: "alt", failed: "danger" };
const LABEL: Record<string, string> = { pending: "pendiente", approved: "aprobada", rejected: "rechazada", ingested: "ingerida", failed: "fallida" };

const PROP_COLS = { name: { get: (p: Prop) => p.name }, author: { get: (p: Prop) => p.author, exact: true }, conf: { get: (p: Prop) => p.confidence ?? -1 }, at: { get: (p: Prop) => p.created_at } };
const STATUSES = ["pending", "approved", "rejected", "failed", "ingested"];
const PLURAL: Record<string, string> = { pending: T("Pendientes"), approved: T("Aprobadas"), rejected: T("Rechazadas"), failed: T("Fallidas"), ingested: T("Ingeridas") };
/** El estado se filtra en el servidor (con la cuenta de cada uno); el resto de columnas, en el navegador. «Todos» = sin filtro de estado. */
function ProposalsTable({ rows, status, onStatus, counts, onOpen }: { rows: Prop[]; status: string; onStatus: (s: string) => void; counts: Record<string, number>; onOpen: (id: number) => void }) {
  const { t } = useTranslation();
  const v = useTableView(rows, PROP_COLS, { key: "at", dir: "desc" });
  const active = v.active;
  const all = Object.values(counts).reduce((a, b) => a + b, 0);
  return (
    <Stack gap="xs">
      <Segments label={t("Estado")} value={status} onChange={onStatus}
        data={[{ value: "all", label: t("Todas"), count: all }, ...STATUSES.map((k) => ({ value: k, label: t(PLURAL[k]), count: counts[k] ?? 0 }))]} />
      <ClearFilters active={active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <FillArea><DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Título")}</ColHead>
          <ColHead sort={v.sortProps("author")} filter={v.select("author")}>{t("Autor")}</ColHead>
          <ColHead sort={v.sortProps("conf")}>{t("Confianza")}</ColHead>
          <ColHead>{t("Estado")}</ColHead>
          <ColHead sort={v.sortProps("at")}>{t("Enviada")}</ColHead>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>
          {v.rows.map((p) => (
            <DataTable.Tr key={p.id} {...rowOpen(() => onOpen(p.id))}>
              <DataTable.Td>{p.name}</DataTable.Td><DataTable.Td>{p.author}</DataTable.Td><DataTable.Td>{p.confidence ?? "—"}</DataTable.Td>
              <DataTable.Td><Pill size="sm" tone={TONE[p.status]}>{t(LABEL[p.status] ?? p.status)}</Pill></DataTable.Td><DataTable.Td>{fmt(p.created_at)}</DataTable.Td>
            </DataTable.Tr>))}
          {v.rows.length === 0 && <DataTable.Tr><DataTable.Td colSpan={5}><EmptyState>{active ? t("Ninguna propuesta coincide con los filtros.") : t("No hay propuestas en este estado.")}</EmptyState></DataTable.Td></DataTable.Tr>}
        </DataTable.Tbody>
      </DataTable></FillArea>
    </Stack>
  );
}

export default function Proposals({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isCurator = ["curator", "admin", "owner"].includes(role);
  const canPropose = isCurator || role === "contributor";
  const [status, setStatusRaw] = useState("all");
  const [chose, setChose] = useState(false);
  const setStatus = (s: string) => { setChose(true); setStatusRaw(s); };
  const [open, setOpen] = useState<number | null>(null); const [note, setNote] = useState("");
  const [name, setName] = useState(""); const [body, setBody] = useState(""); const [conf, setConf] = useState<number | string>("");
  const base = `brains/${graph}/proposals`;
  const list = useQuery({ queryKey: ["proposals", graph, status], queryFn: () => get<Prop[]>(base, { status: status === "all" ? undefined : status }) });
  const cnt = useQuery({ queryKey: ["proposals", graph, "counts"], refetchInterval: 15000, queryFn: () => get<Record<string, number>>(`${base}/counts`) });
  // Sin haber elegido nada, la bandeja abre en «Pendientes» si las hay; si no, en «Todas» (un estado vacío no debe esconder el resto).
  useEffect(() => { if (!chose && cnt.data && (cnt.data.pending ?? 0) > 0) setStatusRaw("pending"); }, [cnt.data, chose]);
  const ai = useQuery({ queryKey: ["ai-status"], refetchInterval: 60000, queryFn: () => get<Record<string, { configured: boolean }>>("ai-status") });
  const detail = useQuery({ queryKey: ["proposal", graph, open], enabled: open !== null, queryFn: () => get<Prop>(`${base}/${open}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["proposals", graph] }); qc.invalidateQueries({ queryKey: ["proposal", graph] }); };
  const submit = useMutation({ mutationFn: () => send<Prop>("POST", base, { name, body, confidence: conf === "" ? undefined : Number(conf) }),
    onSuccess: () => { setName(""); setBody(""); setConf(""); refresh(); } });
  const review = useMutation({ mutationFn: (a: { id: number; verb: "approve" | "reject" }) => send("POST", `${base}/${a.id}/${a.verb}`, { note }),
    onSuccess: () => { setOpen(null); setNote(""); refresh(); } });
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
        </Stack></Panel>)}
      <ProposalsTable rows={list.data ?? []} status={status} onStatus={setStatus} counts={cnt.data ?? {}} onOpen={(id) => { setOpen(id); setNote(""); }} />
      <Modal opened={open !== null} onClose={() => setOpen(null)} title={d?.name ?? t("Propuesta")} size="lg" centered>
        {d && <Stack gap="sm">
          <Group gap="xs"><Pill tone={TONE[d.status]}>{t(LABEL[d.status] ?? d.status)}</Pill>
            <Text size="xs" c="dimmed">{t("Confianza declarada por el autor:")} {d.confidence ?? t("no indicada")}</Text></Group>
          <Panel withBorder p="sm"><Text className="ms-prose">{d.body}</Text></Panel>
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
            <Step title={t("Ingesta en el grafo")} tone={d.status === "ingested" ? "success" : d.status === "failed" ? "danger" : "neutral"}>
              {d.status === "ingested" && <Group gap="xs"><Text size="xs" c="dimmed">{t("Episodio")} {d.episode_uuid ?? ""} · {fmt(d.ingested_at)}</Text>
                {d.episode_uuid && <CopyBtn value={d.episode_uuid} label={t("Copiar id")} doneLabel={t("Copiado")} />}</Group>}
              {d.status === "ingested" && d.ingest_report && <Text size="xs" c="dimmed">{d.ingest_report.entities} {t("entidades (")}{d.ingest_report.untyped_entities} {t("sin tipo) ·")} {d.ingest_report.edges} {t("hechos")}{d.ingest_report.ontology ? (d.ingest_report.off_ontology.length ? t(" · fuera de la ontología: {{v}}", { v: d.ingest_report.off_ontology.join(", ") }) : t(" · todos dentro de la ontología")) : t(" · sin ontología")}{d.ingest_report.aliased_edges ? t(" · {{aliased_edges}} relaciones normalizadas por alias", { aliased_edges: d.ingest_report.aliased_edges }) : ""}{d.ingest_report.auto_merged?.length ? t(" · fusionadas con su principal: {{v}}", { v: d.ingest_report.auto_merged.join(", ") }) : ""}{d.ingest_report.merge_ambiguous?.length ? t(" · sin fusionar por ambiguas: {{v}}", { v: d.ingest_report.merge_ambiguous.join(", ") }) : ""}</Text>}
              {d.status === "failed" && <Notice tone="danger">{t("Falló:")} {d.ingest_error || t("error sin detalle")}</Notice>}
              {d.status === "approved" && <Text size="xs" c="dimmed">{t("Pendiente de ingestar.")}</Text>}
              {(d.status === "pending" || d.status === "rejected") && <Text size="xs" c="dimmed">{t("No aplica.")}</Text>}
            </Step>
          </Steps>
          {isCurator && (d.status === "failed" || d.status === "approved") && <Group justify="flex-end">
            <MutationError error={retry.error} />
            <Btn kind="primary" loading={retry.isPending} onClick={() => retry.mutate(d.id)}>{d.status === "failed" ? t("Reintentar ingesta") : t("Ingerir ahora")}</Btn></Group>}
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
