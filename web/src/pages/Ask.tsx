
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, NumberField, Pill, Segments, TextArea, MutationError, Page, PageHeader, FillArea, ListCard, CodeBlock, Tabs, useTabParam } from "../ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { Brain, fmt, get, send } from "../api";
import RefQueries, { RefQueryForm, type Item, type RefQuery } from "./RefQueries";
import RecallQuality from "./RecallQuality";
import AskAnswer from "./AskAnswer";
import AskAllBrains, { type AllBrainsResult } from "./AskAllBrains";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; source_uuid: string; target_uuid: string; score: number; origin?: string };
/** Entity page of a fact's end; a lent fact opens it in the brain that lends it. */
const entityLink = (uuid: string, origin?: string) => `/entidad/${uuid}${origin ? `?origen=${origin}` : ""}`;
type Chunk = { id: number; origin?: string; name: string; text: string; valid_at: string | null; score: number; rrf: number };
type Passage = { document_id: number; chunk_idx: number; title: string; text: string; similarity: number; origin?: string };
type Res = { recall_id?: string; query: string; facts: Fact[]; chunks: Chunk[]; documents?: Passage[]; documents_state?: string; context: string; index: boolean; ms: Record<string, number> };
type Mark = "expect" | "avoid";
type Rating = "useful" | "irrelevant" | "incorrect";
type Scope = "brain" | "all";
const SCOPE_KEY = "mimirsynth.askScope";  // the last scope chosen, per browser; a convenience, Ask works the same without it
const storedScope = (): Scope => { try { return localStorage.getItem(SCOPE_KEY) === "all" ? "all" : "brain"; } catch { return "brain"; } };

export default function Ask({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const [q, setQ] = useState(() => new URLSearchParams(window.location.search).get("q") ?? "");  // «Open in Ask» from «All my brains»
  // Scope (issue 186): this brain, or the same search in every brain the person can read. A link may set it (`?alcance=`); the choice
  // is then remembered in the browser. With a single brain there is nothing to choose.
  const [params, setParams] = useSearchParams();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const several = (brains.data?.length ?? 0) > 1;
  const asked = params.get("alcance");
  const [chosen, setChosen] = useState<Scope>(() => (asked === "all" || asked === "brain" ? asked : storedScope()));
  const scope: Scope = several ? chosen : "brain";
  const setScope = (v: Scope) => {
    setChosen(v);
    try { localStorage.setItem(SCOPE_KEY, v); } catch { /* sin almacenamiento */ }
    const n = new URLSearchParams(params); n.delete("alcance"); setParams(n, { replace: true });
  };
  useEffect(() => { if (asked === "all" || asked === "brain") setScope(asked); }, [asked]);  // eslint-disable-line react-hooks/exhaustive-deps
  const [nf, setNf] = useState(8); const [nc, setNc] = useState(4);
  const [marks, setMarks] = useState<Record<string, { mark: Mark; item: Item }>>({});
  const [save, setSave] = useState<RefQuery | null>(null);
  const [tab, setTab] = useTabParam("preguntar");
  const [mode, setMode] = useTabParam("contexto", "modo");   // «Responder» writes an answer with citations (issue 126); «Contexto» shows the recall
  const status = useQuery({ queryKey: ["index", graph], queryFn: () => get<{ enabled: boolean; chunks: number; episodes: number }>("index/status", { graph }) });
  const [rated, setRated] = useState<Record<string, Rating>>({});
  const [rateMsg, setRateMsg] = useState("");
  const run = useMutation({ mutationFn: () => send<Res>("POST", `brains/${graph}/recall`, { query: q, facts: nf, chunks: nc }), onSuccess: () => { setMarks({}); setRated({}); setRateMsg(""); } });
  // The open brain pays for the query's embedding in the AI consumption (issue 176).
  const searchAll = useMutation({ mutationFn: () => send<AllBrainsResult>("POST", "search", { query: q, facts: nf, chunks: nc, brain: graph }) });
  const search = () => { if (!q.trim()) return; if (scope === "all") searchAll.mutate(); else run.mutate(); };
  useEffect(() => { run.reset(); }, [graph]);  // eslint-disable-line react-hooks/exhaustive-deps -- results of another brain are not this one's
  // Valorar lo que devolvió el recall (útil, irrelevante, incorrecto): alimenta la pestaña Calidad.
  const rate = useMutation({
    mutationFn: (a: { key: string; kind: string; id: string; rating: Rating }) => send<{ proposal_id: number | null; recorded_only: boolean }>("POST", `brains/${graph}/recall/${run.data?.recall_id}/ratings`, { kind: a.kind, id: a.id, rating: a.rating }),
    onSuccess: (r, a) => { setRated((m) => ({ ...m, [a.key]: a.rating })); setRateMsg(r.proposal_id ? t("Se ha propuesto la corrección del hecho (propuesta #{{id}}); la decide un curador.", { id: r.proposal_id }) : r.recorded_only ? t("Valoración guardada. Con tu rol no se propone la corrección: la verá un curador en Calidad.") : ""); } });
  const rateBtns = (key: string, kind: string, id: string, canIncorrect = true) => run.data?.recall_id && <Group gap={2} wrap="nowrap">
    {(["useful", "irrelevant", ...(canIncorrect ? ["incorrect"] : [])] as Rating[]).map((v) => (
      <Btn key={v} size="row" kind={rated[key] === v ? (v === "useful" ? "primary" : "danger") : "ghost"} onClick={() => rate.mutate({ key, kind, id, rating: v })}>
        {v === "useful" ? t("Útil") : v === "irrelevant" ? t("Irrelevante") : t("Incorrecto")}</Btn>))}
  </Group>;
  const view = scope === "all" ? "contexto" : mode;  // across brains there is no written answer: it needs one brain's recall
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
        onKeyDown={(e) => { if (view === "contexto" && e.key === "Enter" && (e.ctrlKey || e.metaKey) && q) search(); }} />
      <Group gap="md" align="flex-end">
        {several && <Segments label={t("Alcance")} value={scope} onChange={(v) => setScope(v as Scope)}
          data={[{ value: "brain", label: t("Este brain") }, { value: "all", label: t("Todos mis brains") }]} />}
        {scope === "brain" && <Segments label={t("Modo")} value={mode} onChange={(v) => setMode(v)}
          data={[{ value: "responder", label: t("Responder") }, { value: "contexto", label: t("Contexto") }]} />}
      </Group>
      {scope === "all" && <Text size="xs" c="dimmed">{t("La misma búsqueda en todos los brains que puedes leer, con tu rol en cada uno y sin federación. La respuesta redactada, las valoraciones y guardar como consulta de referencia solo están en «Este brain»: los resultados mezclan brains distintos.")}</Text>}
      <Group align="flex-end">
        <NumberField size="xs" label={t("Hechos")} value={nf} min={0} max={30} onChange={(v) => setNf(Number(v) || 0)} w={80} />
        <NumberField size="xs" label={t("Fragmentos")} value={nc} min={0} max={15} onChange={(v) => setNc(Number(v) || 0)} w={100} />
        {view === "contexto" && <Btn kind="primary" disabled={!q} loading={run.isPending || searchAll.isPending} onClick={search}>{t("Buscar (Ctrl+Enter)")}</Btn>}
        {view === "contexto" && scope === "brain" && r && <Text size="xs" c="dimmed">{r.ms.total} {t("ms (embedding")} {r.ms.embed} {t("· hechos")} {r.ms.facts} {t("· fragmentos")} {r.ms.chunks})</Text>}
        {view === "contexto" && scope === "brain" && r && canSync && <Btn size="row" icon="save" onClick={() => setSave(toRef())}>{marked.length ? t("Guardar como consulta de referencia ({{n}} marcados)", { n: marked.length }) : t("Guardar como consulta de referencia")}</Btn>}
      </Group>
      {view === "responder" && <AskAnswer graph={graph} query={q} facts={nf} chunks={nc} />}
      {scope === "all" && <MutationError error={searchAll.error} />}
      {scope === "all" && searchAll.data && <AskAllBrains r={searchAll.data} />}
      {view === "contexto" && scope === "brain" && <MutationError error={run.error ?? rate.error} />}
      {view === "contexto" && scope === "brain" && rateMsg && <Text size="xs" c="dimmed">{rateMsg}</Text>}
      {view === "contexto" && scope === "brain" && r && (
        <div className="ms-ask-wrap"><div className="ms-ask-cols">
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
        </div></div>)}
      {save && <RefQueryForm graph={graph} initial={save} onClose={() => setSave(null)} />}
    </Stack>
  );
  return (
    <Page>
      <PageHeader title={t("Preguntar")} description={<>{t("Recall híbrido: hechos del grafo (vigentes e invalidados) más fragmentos de los episodios originales. Es el contexto que se inyecta al agente.")} {t("«Responder» redacta con ese mismo recall una respuesta que cita de dónde sale cada afirmación.")}</>} />
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
