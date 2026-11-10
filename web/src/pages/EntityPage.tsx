import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Block, Btn, CellText, DataState, EmptyState, EntityChip, humanRelation, MutationError, Notice, Page, PageHeader, Pill, TextField, ViewBar } from "../ui";
import { fmt, get, send } from "../api";
import { TypeDialog } from "./TypePicker";
import EntityMiniGraph from "./EntityMiniGraph";
import { ProbeDialog, ProbeMark, useProbes } from "./Probes";
import { ForgetDialog } from "./Forget";

type Other = { uuid: string; name: string; labels: string[] };
type EFact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; created_at: string | null; other: Other; episodes: number };
type EGroup = { relation: string; direction: "out" | "in"; functional: boolean; generic?: boolean; conflict: boolean; current: EFact[]; previous: EFact[] };
type EPage = {
  entity: { uuid: string; name: string; labels: string[]; aliases: string[]; summary: string | null; summary_repeats?: boolean; origin: string };
  read_only: boolean; as_of: string | null;
  facts: { total: number; shown: number; not_yet: number; truncated: boolean };
  groups: EGroup[];
  neighbors: (Other & { facts: number; current: number })[];
  episodes: { total: number; items: { uuid: string; name: string; valid_at: string | null; created_at: string | null; source: string | null }[] };
  stats: Stats;
};
/** The key figures shown in the summary's place when there is no summary to read (issue 208). */
type Stats = { current: number; earlier: number; first: string | null; last: string | null; neighbors_by_type: { type: string; count: number }[]; type_description: string };
const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "?");
const MAX_CHAIN = 3; // «A → B → C» says each value replaced the one before: only for a single-valued relation, or this many values (issue 208)

/** Everything known about one entity and how it changed. Facts are grouped by relation and read as an evolution, oldest
 *  first; earlier values are folded so that an entity with many facts stays readable. The timeline is an ordered list, not a chart. */
export default function EntityPage({ graph, role }: { graph: string; role: string }) {
  const { uuid = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const origin = params.get("origen") ?? "";
  const asOf = params.get("fecha") ?? "";
  const setAsOf = (v: string) => { const p = new URLSearchParams(params); if (v) p.set("fecha", v); else p.delete("fecha"); setParams(p, { replace: true }); };
  const q = useQuery({ queryKey: ["entity", graph, uuid, origin, asOf], queryFn: () => get<EPage>(`entities/${uuid}`, { graph, origin: origin || undefined, as_of: asOf || undefined }) });
  const docs = useQuery({ queryKey: ["entity-docs", graph, uuid], enabled: !origin, staleTime: 60_000,
    queryFn: () => get<{ documents: { document_id: number; title: string; snippet: string; chunks: number }[] }>("docs/mentions", { graph, entity: uuid }) });
  return (
    <Page>
      <DataState query={q}>{(d) => <EntityBody d={d} graph={graph} role={role} asOf={asOf} setAsOf={setAsOf} origin={origin} docs={docs.data?.documents ?? []} />}</DataState>
    </Page>
  );
}

function EntityBody({ d, graph, role, asOf, setAsOf, origin, docs }: { d: EPage; graph: string; role: string; asOf: string; setAsOf: (v: string) => void; origin: string;
  docs: { document_id: number; title: string; snippet: string; chunks: number }[] }) {
  const { t } = useTranslation();
  const e = d.entity;
  const isCurator = ["curator", "admin", "owner"].includes(role) && !d.read_only;
  const canEdit = isCurator && !asOf;  // looking at a past day is for reading: invalidating from there would be confusing
  const link = (o: Other) => `/entidad/${o.uuid}${origin ? `?origen=${origin}` : ""}`;
  const [showOther, setShowOther] = useState(false);
  const specific = d.groups.filter((g) => !g.generic);
  const other = d.groups.filter((g) => g.generic);
  const otherFacts = other.reduce((n, g) => n + g.current.length + g.previous.length, 0);
  const qc = useQueryClient();
  const [retyping, setRetyping] = useState(false);
  const [done, setDone] = useState<{ op: number; summary: string } | null>(null);
  const refresh = () => ["entity", "graph", "vocab-types", "retype"].forEach((k) => qc.invalidateQueries({ queryKey: [k, graph] }));
  const retype = useMutation({ mutationFn: (type: string) => send<{ op: number; summary: string }>("PUT", `entities/${e.uuid}/type`, { type }, { graph }),
    onSuccess: (r) => { setRetyping(false); setDone(r); refresh(); } });
  const undo = useMutation({ mutationFn: (id: number) => send("POST", `vocab/ops/${id}/revert`, undefined, { graph }), onSuccess: () => { setDone(null); refresh(); } });
  const [fullSummary, setFullSummary] = useState(false);
  const [forgetting, setForgetting] = useState(false);
  const summary = e.summary && !e.summary_repeats ? e.summary : "";  // a summary that only repeats the facts is not shown (issue 194)
  return (<>
    <PageHeader title={e.name} meta={<>
      {/* the type is the same chip, with its colour, as in the facts below (issue 208); curators change it with the pencil */}
      {(e.labels.length ? e.labels : [""]).map((l) => <EntityChip key={l || "-"} name={l || t("(sin tipo)")} type={l || null} />)}
      {canEdit && <Btn size="row" kind="ghost" icon="edit" title={t("Cambiar tipo")} aria-label={t("Cambiar tipo")} onClick={() => { retype.reset(); setRetyping(true); }} />}
      {e.aliases.map((a) => <Pill key={a} title={t("También se llama así (un nombre fusionado en esta entidad)")}>{a}</Pill>)}
      {e.origin && <Pill tone="alt">{t("de «{{origin}}»", { origin: e.origin })}</Pill>}
    </>} />
    {/* the way back and the day to read stay at the top (issue 200) */}
    <ViewBar title={e.name}>
      <Btn kind="link" component={Link} to="/hechos">{t("← Hechos")}</Btn>
      <TextField type="date" label={t("Cómo estaba el día")} value={asOf} onChange={(ev) => setAsOf(ev.currentTarget.value)} />
      {asOf && <Btn kind="ghost" onClick={() => setAsOf("")}>{t("Hoy")}</Btn>}
    </ViewBar>
    {done && <Notice tone="success">{done.summary}. <Btn kind="link" loading={undo.isPending} onClick={() => undo.mutate(done.op)}>{t("Deshacer")}</Btn></Notice>}
    <MutationError error={undo.error} />
    {d.read_only && <Notice title={t("Solo lectura")}>{t("Entidad prestada por «{{origin}}»: solo lectura.", { origin: e.origin })}</Notice>}
    {asOf && <Notice title={t("Cómo estaba el día")}>{t("Lo vigente el {{date}}, según las fechas de validez.", { date: asOf })}{d.facts.not_yet ? " " + t("{{count}} hechos aún no eran ciertos ese día y no se muestran.", { count: d.facts.not_yet }) : ""}</Notice>}
    {d.facts.truncated && <Notice tone="warn">{t("Se muestran los {{shown}} hechos más recientes de {{total}}.", { shown: d.facts.shown, total: d.facts.total })}</Notice>}
    {/* the essentials side by side: the summary (or the key figures) on the left, the graph of its neighbours on the right */}
    <div className="ms-entity-card">
      <div className="ms-entity-card-graph">
        <EntityMiniGraph entity={e} groups={d.groups} neighbors={d.neighbors} link={link} expand={origin ? undefined : `/grafo?nodo=${e.uuid}`} />
      </div>
      <div className="ms-entity-card-summary">
        <Block title={t("Resumen de la entidad")}>
          {summary ? <Stack gap={2}>
            <Text size="sm" className="ms-prose" lineClamp={fullSummary ? undefined : 6}>{summary}</Text>
            {summary.length > 300 && <Group><Btn kind="link" aria-expanded={fullSummary} onClick={() => setFullSummary((x) => !x)}>{fullSummary ? t("Ver menos") : t("Ver más")}</Btn></Group>}
          </Stack> : <KeyFigures d={d} graph={graph} canPropose={isCurator && !origin} />}
        </Block>
      </div>
    </div>
    <TypeDialog graph={graph} opened={retyping} name={e.name} current={e.labels} onClose={() => setRetyping(false)} onPick={(type) => retype.mutate(type)}
      pending={retype.isPending} error={retype.error} />
    {/* the facts on the left and what mentions the entity on the right, about 70 / 30; one column on a phone. Each column is a stack of
        blocks; the relation groups inside «Facts» are blocks too, each with its timeline */}
    <div className="ms-entity-cols">
      <div>
        <Block title={d.stats.earlier ? t("Hechos ({{current}} vigentes, {{earlier}} anteriores)", { current: d.stats.current, earlier: d.stats.earlier }) : t("Hechos")}
          count={d.stats.earlier ? undefined : d.stats.current}>
          {d.groups.length === 0 && <EmptyState>{t("Esta entidad no tiene hechos.")}</EmptyState>}
          {specific.map((g) => <RelationGroup key={`${g.direction}:${g.relation}`} g={g} self={e} graph={graph} canEdit={canEdit} link={link} />)}
        </Block>
        {other.length > 0 && <Block title={t("Otras relaciones")} count={otherFacts}
          help={t("Relaciones genéricas, como RELATES_TO: el extractor las escribe cuando ningún tipo encaja y pueden unir cualquier cosa, así que no se leen como una evolución.")}
          actions={<Btn kind="link" aria-expanded={showOther} onClick={() => setShowOther((x) => !x)}>{showOther ? t("Ocultar") : t("Ver")}</Btn>}>
          {showOther && other.map((g) => <RelationGroup key={`${g.direction}:${g.relation}`} g={g} self={e} graph={graph} canEdit={canEdit} link={link} />)}
        </Block>}
      </div>
      <div>
        <Block title={t("Episodios que la mencionan")} count={d.episodes.total}>
          {d.episodes.total === 0 ? <EmptyState>{t("Ningún episodio la menciona.")}</EmptyState>
            : <ol className="ms-tl ms-tl-list" aria-label={t("Episodios que la mencionan")}>
              {d.episodes.items.map((ep) => (
                <li key={ep.uuid} className="ms-tl-item"><div className="ms-tl-body">
                  <CellText data sub={<>{fmt(ep.valid_at ?? ep.created_at)}{ep.source ? ` · ${ep.source}` : ""}</>}>
                    {origin ? ep.name : <Link to={`/diario?episodio=${ep.uuid}`}>{ep.name}</Link>}
                  </CellText>
                </div></li>))}
            </ol>}
        </Block>
        {!origin && docs.length > 0 && <Block title={t("Documentos que la mencionan")} count={docs.length}>
          <ol className="ms-tl ms-tl-list" aria-label={t("Documentos que la mencionan")}>
            {docs.map((x) => (
              <li key={x.document_id} className="ms-tl-item"><div className="ms-tl-body">
                <CellText sub={<Text inherit lineClamp={2}>…{x.snippet}…</Text>}>
                  <Link to={`/conocimiento?doc=${x.document_id}`}>{x.title}{x.chunks > 1 ? t(" · {{chunks}} pasajes", { chunks: x.chunks }) : ""}</Link>
                </CellText>
              </div></li>))}
          </ol>
        </Block>}
        {isCurator && <Block title={t("Curación")}>
          <Stack gap={4} align="flex-start">
            <Btn kind="link" component={Link} to="/calidad?tab=dup">{t("Fusionar con otra entidad (Calidad del contenido → Duplicados)")}</Btn>
            {["admin", "owner"].includes(role) && <Btn kind="link" component={Link} to="/calidad?tab=corrector">{t("Revisar los tipos dudosos (Calidad del contenido → Tipos dudosos)")}</Btn>}
            <Btn kind="link" component={Link} to="/hechos">{t("Editar el texto de un hecho (Hechos)")}</Btn>
            {role === "owner" && !origin && <Btn kind="link" onClick={() => setForgetting(true)}>{t("Derecho al olvido: ver qué se borraría")}</Btn>}
          </Stack>
        </Block>}
        {forgetting && <ForgetDialog graph={graph} entity={e} onClose={() => setForgetting(false)} />}
      </div>
    </div>
  </>);
}

/** One relation as an evolution, under its heading: the relation as a sentence in the same «subject → relation» order for both
 *  directions (issue 194), with the page's entity on its side; the values on the other side are the timeline below. The current values
 *  show, and the earlier ones are folded under «See earlier (N)». */
function RelationGroup({ g, self, graph, canEdit, link }: { g: EGroup; self: Other; graph: string; canEdit: boolean; link: (o: Other) => string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const values = [...g.current].map((f) => f.other.name);
  const rel = humanRelation(g.relation);
  return (
    <Block title={g.direction === "out" ? `${self.name} → ${rel}` : `${rel} → ${self.name}`} count={g.current.length}
      meta={g.previous.length > 0 && !g.generic && (g.functional || g.previous.length + values.length <= MAX_CHAIN)
        ? [...g.previous.map((f) => f.other.name), ...values].join(" → ") : undefined}
      actions={(g.functional || g.previous.length > 0) && <>
        {g.functional && <Pill>{t("Un solo valor a la vez")}</Pill>}
        {g.previous.length > 0 && <Btn kind="ghost" size="row" onClick={() => setOpen(!open)}>{open ? t("Ocultar anteriores") : t("Ver anteriores ({{count}})", { count: g.previous.length })}</Btn>}
      </>}>
      {g.conflict && <Notice tone="warn">{t("Tiene varios valores vigentes en una relación de un solo valor: posible contradicción.")} <Link to="/calidad?tab=conflicts">{t("Revisar en Contradicciones")}</Link></Notice>}
      {g.current.length === 0 && !open ? <EmptyState>{t("Sin valor vigente.")}</EmptyState>
        : <ol className="ms-tl ms-tl-list" aria-label={t("Evolución de {{relation}}", { relation: g.relation })}>
          {open && g.previous.map((f) => <FactItem key={f.uuid} f={f} graph={graph} canEdit={canEdit} link={link} />)}
          {g.current.map((f) => <FactItem key={f.uuid} f={f} graph={graph} canEdit={canEdit} link={link} />)}
        </ol>}
    </Block>
  );
}

function FactItem({ f, graph, canEdit, link }: { f: EFact; graph: string; canEdit: boolean; link: (o: Other) => string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const old = f.status === "invalidated";
  const act = useMutation({ mutationFn: () => send("POST", `facts/${f.uuid}/${old ? "reactivate" : "invalidate"}`, undefined, { graph }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["entity", graph] }) });
  const probe = useProbes(graph, canEdit).get(f.uuid);   // a check against a live system (issue 293)
  const [probing, setProbing] = useState(false);
  return (
    <li className="ms-tl-item" data-event={old ? "invalidated" : "learned"}>
      <div className="ms-tl-row">
        <div className="ms-tl-body">
          <CellText sub={<>
            {old ? t("Válido {{from}} → {{to}}", { from: day(f.valid_at ?? f.created_at), to: day(f.invalid_at) }) : t("Vigente desde {{from}}", { from: day(f.valid_at ?? f.created_at) })}
            {" · "}{t("aprendido {{date}}", { date: day(f.created_at) })}
            {probe && !old && <>{" · "}<ProbeMark p={probe} /></>}
          </>}>
            <Group gap={6}><EntityChip name={f.other.name} type={f.other.labels[0]} to={link(f.other)} />
              <Text size="sm" td={old ? "line-through" : undefined} c={old ? "dimmed" : undefined}>{f.fact}</Text></Group>
          </CellText>
          <MutationError error={act.error} />
        </div>
        {canEdit && <Group gap={6} wrap="nowrap">
          {!old && <Btn size="row" icon="test" onClick={() => setProbing(true)}>{probe ? t("Sonda") : t("Poner sonda")}</Btn>}
          <Btn size="row" icon={old ? "undo" : "close"} loading={act.isPending} onClick={() => act.mutate()}>{old ? t("Reactivar") : t("Invalidar")}</Btn>
        </Group>}
      </div>
      {probing && <ProbeDialog graph={graph} fact={f} probe={probe} onClose={() => setProbing(false)} />}
    </li>
  );
}

/** What fills the summary's place when there is no summary to read (issue 208): why, a way for a curator to have one written, and the key
 *  figures of the entity (its facts, episodes, dates, neighbours by type and what its type means in the ontology). */
function KeyFigures({ d, graph, canPropose }: { d: EPage; graph: string; canPropose: boolean }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const e = d.entity; const s = d.stats;
  const [kept, setKept] = useState(false);
  const propose = useMutation({ mutationFn: () => send<{ item: { status: string } }>("POST", `brains/${graph}/summaries/entity/${e.uuid}`),
    onSuccess: (r) => { if (r.item.status === "same") setKept(true); else nav("/calidad?tab=summaries"); } });
  return (
    <Stack gap={6}>
      <EmptyState action={canPropose && <Btn size="row" icon="edit" loading={propose.isPending} onClick={() => propose.mutate()}>{e.summary ? t("Proponer un resumen mejor") : t("Proponer un resumen")}</Btn>}>
        {e.summary ? t("El resumen solo repite los hechos, que están más abajo.") : t("Esta entidad aún no tiene resumen.")}
      </EmptyState>
      {kept && <Notice tone="success">{t("El motor ha dejado el resumen como estaba.")}</Notice>}
      <MutationError error={propose.error} />
      {s.type_description && <Text size="sm">{s.type_description}</Text>}
      <Text size="sm">{t("{{current}} hechos vigentes · {{earlier}} anteriores · {{episodes}} episodios", { current: s.current, earlier: s.earlier, episodes: d.episodes.total })}</Text>
      {s.first && <Text size="sm" c="dimmed">{s.first.slice(0, 10) === s.last?.slice(0, 10) ? t("El {{date}}", { date: day(s.first) }) : t("Del {{first}} al {{last}}", { first: day(s.first), last: day(s.last) })}</Text>}
      {s.neighbors_by_type.length > 0 && <Group gap={6} aria-label={t("Entidades relacionadas por tipo")}>
        {s.neighbors_by_type.map((n) => <EntityChip key={n.type || "-"} name={`${n.type || t("(sin tipo)")} · ${n.count}`} type={n.type || null} />)}
      </Group>}
    </Stack>
  );
}
