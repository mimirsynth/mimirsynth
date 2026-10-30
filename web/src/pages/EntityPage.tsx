import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Btn, DataState, EmptyState, FillArea, MutationError, Notice, Page, PageHeader, Panel, Pill, SplitView, TextField } from "../ui";
import { fmt, get, send } from "../api";

type Other = { uuid: string; name: string; labels: string[] };
type EFact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; created_at: string | null; other: Other; episodes: number };
type EGroup = { relation: string; direction: "out" | "in"; functional: boolean; generic?: boolean; conflict: boolean; current: EFact[]; previous: EFact[] };
type EPage = {
  entity: { uuid: string; name: string; labels: string[]; aliases: string[]; summary: string | null; origin: string };
  read_only: boolean; as_of: string | null;
  facts: { total: number; shown: number; not_yet: number; truncated: boolean };
  groups: EGroup[];
  neighbors: (Other & { facts: number; current: number })[];
  episodes: { total: number; items: { uuid: string; name: string; valid_at: string | null; created_at: string | null; source: string | null }[] };
};
const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "?");

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
  return (<>
    <PageHeader title={e.name} actions={<Group gap="xs" align="flex-end">
      <TextField type="date" label={t("Cómo estaba el día")} value={asOf} onChange={(ev) => setAsOf(ev.currentTarget.value)} w={170} />
      {asOf && <Btn kind="ghost" onClick={() => setAsOf("")}>{t("Hoy")}</Btn>}
      {!origin && <Btn kind="secondary" icon="graph" component={Link} to={`/grafo?nodo=${e.uuid}`}>{t("Ver en el grafo")}</Btn>}
    </Group>} />
    {/* type, merged names and summary go under the title, not in its description: that one is a paragraph and these are blocks */}
    <Stack gap={4}>
      <Group gap={4}>{(e.labels.length ? e.labels : [t("(sin tipo)")]).map((l) => <Pill key={l} size="xs">{l}</Pill>)}
        {e.aliases.length > 0 && <Text size="xs" c="dimmed">{t("También: {{names}}", { names: e.aliases.join(", ") })}</Text>}
        {e.origin && <Pill size="xs" tone="alt">{t("de «{{origin}}»", { origin: e.origin })}</Pill>}</Group>
      {e.summary && <Text size="sm" className="ms-prose">{e.summary}</Text>}
    </Stack>
    {d.read_only &&<Notice>{t("Entidad prestada por «{{origin}}»: solo lectura.", { origin: e.origin })}</Notice>}
    {asOf && <Notice>{t("Lo vigente el {{date}}, según las fechas de validez.", { date: asOf })}{d.facts.not_yet ? " " + t("{{count}} hechos aún no eran ciertos ese día y no se muestran.", { count: d.facts.not_yet }) : ""}</Notice>}
    {d.facts.truncated && <Notice tone="warn">{t("Se muestran los {{shown}} hechos más recientes de {{total}}.", { shown: d.facts.shown, total: d.facts.total })}</Notice>}
    <SplitView main={<FillArea><Stack gap="sm">
      {d.groups.length === 0 && <EmptyState>{t("Esta entidad no tiene hechos.")}</EmptyState>}
      {specific.map((g) => <RelationGroup key={`${g.direction}:${g.relation}`} g={g} graph={graph} canEdit={canEdit} link={link} />)}
      {other.length > 0 && <Stack gap="xs">
        <Group gap="xs">
          <Text size="sm" fw={700}>{t("Otras relaciones ({{count}} hechos)", { count: otherFacts })}</Text>
          <Btn kind="link" aria-expanded={showOther} onClick={() => setShowOther((x) => !x)}>{showOther ? t("Ocultar") : t("Ver")}</Btn>
        </Group>
        <Text size="xs" c="dimmed">{t("Relaciones genéricas, como RELATES_TO: el extractor las escribe cuando ningún tipo encaja y pueden unir cualquier cosa, así que no se leen como una evolución.")}</Text>
        {showOther && other.map((g) => <RelationGroup key={`${g.direction}:${g.relation}`} g={g} graph={graph} canEdit={canEdit} link={link} />)}
      </Stack>}
    </Stack></FillArea>} aside={<Panel withBorder p="sm" h="100%"><FillArea><Stack gap="sm">
      <Text size="sm" fw={700}>{t("Relacionadas ({{count}})", { count: d.neighbors.length })}</Text>
      <Group gap={4}>{d.neighbors.slice(0, 40).map((n) => (
        <Link key={n.uuid} to={link(n)} className="ms-nolink"><Pill size="xs">{n.name}</Pill></Link>))}</Group>
      {d.episodes.total > 0 && <Text size="sm" fw={700}>{t("Episodios que la mencionan ({{count}})", { count: d.episodes.total })}</Text>}
      {d.episodes.items.map((ep) => (
        <Stack key={ep.uuid} gap={0}>
          {origin ? <Text size="xs">{ep.name}</Text> : <Text size="xs" component={Link} to={`/diario?episodio=${ep.uuid}`}>{ep.name}</Text>}
          <Text size="xs" c="dimmed">{fmt(ep.valid_at ?? ep.created_at)}{ep.source ? ` · ${ep.source}` : ""}</Text>
        </Stack>))}
      {!origin && docs.length > 0 && <>
        <Text size="sm" fw={700}>{t("Documentos que la mencionan ({{count}})", { count: docs.length })}</Text>
        {docs.map((x) => (
          <Stack key={x.document_id} gap={0}>
            <Text size="xs" component={Link} to={`/conocimiento?doc=${x.document_id}`}>{x.title}{x.chunks > 1 ? t(" · {{chunks}} pasajes", { chunks: x.chunks }) : ""}</Text>
            <Text size="xs" c="dimmed" lineClamp={2}>…{x.snippet}…</Text>
          </Stack>))}
      </>}
      {isCurator && <>
        <Text size="sm" fw={700}>{t("Curación")}</Text>
        <Text size="xs" component={Link} to="/vocabulario?tab=dup">{t("Fusionar con otra entidad (Vocabulario → Duplicados)")}</Text>
        {["admin", "owner"].includes(role) && <Text size="xs" component={Link} to="/vocabulario?tab=corrector">{t("Cambiar el tipo (Vocabulario → Corrector de tipos)")}</Text>}
        <Text size="xs" component={Link} to="/hechos">{t("Editar el texto de un hecho (Hechos)")}</Text>
      </>}
    </Stack></FillArea></Panel>} />
  </>);
}

/** One relation as an evolution: the current values, and the earlier ones folded under «N anteriores». */
function RelationGroup({ g, graph, canEdit, link }: { g: EGroup; graph: string; canEdit: boolean; link: (o: Other) => string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const values = [...g.current].map((f) => f.other.name);
  return (
    <Panel withBorder p="sm"><Stack gap="xs">
      <Group gap="xs" justify="space-between">
        <Group gap="xs">
          <Text size="sm" fw={700} className="ms-data">{g.direction === "out" ? `${g.relation} →` : `← ${g.relation}`}</Text>
          {g.functional && <Pill size="xs">{t("Un solo valor a la vez")}</Pill>}
          {g.previous.length > 0 && !g.generic && <Text size="xs" c="dimmed">{[...g.previous.map((f) => f.other.name), ...values].join(" → ")}</Text>}
        </Group>
        {g.previous.length > 0 && <Btn kind="ghost" size="row" onClick={() => setOpen(!open)}>{open ? t("Ocultar anteriores") : t("Ver anteriores ({{count}})", { count: g.previous.length })}</Btn>}
      </Group>
      {g.conflict && <Notice tone="warn">{t("Tiene varios valores vigentes en una relación de un solo valor: posible contradicción.")} <Link to="/vocabulario?tab=conflicts">{t("Revisar en Contradicciones")}</Link></Notice>}
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
      <Group gap="xs" justify="space-between">
        <Stack gap={0}>
          <Group gap={6}><Link to={link(f.other)} className="ms-nolink"><Pill size="xs">{f.other.name}</Pill></Link>
            <Text size="sm" td={old ? "line-through" : undefined} c={old ? "dimmed" : undefined}>{f.fact}</Text></Group>
          <Text size="xs" c="dimmed">
            {old ? t("Válido {{from}} → {{to}}", { from: day(f.valid_at ?? f.created_at), to: day(f.invalid_at) }) : t("Vigente desde {{from}}", { from: day(f.valid_at ?? f.created_at) })}
            {" · "}{t("aprendido {{date}}", { date: day(f.created_at) })}
          </Text>
          <MutationError error={act.error} />
        </Stack>
        {canEdit && <Btn size="row" kind="ghost" loading={act.isPending} onClick={() => act.mutate()}>{old ? t("Reactivar") : t("Invalidar")}</Btn>}
      </Group>
    </li>
  );
}
