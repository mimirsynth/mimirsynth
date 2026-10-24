import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, ClearFilters, ColHead, ComboField, DataTable, FillArea, Modal, Notice, Page, Panel, Pill, StatCard, Tabs, Toggle, useTableView, MutationError, ConfirmDialog, DataState, EmptyState, PageHeader, useTabParam, StatGrid } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import Retype from "./Retype";
import VocabOntology from "./VocabOntology";
import VocabTypes from "./VocabTypes";
import VocabDuplicates from "./VocabDuplicates";

type Rel = { name: string; facts: number; generic: boolean; variants: { raw: string; facts: number }[] };
type Dup = { key: string; members: { uuid: string; name: string; labels: string[]; degree: number }[] };
type Vocab = {
  summary: Record<string, number>; ignored_duplicates?: string[]; relations: Rel[]; labels: { label: string; count: number }[]; duplicates: Dup[];
};
type Alias = { id: number; alias: string; canonical: string };

type RelRow = { name: string; facts: number; generic?: boolean; variants: { raw: string; facts: number }[] };
const REL_COLS = { name: { get: (r: RelRow) => r.name }, facts: { get: (r: RelRow) => r.facts }, variants: { get: (r: RelRow) => r.variants.map((v) => v.raw).join(" ") } };
function RelationsTable({ rows, isAdmin, onUnify }: { rows: RelRow[]; isAdmin: boolean; onUnify: (name: string) => void }) {
  const v = useTableView(rows, REL_COLS, { key: "facts", dir: "desc" });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <FillArea><DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>Relación (normalizada)</ColHead>
          <ColHead sort={v.sortProps("facts")}>Hechos</ColHead>
          <ColHead filter={v.text("variants", "Variante cruda…")}>Variantes crudas</ColHead>
          {isAdmin && <DataTable.Th />}
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((r) => (
          <DataTable.Tr key={r.name}>
            <DataTable.Td><Group gap={6}><Text fw={500}>{r.name}</Text>{r.generic && <Pill size="xs" tone="warn">genérica</Pill>}</Group></DataTable.Td>
            <DataTable.Td>{r.facts}</DataTable.Td>
            <DataTable.Td>{r.variants.length > 1 ? r.variants.map((x) => `${x.raw} (${x.facts})`).join(" · ") : <Text span c="dimmed">—</Text>}</DataTable.Td>
            {isAdmin && <DataTable.Td><Btn size="row" icon="refresh" onClick={() => onUnify(r.name)}>Unificar con…</Btn></DataTable.Td>}
          </DataTable.Tr>))}</DataTable.Tbody></DataTable></FillArea>
    </Stack>
  );
}

function AliasesTable({ rows, isAdmin, onDelete }: { rows: Alias[]; isAdmin: boolean; onDelete: (a: Alias) => void }) {
  const v = useTableView(rows, { alias: { get: (a: Alias) => a.alias }, canonical: { get: (a: Alias) => a.canonical } }, { key: "alias", dir: "asc" });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm" w={560}><DataTable.Thead><DataTable.Tr>
        <ColHead sort={v.sortProps("alias")} filter={v.text("alias")}>Alias</ColHead>
        <ColHead sort={v.sortProps("canonical")} filter={v.text("canonical")}>Se lee como</ColHead>
        {isAdmin && <DataTable.Th />}</DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a) => (
          <DataTable.Tr key={a.id}><DataTable.Td>{a.alias}</DataTable.Td><DataTable.Td>{a.canonical}</DataTable.Td>
            {isAdmin && <DataTable.Td><Btn kind="danger" size="row" icon="trash" onClick={() => onDelete(a)}>Quitar</Btn></DataTable.Td>}</DataTable.Tr>))}</DataTable.Tbody></DataTable>
    </Stack>
  );
}

export default function Vocabulary({ graph, role }: { graph: string; role: string }) {
  const isAdmin = ["admin", "owner"].includes(role);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["vocab", graph], queryFn: () => get<Vocab>("vocabulary", { graph }) });
  const data = q.data;
  const { data: aliases = [] } = useQuery({ queryKey: ["vocab-aliases", graph], queryFn: () => get<Alias[]>("vocab/aliases", { graph }) });
  const [tab, setTab] = useTabParam("rel");
  const [tail, setTail] = useState(false);
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [delAlias, setDelAlias] = useState<Alias | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["vocab", graph] }); qc.invalidateQueries({ queryKey: ["vocab-aliases", graph] }); };
  const add = useMutation({ mutationFn: () => send("POST", `vocab/aliases`, { alias: from, canonical: to }, { graph }), onSuccess: () => { setFrom(null); setTo(""); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `vocab/aliases/${id}`, undefined, { graph }), onSuccess: refresh });
  if (!data) return <DataState query={q} />;
  const s = data.summary;
  const rels = data.relations.filter((r) => !tail || r.facts <= 2);
  return (
    <Page>
      <PageHeader title="Vocabulario" description={<>Qué tipos de relación y de entidad existen en el grafo, para decidir qué normalizar o fusionar. Unificar una relación con otra es un alias: se aplica al leer y no modifica los datos del grafo (se puede deshacer).</>} />
      <StatGrid>
        <StatCard label="Tipos de relación" value={`${s.relation_types_raw} → ${s.relation_types_canonical}`} hint="crudos → tras normalizar formato" />
        <StatCard label="Hechos genéricos" value={`${s.generic_pct} %`} hint="RELATES_TO, MENTIONED_IN…" />
        <StatCard label="Cola larga" value={s.long_tail_types} hint={`${s.long_tail_facts} hechos en tipos con ≤2 usos`} />
        <StatCard label="Entidades" value={s.entities} />
        <StatCard label="Posibles duplicados" value={s.duplicate_groups} hint="mismo nombre salvo versión/mayúsculas" />
      </StatGrid>
      <Tabs value={tab} onChange={setTab} className="ms-tabs-fill">
        <Tabs.List>
          <Tabs.Tab value="rel">Relaciones ({data.relations.length})</Tabs.Tab>
          <Tabs.Tab value="ent">Tipos de entidad ({data.labels.length})</Tabs.Tab>
          {isAdmin && <Tabs.Tab value="corrector">Corrector de tipos</Tabs.Tab>}
          <Tabs.Tab value="onto">Ontología</Tabs.Tab>
          <Tabs.Tab value="ali">Alias ({aliases.length})</Tabs.Tab>
          <Tabs.Tab value="dup">Duplicados ({data.duplicates.length})</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="rel" pt="sm">
          <Toggle mb="xs" label="Solo cola larga (≤2 hechos)" checked={tail} onChange={(e) => setTail(e.currentTarget.checked)} />
          <RelationsTable rows={rels} isAdmin={isAdmin} onUnify={(n) => { setFrom(n); setTo(""); }} />
        </Tabs.Panel>
        <Tabs.Panel value="ent" pt="sm"><VocabTypes graph={graph} isAdmin={isAdmin} /></Tabs.Panel>
        {isAdmin && <Tabs.Panel value="corrector" pt="sm"><Retype graph={graph} role={role} /></Tabs.Panel>}
        <Tabs.Panel value="onto" pt="sm"><VocabOntology graph={graph} role={role} /></Tabs.Panel>
        <Tabs.Panel value="ali" pt="sm">
          <FillArea>
            {aliases.length === 0 ? <EmptyState>Sin alias. Usa «Unificar con…» en la pestaña Relaciones.</EmptyState> : (
              <AliasesTable rows={aliases} isAdmin={isAdmin} onDelete={setDelAlias} />)}
          </FillArea>
        </Tabs.Panel>
        <Tabs.Panel value="dup" pt="sm"><VocabDuplicates graph={graph} groups={data.duplicates} ignored={data.ignored_duplicates ?? []} isAdmin={isAdmin} /></Tabs.Panel>
      </Tabs>
      <ConfirmDialog opened={!!delAlias} onClose={() => setDelAlias(null)} title="Quitar alias" action="Quitar alias" subject={delAlias && `${delAlias.alias} → ${delAlias.canonical}`}
        warning="La relación vuelve a leerse con su nombre propio. Los hechos del grafo no se modifican." onConfirm={() => del.mutateAsync(delAlias!.id)} />
      <Modal opened={!!from} onClose={() => setFrom(null)} title="Unificar relación" centered>
        <Stack>
          <Text size="sm"><b>{from}</b> se leerá como el nombre que elijas. Los hechos del grafo no se modifican y puedes quitar el alias después.</Text>
          <ComboField label="Se lee como" data={data.relations.map((r) => r.name).filter((n) => n !== from)} limit={50} value={to} onChange={setTo} placeholder="Elige una relación o escribe un nombre nuevo" />
          <MutationError error={add.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setFrom(null)}>Cancelar</Btn><Btn kind="primary" icon="check" disabled={!to.trim()} loading={add.isPending} onClick={() => add.mutate()}>Crear alias</Btn></Group>
        </Stack>
      </Modal>
    </Page>
  );
}
