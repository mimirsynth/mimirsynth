import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Btn, DataState, EmptyState, EntityChip, FillArea, MutationError, Notice, Page, PageHeader, Panel, Pill, TextField } from "../ui";
import { fmt, get, send } from "../api";
import { TypeDialog } from "./TypePicker";
import EntityMiniGraph, { humanRelation } from "./EntityMiniGraph";

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
/** The key figures of the top card, shown when there is no summary to read (issue 208). */
type Stats = { current: number; earlier: number; first: string | null; last: string | null; neighbors_by_type: { type: string; count: number }[]; type_description: string };
const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "?");
const MAX_HEAD = 3;  // values named in a group's heading; the rest are counted
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
  const summary = e.summary && !e.summary_repeats ? e.summary : "";  // a summary that only repeats the facts is not shown (issue 194)
  return (<>
    {/* the way back and the day to read stay at the top (issue 200) */}
    <Group justify="space-between" align="flex-end">
      <Btn kind="link" component={Link} to="/hechos">{t("← Hechos")}</Btn>
      <Group gap="xs" align="flex-end">
        <TextField type="date" label={t("Cómo estaba el día")} value={asOf} onChange={(ev) => setAsOf(ev.currentTarget.value)} w={170} />
        {asOf && <Btn kind="ghost" onClick={() => setAsOf("")}>{t("Hoy")}</Btn>}
      </Group>
    </Group>
    <FillArea><Stack gap="sm">
      {/* the essentials in one card: the name, its type and other names, and the summary on the left; the graph on the right */}
      <Panel withBorder p="md" className="ms-entity-card">
        <div className="ms-entity-card-head">
          <PageHeader title={e.name} meta={<>
            {/* the type is the same chip, with its colour, as in the facts below (issue 208); curators change it with the pencil */}
            {(e.labels.length ? e.labels : [""]).map((l) => <EntityChip key={l || "-"} name={l || t("(sin tipo)")} type={l || null} />)}
            {canEdit && <Btn size="row" kind="ghost" icon="edit" title={t("Cambiar tipo")} aria-label={t("Cambiar tipo")} onClick={() => { retype.reset(); setRetyping(true); }} />}
            {e.aliases.map((a) => <Pill key={a} size="xs" title={t("También se llama así (un nombre fusionado en esta entidad)")}>{a}</Pill>)}
            {e.origin && <Pill size="xs" tone="alt">{t("de «{{origin}}»", { origin: e.origin })}</Pill>}
          </>} />
        </div>
        <div className="ms-entity-card-graph">
          <EntityMiniGraph entity={e} groups={d.groups} neighbors={d.neighbors} link={link} expand={origin ? undefined : `/grafo?nodo=${e.uuid}`} />
        </div>
        {summary ? <Stack gap={2} className="ms-entity-card-summary">
          <Text size="sm" className="ms-prose" lineClamp={fullSummary ? undefined : 6}>{summary}</Text>
          {summary.length > 300 && <Group><Btn kind="link" aria-expanded={fullSummary} onClick={() => setFullSummary((x) => !x)}>{fullSummary ? t("Ver menos") : t("Ver más")}</Btn></Group>}
        </Stack> : <KeyFigures d={d} graph={graph} canPropose={isCurator && !origin} />}
      </Panel>
      {done && <Notice tone="success">{done.summary}. <Btn kind="link" loading={undo.isPending} onClick={() => undo.mutate(done.op)}>{t("Deshacer")}</Btn></Notice>}
      <MutationError error={undo.error} />
      <TypeDialog graph={graph} opened={retyping} name={e.name} current={e.labels} onClose={() => setRetyping(false)} onPick={(type) => retype.mutate(type)}
        pending={retype.isPending} error={retype.error} />
      {d.read_only && <Notice>{t("Entidad prestada por «{{origin}}»: solo lectura.", { origin: e.origin })}</Notice>}
      {asOf && <Notice>{t("Lo vigente el {{date}}, según las fechas de validez.", { date: asOf })}{d.facts.not_yet ? " " + t("{{count}} hechos aún no eran ciertos ese día y no se muestran.", { count: d.facts.not_yet }) : ""}</Notice>}
      {d.facts.truncated && <Notice tone="warn">{t("Se muestran los {{shown}} hechos más recientes de {{total}}.", { shown: d.facts.shown, total: d.facts.total })}</Notice>}
      {/* the facts on the left and what mentions the entity on the right, about 70 / 30; one column on a phone */}
      <div className="ms-entity-cols">
        <Stack gap="sm">
          <Text size="sm" fw={700}>{d.stats.earlier ? t("Hechos ({{current}} vigentes, {{earlier}} anteriores)", { current: d.stats.current, earlier: d.stats.earlier })
            : t("Hechos ({{count}})", { count: d.stats.current })}</Text>
          {d.groups.length === 0 && <EmptyState>{t("Esta entidad no tiene hechos.")}</EmptyState>}
          {specific.map((g) => <RelationGroup key={`${g.direction}:${g.relation}`} g={g} self={e} graph={graph} canEdit={canEdit} link={link} />)}
          {other.length > 0 && <Stack gap="xs">
            <Group gap="xs">
              <Text size="sm" fw={700}>{t("Otras relaciones ({{count}} hechos)", { count: otherFacts })}</Text>
              <Btn kind="link" aria-expanded={showOther} onClick={() => setShowOther((x) => !x)}>{showOther ? t("Ocultar") : t("Ver")}</Btn>
            </Group>
            <Text size="xs" c="dimmed">{t("Relaciones genéricas, como RELATES_TO: el extractor las escribe cuando ningún tipo encaja y pueden unir cualquier cosa, así que no se leen como una evolución.")}</Text>
            {showOther && other.map((g) => <RelationGroup key={`${g.direction}:${g.relation}`} g={g} self={e} graph={graph} canEdit={canEdit} link={link} />)}
          </Stack>}
        </Stack>
        <Panel withBorder p="sm"><Stack gap="sm">
          <Text size="sm" fw={700}>{t("Episodios que la mencionan ({{count}})", { count: d.episodes.total })}</Text>
          {d.episodes.total === 0 && <Text size="xs" c="dimmed">{t("Ningún episodio la menciona.")}</Text>}
          {d.episodes.items.length > 0 && <ol className="ms-tl ms-tl-list" aria-label={t("Episodios que la mencionan")}>
            {d.episodes.items.map((ep) => (
              <li key={ep.uuid} className="ms-tl-item"><Stack gap={0} className="ms-tl-body">
                {origin ? <Text size="sm">{ep.name}</Text> : <Text size="sm" component={Link} to={`/diario?episodio=${ep.uuid}`}>{ep.name}</Text>}
                <Text size="xs" c="dimmed">{fmt(ep.valid_at ?? ep.created_at)}{ep.source ? ` · ${ep.source}` : ""}</Text>
              </Stack></li>))}
          </ol>}
          {!origin && docs.length > 0 && <>
            <Text size="sm" fw={700}>{t("Documentos que la mencionan ({{count}})", { count: docs.length })}</Text>
            <ol className="ms-tl ms-tl-list" aria-label={t("Documentos que la mencionan")}>
              {docs.map((x) => (
                <li key={x.document_id} className="ms-tl-item"><Stack gap={0} className="ms-tl-body">
                  <Text size="sm" component={Link} to={`/conocimiento?doc=${x.document_id}`}>{x.title}{x.chunks > 1 ? t(" · {{chunks}} pasajes", { chunks: x.chunks }) : ""}</Text>
                  <Text size="xs" c="dimmed" lineClamp={2}>…{x.snippet}…</Text>
                </Stack></li>))}
            </ol>
          </>}
          {isCurator && <>
            <Text size="sm" fw={700}>{t("Curación")}</Text>
            <Text size="xs" component={Link} to="/calidad?tab=dup">{t("Fusionar con otra entidad (Calidad del contenido → Duplicados)")}</Text>
            {["admin", "owner"].includes(role) && <Text size="xs" component={Link} to="/calidad?tab=corrector">{t("Revisar los tipos dudosos (Calidad del contenido → Tipos dudosos)")}</Text>}
            <Text size="xs" component={Link} to="/hechos">{t("Editar el texto de un hecho (Hechos)")}</Text>
          </>}
        </Stack></Panel>
      </div>
    </Stack></FillArea>
  </>);
}

/** One relation as an evolution: the current values, and the earlier ones folded under «N anteriores». */
/** The heading of a relation, as a sentence in the same «subject → relation → object» order for both directions (issue 194): the page's
 *  entity is plain text, on its side, and the current values on the other side are links. */
function RelationHead({ g, self, link }: { g: EGroup; self: Other; link: (o: Other) => string }) {
  const { t } = useTranslation();
  const others = [...new Map(g.current.map((f) => [f.other.uuid, f.other])).values()];
  const shown = others.slice(0, MAX_HEAD);
  const side = others.length ? <>{shown.map((o, i) => <span key={o.uuid}>{i > 0 && " "}<EntityChip name={o.name} type={o.labels[0]} to={link(o)} /></span>)}
    {others.length > MAX_HEAD && ` ${t("y {{count}} más", { count: others.length - MAX_HEAD })}`}</> : <span>—</span>;
  const me = <EntityChip name={self.name} type={self.labels[0]} current />;  // the page's own entity: not a link
  const rel = <span className="ms-relhead-rel" title={g.relation}>{humanRelation(g.relation)}</span>;
  return <Text size="sm" className="ms-relhead">{g.direction === "out" ? <>{me} → {rel} → {side}</> : <>{side} → {rel} → {me}</>}</Text>;
}

function RelationGroup({ g, self, graph, canEdit, link }: { g: EGroup; self: Other; graph: string; canEdit: boolean; link: (o: Other) => string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const values = [...g.current].map((f) => f.other.name);
  return (
    <Panel withBorder p="sm"><Stack gap="xs">
      <Group gap="xs" justify="space-between">
        <Group gap="xs">
          <RelationHead g={g} self={self} link={link} />
          {g.functional && <Pill size="xs">{t("Un solo valor a la vez")}</Pill>}
          {g.previous.length > 0 && !g.generic && (g.functional || g.previous.length + values.length <= MAX_CHAIN)
            && <Text size="xs" c="dimmed">{[...g.previous.map((f) => f.other.name), ...values].join(" → ")}</Text>}
        </Group>
        {g.previous.length > 0 && <Btn kind="ghost" size="row" onClick={() => setOpen(!open)}>{open ? t("Ocultar anteriores") : t("Ver anteriores ({{count}})", { count: g.previous.length })}</Btn>}
      </Group>
      {g.conflict && <Notice tone="warn">{t("Tiene varios valores vigentes en una relación de un solo valor: posible contradicción.")} <Link to="/calidad?tab=conflicts">{t("Revisar en Contradicciones")}</Link></Notice>}
      {g.current.length === 0 && !open && <Text size="xs" c="dimmed">{t("Sin valor vigente.")}</Text>}
      <ol className="ms-tl ms-tl-list" aria-label={t("Evolución de {{relation}}", { relation: g.relation })}>
        {open && g.previous.map((f) => <FactItem key={f.uuid} f={f} graph={graph} canEdit={canEdit} link={link} />)}
        {g.current.map((f) => <FactItem key={f.uuid} f={f} graph={graph} canEdit={canEdit} link={link} />)}
      </ol>
    </Stack></Panel>
  );
}

function FactItem({ f, graph, canEdit, link }: { f: EFact; graph: string; canEdit: boolean; link: (o: Other) => string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const old = f.status === "invalidated";
  const act = useMutation({ mutationFn: () => send("POST", `facts/${f.uuid}/${old ? "reactivate" : "invalidate"}`, undefined, { graph }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["entity", graph] }) });
  return (
    <li className="ms-tl-item" data-event={old ? "invalidated" : "learned"}>
      <Group gap="xs" justify="space-between" wrap="nowrap" align="flex-start">
        <Stack gap={0} className="ms-tl-body">
          <Group gap={6}><EntityChip name={f.other.name} type={f.other.labels[0]} to={link(f.other)} />
            <Text size="sm" td={old ? "line-through" : undefined} c={old ? "dimmed" : undefined}>{f.fact}</Text></Group>
          <Text size="xs" c="dimmed">
            {old ? t("Válido {{from}} → {{to}}", { from: day(f.valid_at ?? f.created_at), to: day(f.invalid_at) }) : t("Vigente desde {{from}}", { from: day(f.valid_at ?? f.created_at) })}
            {" · "}{t("aprendido {{date}}", { date: day(f.created_at) })}
          </Text>
          <MutationError error={act.error} />
        </Stack>
        {canEdit && <Btn size="row" icon={old ? "undo" : "close"} loading={act.isPending} onClick={() => act.mutate()}>{old ? t("Reactivar") : t("Invalidar")}</Btn>}
      </Group>
    </li>
  );
}

/** What fills the left half of the card when there is no summary to read (issue 208): why, a way for a curator to have one written, and
 *  the key figures of the entity (its facts, episodes, dates, neighbours by type and what its type means in the ontology). */
function KeyFigures({ d, graph, canPropose }: { d: EPage; graph: string; canPropose: boolean }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const e = d.entity; const s = d.stats;
  const [kept, setKept] = useState(false);
  const propose = useMutation({ mutationFn: () => send<{ item: { status: string } }>("POST", `brains/${graph}/summaries/entity/${e.uuid}`),
    onSuccess: (r) => { if (r.item.status === "same") setKept(true); else nav("/calidad?tab=summaries"); } });
  return (
    <Stack gap={6} className="ms-entity-card-summary">
      <Text size="xs" c="dimmed">{e.summary ? t("El resumen solo repite los hechos, que están más abajo.") : t("Esta entidad aún no tiene resumen.")}</Text>
      {canPropose && <Group gap="xs">
        <Btn size="row" icon="edit" loading={propose.isPending} onClick={() => propose.mutate()}>{e.summary ? t("Proponer un resumen mejor") : t("Proponer un resumen")}</Btn>
        {kept && <Text size="xs" c="dimmed">{t("El motor ha dejado el resumen como estaba.")}</Text>}
      </Group>}
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
