import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, ClearFilters, ColHead, ComboField, DataTable, FillArea, Modal, Notice, Page, Panel, Pill, StatCard, Tabs, Toggle, useTableView, MutationError, ConfirmDialog, DataState, EmptyState, PageHeader, useTabParam, StatGrid } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { get, send } from "../api";
import VocabOntology from "./VocabOntology";
import VocabTypes from "./VocabTypes";
import { TabIntro } from "./Quality";

/** The tabs that moved to Content quality (issue 164): old links and bookmarks land on the same tool there. */
const MOVED = ["dup", "conflicts", "stale", "corrector"];

type Rel = { name: string; facts: number; generic: boolean; variants: { raw: string; facts: number }[] };
type Vocab = { summary: Record<string, number>; relations: Rel[]; labels: { label: string; count: number }[] };
type Alias = { id: number; alias: string; canonical: string };

type RelRow = { name: string; facts: number; generic?: boolean; variants: { raw: string; facts: number }[] };
const REL_COLS = { name: { get: (r: RelRow) => r.name }, facts: { get: (r: RelRow) => r.facts }, variants: { get: (r: RelRow) => r.variants.map((v) => v.raw).join(" ") } };
function RelationsTable({ rows, isAdmin, onUnify }: { rows: RelRow[]; isAdmin: boolean; onUnify: (name: string) => void }) {
  const { t } = useTranslation();
  const v = useTableView(rows, REL_COLS, { key: "facts", dir: "desc" });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <FillArea><DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Relación (normalizada)")}</ColHead>
          <ColHead sort={v.sortProps("facts")}>{t("Hechos")}</ColHead>
          <ColHead filter={v.text("variants", t("Variante cruda…"))}>{t("Variantes crudas")}</ColHead>
          {isAdmin && <DataTable.ActionsHead />}
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((r) => (
          <DataTable.Tr key={r.name}>
            <DataTable.Td><Group gap={6}><Text fw={500}>{r.name}</Text>{r.generic && <Pill size="xs" tone="warn">{t("genérica")}</Pill>}</Group></DataTable.Td>
            <DataTable.Td>{r.facts}</DataTable.Td>
            <DataTable.Td>{r.variants.length > 1 ? r.variants.map((x) => `${x.raw} (${x.facts})`).join(" · ") : <Text span c="dimmed">—</Text>}</DataTable.Td>
            {isAdmin && <DataTable.Td><Btn size="row" icon="refresh" onClick={() => onUnify(r.name)}>{t("Unificar con…")}</Btn></DataTable.Td>}
          </DataTable.Tr>))}</DataTable.Tbody></DataTable></FillArea>
    </Stack>
  );
}

function AliasesTable({ rows, isAdmin, onDelete }: { rows: Alias[]; isAdmin: boolean; onDelete: (a: Alias) => void }) {
  const { t } = useTranslation();
  const v = useTableView(rows, { alias: { get: (a: Alias) => a.alias }, canonical: { get: (a: Alias) => a.canonical } }, { key: "alias", dir: "asc" });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm" w={560}><DataTable.Thead><DataTable.Tr>
        <ColHead sort={v.sortProps("alias")} filter={v.text("alias")}>{t("Alias")}</ColHead>
        <ColHead sort={v.sortProps("canonical")} filter={v.text("canonical")}>{t("Se lee como")}</ColHead>
        {isAdmin && <DataTable.ActionsHead />}</DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a) => (
          <DataTable.Tr key={a.id}><DataTable.Td>{a.alias}</DataTable.Td><DataTable.Td>{a.canonical}</DataTable.Td>
            {isAdmin && <DataTable.Td><Btn kind="danger" size="row" icon="trash" onClick={() => onDelete(a)}>{t("Quitar")}</Btn></DataTable.Td>}</DataTable.Tr>))}</DataTable.Tbody></DataTable>
    </Stack>
  );
}

export default function Vocabulary({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const isAdmin = ["admin", "owner"].includes(role);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["vocab", graph], queryFn: () => get<Vocab>("vocabulary", { graph }) });
  const data = q.data;
  const { data: aliases = [] } = useQuery({ queryKey: ["vocab-aliases", graph], queryFn: () => get<Alias[]>("vocab/aliases", { graph }) });
  const [tab, setTab] = useTabParam("rel");
  const [sp] = useSearchParams();
  const [tail, setTail] = useState(false);
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [delAlias, setDelAlias] = useState<Alias | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["vocab", graph] }); qc.invalidateQueries({ queryKey: ["vocab-aliases", graph] }); };
  const add = useMutation({ mutationFn: () => send("POST", `vocab/aliases`, { alias: from, canonical: to }, { graph }), onSuccess: () => { setFrom(null); setTo(""); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `vocab/aliases/${id}`, undefined, { graph }), onSuccess: refresh });
  if (MOVED.includes(tab)) return <Navigate to={`/calidad?${sp.toString()}`} replace />;
  if (!data) return <DataState query={q} />;
  const s = data.summary;
  const rels = data.relations.filter((r) => !tail || r.facts <= 2);
  return (
    <Page>
      <PageHeader title={t("Vocabulario")} description={<>
        {t("El marco del brain: qué tipos de cosas y de relaciones existen y cómo se normalizan sus nombres. Vale para todo el brain, se aplica a lo que se ingiera a partir de ahora y lo cambian los administradores.")}{" "}
        {t("Ontología es lo declarado, lo que se pide al ingestor; Relaciones y Tipos de entidad son lo observado, lo que hay de verdad en el grafo. Compararlos dice qué falta declarar y qué sobra.")}{" "}
        {t("Para limpiar el contenido que ya hay (duplicados, contradicciones, tipos dudosos, hechos a revisar), ve a")}{" "}
        <Btn kind="link" component={Link} to="/calidad">{t("Calidad del contenido")}</Btn>.</>} />
      <StatGrid>
        <StatCard label={t("Tipos de relación")} value={`${s.relation_types_raw} → ${s.relation_types_canonical}`} hint={t("crudos → tras normalizar formato")} />
        <StatCard label={t("Hechos genéricos")} value={`${s.generic_pct} %`} hint={t("RELATES_TO, MENTIONED_IN…")} />
        <StatCard label={t("Cola larga")} value={s.long_tail_types} hint={t("{{long_tail_facts}} hechos en tipos con ≤2 usos", { long_tail_facts: s.long_tail_facts })} />
        <StatCard label={t("Entidades")} value={s.entities} />
      </StatGrid>
      <Tabs value={tab} onChange={setTab} className="ms-tabs-fill">
        <Tabs.List>
          <Tabs.Tab value="rel">{t("Relaciones")}</Tabs.Tab>
          <Tabs.Tab value="ent">{t("Tipos de entidad")}</Tabs.Tab>
          <Tabs.Tab value="onto">{t("Ontología")}</Tabs.Tab>
          <Tabs.Tab value="ali">{t("Alias")}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="rel" pt="sm">
          <TabIntro>{t("Las relaciones que hay de verdad en el grafo, con cuántos hechos usa cada una. Sirve para ver variantes del mismo nombre (RunsOn, IsHostedOn…) y unificarlas con un alias, lo que hace un administrador: no cambia el grafo y se puede quitar. Qué relaciones debe extraer el ingestor se declara en Ontología.")}</TabIntro>
          <Toggle my="xs" label={t("Solo cola larga (≤2 hechos)")} checked={tail} onChange={(e) => setTail(e.currentTarget.checked)} />
          <RelationsTable rows={rels} isAdmin={isAdmin} onUnify={(n) => { setFrom(n); setTo(""); }} />
        </Tabs.Panel>
        <Tabs.Panel value="ent" pt="sm"><VocabTypes graph={graph} isAdmin={isAdmin} /></Tabs.Panel>
        <Tabs.Panel value="onto" pt="sm"><VocabOntology graph={graph} role={role} /></Tabs.Panel>
        <Tabs.Panel value="ali" pt="sm">
          <FillArea><Stack gap="sm">
            <TabIntro>{t("Un alias hace que un nombre de relación se lea como otro (HostedOn como HOSTED_ON), al leer y al ingerir, sin cambiar los datos del grafo; se puede quitar. Se crean con «Unificar con…» en Relaciones.")}{" "}
              {t("Los nombres de las entidades fusionadas no están aquí: se guardan en la entidad principal, para que lo que se ingiera después con ese nombre vaya a ella, y la fusión se deshace en")}{" "}
              <Btn kind="link" component={Link} to="/calidad?tab=dup">{t("Calidad del contenido → Duplicados")}</Btn>.</TabIntro>
            {aliases.length === 0 ? <EmptyState>{t("Sin alias. Usa «Unificar con…» en la pestaña Relaciones.")}</EmptyState> : (
              <AliasesTable rows={aliases} isAdmin={isAdmin} onDelete={setDelAlias} />)}
          </Stack></FillArea>
        </Tabs.Panel>
      </Tabs>
      <ConfirmDialog opened={!!delAlias} onClose={() => setDelAlias(null)} title={t("Quitar alias")} action={t("Quitar alias")} subject={delAlias && `${delAlias.alias} → ${delAlias.canonical}`}
        warning={t("La relación vuelve a leerse con su nombre propio. Los hechos del grafo no se modifican.")} onConfirm={() => del.mutateAsync(delAlias!.id)} />
      <Modal opened={!!from} onClose={() => setFrom(null)} title={t("Unificar relación")} centered>
        <Stack>
          <Text size="sm"><b>{from}</b> {t("se leerá como el nombre que elijas. Los hechos del grafo no se modifican y puedes quitar el alias después.")}</Text>
          <ComboField label={t("Se lee como")} data={data.relations.map((r) => r.name).filter((n) => n !== from)} limit={50} value={to} onChange={setTo} placeholder={t("Elige una relación o escribe un nombre nuevo")} />
          <MutationError error={add.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setFrom(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" disabled={!to.trim()} loading={add.isPending} onClick={() => add.mutate()}>{t("Crear alias")}</Btn></Group>
        </Stack>
      </Modal>
    </Page>
  );
}
