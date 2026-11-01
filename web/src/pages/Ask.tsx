
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, NumberField, Pill, TextArea, MutationError, Page, PageHeader, FillArea, ListCard, CodeBlock, Tabs, useTabParam } from "../ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { fmt, get, send } from "../api";
import RefQueries, { RefQueryForm, type Item, type RefQuery } from "./RefQueries";
import RecallQuality from "./RecallQuality";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; source_uuid: string; target_uuid: string; score: number; origin?: string };
/** Entity page of a fact's end; a lent fact opens it in the brain that lends it. */
const entityLink = (uuid: string, origin?: string) => `/entidad/${uuid}${origin ? `?origen=${origin}` : ""}`;
type Chunk = { id: number; origin?: string; name: string; text: string; valid_at: string | null; score: number; rrf: number };
type Passage = { document_id: number; chunk_idx: number; title: string; text: string; similarity: number; origin?: string };
type Res = { recall_id?: string; query: string; facts: Fact[]; chunks: Chunk[]; documents?: Passage[]; documents_state?: string; context: string; index: boolean; ms: Record<string, number> };
type Mark = "expect" | "avoid";
type Rating = "useful" | "irrelevant" | "incorrect";

export default function Ask({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [nf, setNf] = useState(8); const [nc, setNc] = useState(4);
  const [marks, setMarks] = useState<Record<string, { mark: Mark; item: Item }>>({});
  const [save, setSave] = useState<RefQuery | null>(null);
  const [tab, setTab] = useTabParam("preguntar");
  const status = useQuery({ queryKey: ["index", graph], queryFn: () => get<{ enabled: boolean; chunks: number; episodes: number }>("index/status", { graph }) });
  const [rated, setRated] = useState<Record<string, Rating>>({});
  const [rateMsg, setRateMsg] = useState("");
  const run = useMutation({ mutationFn: () => send<Res>("POST", `brains/${graph}/recall`, { query: q, facts: nf, chunks: nc }), onSuccess: () => { setMarks({}); setRated({}); setRateMsg(""); } });
  // Valorar lo que devolvió el recall (útil, irrelevante, incorrecto): alimenta la pestaña Calidad.
  const rate = useMutation({
    mutationFn: (a: { key: string; kind: string; id: string; rating: Rating }) => send<{ proposal_id: number | null; recorded_only: boolean }>("POST", `brains/${graph}/recall/${run.data?.recall_id}/ratings`, { kind: a.kind, id: a.id, rating: a.rating }),
    onSuccess: (r, a) => { setRated((m) => ({ ...m, [a.key]: a.rating })); setRateMsg(r.proposal_id ? t("Se ha propuesto la corrección del hecho (propuesta #{{id}}); la decide un curador.", { id: r.proposal_id }) : r.recorded_only ? t("Valoración guardada. Con tu rol no se propone la corrección: la verá un curador en Calidad.") : ""); } });
  const rateBtns = (key: string, kind: string, id: string, canIncorrect = true) => run.data?.recall_id && <Group gap={2} wrap="nowrap">
    {(["useful", "irrelevant", ...(canIncorrect ? ["incorrect"] : [])] as Rating[]).map((v) => (
      <Btn key={v} size="row" kind={rated[key] === v ? (v === "useful" ? "primary" : "danger") : "ghost"} onClick={() => rate.mutate({ key, kind, id, rating: v })}>
        {v === "useful" ? t("Útil") : v === "irrelevant" ? t("Irrelevante") : t("Incorrecto")}</Btn>))}
  </Group>;
  const sync = useMutation({ mutationFn: () => send<any>("POST", `brains/${graph}/index/sync`), onSuccess: () => status.refetch() });
  const canSync = ["curator", "admin", "owner"].includes(role);
  const r = run.data;
  // Marcar un resultado como «debe salir» o «sobra» para guardarla como consulta de referencia. Se guarda el principio del texto.
  const toggle = (key: string, mark: Mark, item: Item) => setMarks((m) => {
    const n = { ...m };
    if (n[key]?.mark === mark) delete n[key]; else n[key] = { mark, item: { ...item, text: item.text.slice(0, 200) } };
    return n;
  });
  const markBtns = (key: string, item: Item) => canSync && <Group gap={4} wrap="nowrap">
    <Btn size="row" kind={marks[key]?.mark === "expect" ? "primary" : "ghost"} icon="check" onClick={() => toggle(key, "expect", item)}>{t("Debe salir")}</Btn>
    <Btn size="row" kind={marks[key]?.mark === "avoid" ? "danger" : "ghost"} icon="close" onClick={() => toggle(key, "avoid", item)}>{t("Sobra")}</Btn>
  </Group>;
  const marked = Object.values(marks);
  const toRef = (): RefQuery => ({ query: r?.query ?? q, expect: marked.filter((m) => m.mark === "expect").map((m) => m.item), avoid: marked.filter((m) => m.mark === "avoid").map((m) => m.item),
    docs: null, note: "" });
  const ask = (
    <Stack gap="xs">
      <Group gap="xs">
        {status.data && <Pill tone={status.data.enabled ? "success" : "warn"}>{status.data.enabled ? t("índice: {{chunks}} fragmentos de {{episodes}} episodios", { chunks: status.data.chunks, episodes: status.data.episodes }) : t("índice de texto desactivado (requiere PostgreSQL)")}</Pill>}
        {canSync && status.data?.enabled && <Btn size="row" loading={sync.isPending} onClick={() => sync.mutate()} icon="refresh">{t("Reindexar ahora")}</Btn>}
        {sync.data && <Text size="xs" c="dimmed">{sync.data.reindexed} {t("episodios reindexados")}</Text>}
      </Group>
      <TextArea autosize minRows={2} placeholder={t("¿Dónde está Nextcloud ahora?")} value={q} onChange={(e) => setQ(e.currentTarget.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && q) run.mutate(); }} />
      <Group align="flex-end">
        <NumberField size="xs" label={t("Hechos")} value={nf} min={0} max={30} onChange={(v) => setNf(Number(v) || 0)} w={80} />
        <NumberField size="xs" label={t("Fragmentos")} value={nc} min={0} max={15} onChange={(v) => setNc(Number(v) || 0)} w={100} />
        <Btn kind="primary" disabled={!q} loading={run.isPending} onClick={() => run.mutate()}>{t("Buscar (Ctrl+Enter)")}</Btn>
        {r && <Text size="xs" c="dimmed">{r.ms.total} {t("ms (embedding")} {r.ms.embed} {t("· hechos")} {r.ms.facts} {t("· fragmentos")} {r.ms.chunks})</Text>}
        {r && canSync && <Btn size="row" icon="save" onClick={() => setSave(toRef())}>{marked.length ? t("Guardar como consulta de referencia ({{n}} marcados)", { n: marked.length }) : t("Guardar como consulta de referencia")}</Btn>}
      </Group>
      <MutationError error={run.error ?? rate.error} />
      {rateMsg && <Text size="xs" c="dimmed">{rateMsg}</Text>}
      {r && (
        <Group align="flex-start" wrap="nowrap" gap="md">
          <Stack className="ms-ask-main" gap="xs">
            <Title order={5}>{t("Hechos (")}{r.facts.length})</Title>
            {r.facts.map((f) => (
              <ListCard key={f.uuid} invalid={f.status === "invalidated"} actions={<Group gap="xs" wrap="nowrap">{rateBtns(`f:${f.uuid}`, "fact", f.uuid, !f.origin)}{markBtns(`f:${f.uuid}`, { text: f.fact, kind: "fact" })}</Group>}
                tags={<>{f.origin && <Pill size="xs" tone="alt">{f.origin}</Pill>}<Link to={entityLink(f.source_uuid, f.origin)} className="ms-nolink"><Pill size="xs">{f.source}</Pill></Link>
                  <Text size="xs" className="ms-data">{f.name}</Text><Link to={entityLink(f.target_uuid, f.origin)} className="ms-nolink"><Pill size="xs">{f.target}</Pill></Link></>}
                meta={<>{t("sim")} {f.score} · {fmt(f.valid_at)}{f.invalid_at ? ` → ${fmt(f.invalid_at)}` : ""}</>}>{f.fact}</ListCard>))}
            <Title order={5} mt="xs">{t("Fragmentos de episodios (")}{r.chunks.length})</Title>
            {r.chunks.map((c) => (
              <ListCard key={`${c.origin ?? ""}-${c.id}`} title={c.origin ? `${c.name} · ${c.origin}` : c.name} aside={`${fmt(c.valid_at)} · sim ${c.score}`}
                actions={<Group gap="xs" wrap="nowrap">{rateBtns(`c:${c.origin ?? ""}:${c.id}`, "chunk", `${c.origin ?? ""}:${c.id}`, false)}{markBtns(`c:${c.origin ?? ""}:${c.id}`, { text: c.text, kind: "chunk" })}</Group>}>{c.text}</ListCard>))}
            {!!r.documents?.length && <>
              <Title order={5} mt="xs">{t("Pasajes de documentos ({{n}})", { n: r.documents.length })}</Title>
              {r.documents.map((p) => (
                <ListCard key={`${p.origin ?? ""}-${p.document_id}-${p.chunk_idx}`} title={p.origin ? `${p.title} · ${p.origin}` : p.title} aside={`sim ${p.similarity.toFixed(2)}`}
                  actions={<Group gap="xs" wrap="nowrap">{rateBtns(`d:${p.origin ?? ""}:${p.document_id}:${p.chunk_idx}`, "doc", `${p.origin ?? ""}:${p.document_id}:${p.chunk_idx}`, false)}{markBtns(`d:${p.origin ?? ""}:${p.document_id}:${p.chunk_idx}`, { text: p.text, kind: "doc" })}</Group>}>{p.text}</ListCard>))}
            </>}
          </Stack>
          <Stack gap="xs" className="ms-ask-side">
            <Title order={6}>{t("Contexto inyectado")}</Title>
            <CodeBlock copy>{r.context}</CodeBlock>
          </Stack>
        </Group>)}
      {save && <RefQueryForm graph={graph} initial={save} onClose={() => setSave(null)} />}
    </Stack>
  );
  return (
    <Page>
      <PageHeader title={t("Preguntar")} description={<>{t("Recall híbrido: hechos del grafo (vigentes e invalidados) más fragmentos de los episodios originales. Es el contexto que se inyecta al agente.")}</>} />
      <FillArea>
        {canSync ? <Tabs value={tab} onChange={(v) => setTab(v)}>
          <Tabs.List>
            <Tabs.Tab value="preguntar">{t("Preguntar")}</Tabs.Tab>
            <Tabs.Tab value="referencia">{t("Consultas de referencia")}</Tabs.Tab>
            <Tabs.Tab value="calidad">{t("Calidad")}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="preguntar" pt="sm">{ask}</Tabs.Panel>
          <Tabs.Panel value="referencia" pt="sm"><RefQueries graph={graph} /></Tabs.Panel>
          <Tabs.Panel value="calidad" pt="sm"><RecallQuality graph={graph} canAdmin={["admin", "owner"].includes(role)} /></Tabs.Panel>
        </Tabs> : ask}
      </FillArea>
    </Page>
  );
}
