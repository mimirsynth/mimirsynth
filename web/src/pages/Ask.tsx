
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, NumberField, Pill, Segments, TextArea, MutationError, Page, PageHeader, FillArea, ListCard, CodeBlock, Tabs, useTabParam, CardLink } from "../ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Fragment, useEffect, useState } from "react";
import { Brain, fmt, fmtDay, get, send } from "../api";
import RefQueries, { RefQueryForm, type Item, type RefQuery } from "./RefQueries";
import RecallQuality from "./RecallQuality";
import AskAnswer from "./AskAnswer";
import AskAllBrains, { type AllBrainsResult } from "./AskAllBrains";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; source_uuid: string; target_uuid: string; score?: number; similarity?: number | null; origin?: string; replaces?: string };
/** Entity page of a fact's end; a lent fact opens it in the brain that lends it. */
const entityLink = (uuid: string, origin?: string) => `/entidad/${uuid}${origin ? `?origen=${origin}` : ""}`;
type Superseded = { uuid: string; fact: string; invalid_at: string | null; replaced_by: { uuid: string; fact: string }[] }[];
type Chunk = { id: number; origin?: string; name: string; text: string; valid_at: string | null; score: number; similarity?: number | null; rrf: number; superseded?: Superseded };
type Passage = { document_id: number; chunk_idx: number; title: string; text: string; similarity: number; origin?: string; superseded?: Superseded;
  source_updated_at?: string | null; last_seen_at?: string | null };
type Res = { recall_id?: string; query: string; facts: Fact[]; chunks: Chunk[]; documents?: Passage[]; documents_state?: string; context: string; index: boolean; min_similarity?: number; ms: Record<string, number> };
/** «0.42», or null for what joins the recall by its link to a fact no longer true rather than by its closeness to the question. */
const simValue = (x: { similarity?: number | null; score?: number }) => { const v = x.similarity ?? x.score; return typeof v === "number" ? v.toFixed(2) : null; };
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
  const sim = (x: { similarity?: number | null; score?: number }) => { const v = simValue(x); return v === null ? null : `${t("sim")} ${v}`; };
  // Every card of the result has an anchor, so what replaces what reads as a link between the two cards (issue: critique of Ask).
  const factAnchor = (origin: string | undefined, uuid: string) => `hecho-${origin ?? ""}-${uuid}`;
  const chunkAnchor = (c: Chunk) => `fragmento-${c.origin ?? ""}-${c.id}`;
  const passageAnchor = (p: Passage) => `pasaje-${p.origin ?? ""}-${p.document_id}-${p.chunk_idx}`;
  /** «fact», a link to its card when it is in the result. */
  const factRef = (origin: string | undefined, uuid: string, text: string) => r?.facts.some((x) => x.uuid === uuid && x.origin === origin)
    ? <>«<CardLink to={factAnchor(origin, uuid)}>{text}</CardLink>»</> : <>«{text}»</>;
  /** The fragments and passages of the result that state a fact no longer true. */
  const statedBy = (f: Fact) => [...(r?.chunks ?? []).map((c) => ({ origin: c.origin, name: c.name, anchor: chunkAnchor(c), gone: c.superseded })),
    ...(r?.documents ?? []).map((p) => ({ origin: p.origin, name: p.title, anchor: passageAnchor(p), gone: p.superseded }))]
    .filter((x) => x.origin === f.origin && x.gone?.some((s) => s.uuid === f.uuid));
  const current = r?.facts.filter((f) => f.status !== "invalidated") ?? [];
  const gone = r?.facts.filter((f) => f.status === "invalidated") ?? [];
  /** The sentence under a fact: what it replaces, or, for one no longer true, what replaced it and what in the result states it. */
  const factNote = (f: Fact) => {
    if (f.status !== "invalidated") {
      if (!f.replaces) return undefined;
      const old = gone.find((g) => g.origin === f.origin && g.fact === f.replaces);
      return <>{t("Sustituye a")} {old ? factRef(old.origin, old.uuid, old.fact) : <>«{f.replaces}»</>}</>;
    }
    const now = current.filter((c) => c.origin === f.origin && c.replaces === f.fact);
    const by = statedBy(f);
    if (!now.length && !by.length) return undefined;
    return <>
      {now.length > 0 && <div>{t("Ahora:")} {now.map((c, i) => <Fragment key={c.uuid}>{i ? " · " : ""}{factRef(c.origin, c.uuid, c.fact)}</Fragment>)}</div>}
      {by.length > 0 && <div>{t("Lo dice:")} {by.map((x, i) => <Fragment key={x.anchor}>{i ? " · " : ""}«<CardLink to={x.anchor}>{x.name}</CardLink>»</Fragment>)}</div>}
    </>;
  };
  const validity = (f: Fact) => (f.invalid_at ? `${fmtDay(f.valid_at)} → ${fmtDay(f.invalid_at)}` : t("desde {{date}}", { date: fmtDay(f.valid_at) }));
  const factCard = (f: Fact) => (
    <ListCard key={`${f.origin ?? ""}-${f.uuid}`} anchor={factAnchor(f.origin, f.uuid)} invalid={f.status === "invalidated"} note={factNote(f)}
      actions={<Group gap="xs" wrap="nowrap">{rateBtns(`f:${f.uuid}`, "fact", f.uuid, !f.origin)}{markBtns(`f:${f.uuid}`, { text: f.fact, kind: "fact" })}</Group>}
      tags={<>{f.origin && <Pill size="xs" tone="alt">{f.origin}</Pill>}<Link to={entityLink(f.source_uuid, f.origin)} className="ms-nolink"><Pill size="xs">{f.source}</Pill></Link>
        <Text size="xs" className="ms-data">{f.name}</Text><Link to={entityLink(f.target_uuid, f.origin)} className="ms-nolink"><Pill size="xs">{f.target}</Pill></Link></>}
      meta={`${sim(f) ?? t("sin similitud")} · ${validity(f)}`}>{f.fact}</ListCard>);
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
  // A fragment or a passage that states something no longer true (issues 282 and 286): the mark first, then what stopped being true and
  // what is true now, before its text, so it is not read as current.
  const supersededNotice = (origin: string | undefined, sup?: Superseded) => (sup?.length ? <>
    <Pill size="xs" tone="warn">{t("Puede estar superado")}</Pill>
    {sup.map((s) => (
      <div key={s.uuid}>
        <div>{t("Dejó de ser cierto el {{date}}:", { date: fmtDay(s.invalid_at) })} {factRef(origin, s.uuid, s.fact)}</div>
        {s.replaced_by.length > 0 && <div>{t("Ahora:")} {s.replaced_by.map((x, i) => <Fragment key={x.uuid}>{i ? " · " : ""}{factRef(origin, x.uuid, x.fact)}</Fragment>)}</div>}
      </div>))}
  </> : undefined);
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
            {!r.facts.length && !r.chunks.length && !!r.min_similarity && (
              <Text size="xs" c="dimmed">{t("Ningún hecho ni fragmento llega a la similitud mínima ({{v}}, en Administración → Recuerdo).", { v: r.min_similarity })}</Text>)}
            <Title order={5}>{t("Hechos vigentes ({{n}})", { n: current.length })}</Title>
            {current.map(factCard)}
            {gone.length > 0 && <>
              <Title order={5} mt="xs">{t("Hechos que dejaron de ser ciertos ({{n}})", { n: gone.length })}</Title>
              {gone.map(factCard)}
            </>}
            <Title order={5} mt="xs">{t("Fragmentos de episodios ({{n}})", { n: r.chunks.length })}</Title>
            {r.chunks.map((c) => (
              <ListCard key={`${c.origin ?? ""}-${c.id}`} anchor={chunkAnchor(c)} title={c.origin ? `${c.name} · ${c.origin}` : c.name} aside={[fmt(c.valid_at), sim(c)].filter(Boolean).join(" · ")}
                actions={<Group gap="xs" wrap="nowrap">{rateBtns(`c:${c.origin ?? ""}:${c.id}`, "chunk", `${c.origin ?? ""}:${c.id}`, false)}{markBtns(`c:${c.origin ?? ""}:${c.id}`, { text: c.text, kind: "chunk" })}</Group>}
                notice={supersededNotice(c.origin, c.superseded)}>{c.text}</ListCard>))}
            {!!r.documents?.length && <>
              <Title order={5} mt="xs">{t("Pasajes de documentos ({{n}})", { n: r.documents.length })}</Title>
              {r.documents.map((p) => (
                <ListCard key={`${p.origin ?? ""}-${p.document_id}-${p.chunk_idx}`} anchor={passageAnchor(p)} title={p.origin ? `${p.title} · ${p.origin}` : p.title}
                  aside={[t("actualizado el {{date}}", { date: fmt(p.source_updated_at ?? p.last_seen_at) }), sim(p)].filter(Boolean).join(" · ")}
                  notice={supersededNotice(p.origin, p.superseded)}
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
