import { useTranslation } from "react-i18next";
import { T } from "../i18n";
import { send } from "../api";
import { Group, Stack, Text } from "@mantine/core";
import { Btn, ClearFilters, ColHead, DataTable, FillArea, GraphCanvas, MenuButton, MutationError, QueryComposer, readEffects, Page, PageHeader, Tabs, useTableView, typeColor, CANVAS, type CanvasLink, type CanvasNode } from "../ui";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

type QNode = { id: string; labels: string[]; properties: Record<string, any> };
type QEdge = { id: string; relation: string; source: string; target: string; properties: Record<string, any> };
type QRes = { columns: string[]; rows: any[][]; truncated: boolean; total: number; nodes: QNode[]; edges: QEdge[]; ms: number };

// Examples that run on any brain: none names an entity the brain may not have.
const EXAMPLES: [string, string][] = [
  [T("Vecindad de la entidad más conectada"), "MATCH (n:Entity)-[r:RELATES_TO]-() WITH n, count(r) AS grado ORDER BY grado DESC LIMIT 1\nMATCH (n)-[r:RELATES_TO]-(m:Entity) RETURN n, r, m LIMIT 40"],
  [T("Hechos invalidados recientes"), "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NOT NULL RETURN a, r, b ORDER BY r.invalid_at DESC LIMIT 25"],
  [T("Entidades por grado"), "MATCH (n:Entity) OPTIONAL MATCH (n)-[r:RELATES_TO]-() RETURN n.name AS entidad, count(r) AS grado ORDER BY grado DESC LIMIT 30"],
  [T("Episodios recientes"), "MATCH (e:Episodic) RETURN e.name AS nombre, e.created_at AS creado ORDER BY e.created_at DESC LIMIT 20"],
  [T("Hechos por tipo de relación"), "MATCH ()-[r:RELATES_TO]->() RETURN r.name AS relacion, count(*) AS n ORDER BY n DESC"],
];
const HIST = "q-hist";
const cell = (v: any) => (v && typeof v === "object" ? (v._type === "node" ? `(${v.properties?.name ?? v.id}:${(v.labels ?? []).join(":")})` : v._type === "edge" ? `[${v.properties?.name ?? v.relation}]` : JSON.stringify(v).slice(0, 120)) : String(v ?? ""));

/** The uuid of an entity node in a result cell, to link it to its entity page. */
const entityUuid = (v: any): string | null => (v && v._type === "node" && (v.labels ?? []).includes("Entity") && v.properties?.uuid ? String(v.properties.uuid) : null);

/** Resultado de una consulta Cypher: columnas arbitrarias, cada una con orden y filtro de texto sobre su valor visible. */
function ResultTable({ columns, rows }: { columns: string[]; rows: any[][] }) {
  const objs = rows.map((r, i) => ({ i, r }));
  const cols = Object.fromEntries(columns.map((c, j) => [c, { get: (o: { r: any[] }) => { const v = o.r[j]; return typeof v === "number" ? v : typeof v === "string" ? v : cell(v); } }]));
  const v = useTableView(objs, cols);
  return (
    <FillArea><Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="xs"><DataTable.Thead><DataTable.Tr>{columns.map((c) => <ColHead key={c} sort={v.sortProps(c)} filter={v.text(c)}>{c}</ColHead>)}</DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((o) => <DataTable.Tr key={o.i}>{o.r.map((x, j) => <DataTable.Td key={j}>{entityUuid(x) ? <Link to={`/entidad/${entityUuid(x)}`}>{cell(x)}</Link> : cell(x)}</DataTable.Td>)}</DataTable.Tr>)}</DataTable.Tbody></DataTable>
    </Stack></FillArea>
  );
}

export default function Query({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [q, setQ] = useState(EXAMPLES[0][1]);
  const [before, setBefore] = useState<string | null>(null);  // what an example or the history replaced, for «Undo»
  const [res, setRes] = useState<QRes | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<string>("tabla");
  const [hist, setHist] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(HIST) || "[]"); } catch { return []; } });
  const [sel, setSel] = useState<string | null>(null);
  const [effects] = useState(readEffects);  // el que se eligió en Grafo para este dispositivo

  const pick = (text: string) => { if (text === q) return; setBefore(q); setQ(text); };
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const j = await send<QRes>("POST", `brains/${graph}/query`, { query: q });
      setRes(j); setSel(null); setTab(j.nodes.length ? "grafo" : "tabla"); setBefore(null);
      const h = [q, ...hist.filter((x) => x !== q)].slice(0, 20); setHist(h); try { localStorage.setItem(HIST, JSON.stringify(h)); } catch { /* sin storage */ }
    } catch (e) { setErr(e); setRes(null); } finally { setBusy(false); }
  };

  // resultado -> lienzo del grafo (el mismo de la pantalla Grafo, en 2D y con disposición de fuerza)
  const graphData = useMemo(() => {
    if (!res) return { nodes: [] as CanvasNode[], links: [] as CanvasLink[] };
    const lab = (n: QNode) => n.labels.filter((l) => l !== "Entity")[0] ?? n.labels[0] ?? t("Nodo");
    const name = (n: QNode) => String(n.properties.name ?? n.properties.fact ?? n.id);
    return {
      nodes: res.nodes.map((n) => ({ id: n.id, color: typeColor(lab(n)), size: 8, caption: name(n), visible: true, tooltip: `${name(n)}
${lab(n)}` })),
      // a fact's edge is a RELATES_TO whose own relation is in its `name`: that is the one worth reading on the link
      links: res.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, label: String(e.properties.name ?? e.relation), color: e.properties.invalid_at ? CANVAS.linkInvalid : CANVAS.link, dashed: !!e.properties.invalid_at, visible: true })),
    };
  }, [res]); // eslint-disable-line react-hooks/exhaustive-deps

  const selNode = res?.nodes.find((n) => n.id === sel);
  const selEntity = selNode && selNode.labels.includes("Entity") && selNode.properties.uuid ? { uuid: String(selNode.properties.uuid), name: String(selNode.properties.name ?? "") } : null;
  return (
    <Page fill>
      <PageHeader title={t("Consulta Cypher")} description={t("Consultas Cypher de solo lectura contra el grafo del brain: las entidades son nodos :Entity y cada hecho es una arista RELATES_TO con su relación en «name». Cualquier escritura se rechaza.")} />
      <QueryComposer label={t("Consulta")} code value={q} onChange={(v) => { setQ(v); setBefore(null); }} onRun={run} busy={busy}
        runLabel={t("Ejecutar")} busyLabel={t("Ejecutando…")} placeholder="MATCH (n:Entity) RETURN n.name LIMIT 25"  // i18n-ok: Cypher, not words
        tools={<>
          <MenuButton label={t("Ejemplos")} items={EXAMPLES.map(([title, text]) => ({ key: title, label: t(title), onClick: () => pick(text) }))} />
          <MenuButton label={t("Historial")} items={hist.map((h) => ({ key: h, label: h.length > 90 ? `${h.slice(0, 90)}…` : h, onClick: () => pick(h) }))} />
          {before !== null && <Btn kind="ghost" icon="undo" onClick={() => { setQ(before); setBefore(null); }}>{t("Deshacer")}</Btn>}
        </>}
        status={res ? <>{t("{{total}} filas · {{ms}} ms", { total: res.total, ms: res.ms })}{res.truncated ? t(" · resultado recortado a 500 filas") : ""}</> : ""} />
      <MutationError error={err} />
      {res && (
        <Tabs value={tab} onChange={(v) => setTab(v ?? "tabla")} className="ms-tabs-fill">
          <Tabs.List>
            <Tabs.Tab value="tabla">{t("Tabla ({{n}})", { n: res.total })}</Tabs.Tab>
            <Tabs.Tab value="grafo" disabled={!res.nodes.length}>{t("Grafo ({{nodes}} nodos · {{edges}} aristas)", { nodes: res.nodes.length, edges: res.edges.length })}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="tabla" className="ms-tabpanel-fill" pt="xs">
            <ResultTable key={res.ms + res.total} columns={res.columns} rows={res.rows} />
          </Tabs.Panel>
          <Tabs.Panel value="grafo" className="ms-tabpanel-fill" pt="xs">
            <div className="ms-canvas ms-canvas-fill">
              <GraphCanvas nodes={graphData.nodes} links={graphData.links} effects={effects} selectedNode={sel} onNodeClick={setSel} onBackgroundClick={() => setSel(null)} />
            </div>
            {selEntity && <Group gap="xs" mt="xs"><Text size="xs">{selEntity.name}</Text><Btn size="row" icon="graph" component={Link} to={`/entidad/${selEntity.uuid}`}>{t("Ver página")}</Btn></Group>}
          </Tabs.Panel>
        </Tabs>
      )}
    </Page>
  );
}
