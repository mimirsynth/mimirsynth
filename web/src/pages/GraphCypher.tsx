import { useTranslation } from "react-i18next";
import { Group } from "@mantine/core";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { T } from "../i18n";
import { send } from "../api";
import { Block, Btn, CellText, ClearFilters, ColHead, DataTable, EmptyState, FillArea, GraphCanvas, Loading, MenuButton, MutationError, Pill, QueryComposer, readEffects, Segments, SplitView,
  useTableView, typeColor, ViewBar, CANVAS, type CanvasLink, type CanvasNode } from "../ui";

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
const nodeName = (n: QNode) => String(n.properties.name ?? n.properties.fact ?? n.id);
const nodeType = (n: QNode, fallback: string) => n.labels.filter((l) => l !== "Entity")[0] ?? n.labels[0] ?? fallback;
const relName = (e: QEdge) => String(e.properties.name ?? e.relation);
// an embedding is a long list of numbers: nothing to read in a property table
const readable = ([, v]: [string, any]) => !(Array.isArray(v) && v.length > 16 && typeof v[0] === "number");

/** The Graph screen's Cypher tab: a read-only query, and what it returns as a graph (when it returns nodes) or as a table. */
export default function GraphCypher({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [q, setQ] = useState(EXAMPLES[0][1]);
  const [before, setBefore] = useState<string | null>(null);  // what an example or the history replaced, for «Undo»
  const [res, setRes] = useState<QRes | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [hist, setHist] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(HIST) || "[]"); } catch { return []; } });

  const pick = (text: string) => { if (text === q) return; setBefore(q); setQ(text); };
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const j = await send<QRes>("POST", `brains/${graph}/query`, { query: q });
      setRes(j); setBefore(null);
      const h = [q, ...hist.filter((x) => x !== q)].slice(0, 20); setHist(h); try { localStorage.setItem(HIST, JSON.stringify(h)); } catch { /* sin storage */ }
    } catch (e) { setErr(e); setRes(null); } finally { setBusy(false); }
  };

  return (
    <>
      <QueryComposer label={t("Consulta")} code value={q} onChange={(v) => { setQ(v); setBefore(null); }} onRun={run} busy={busy}
        runLabel={t("Ejecutar")} busyLabel={t("Ejecutando…")} placeholder="MATCH (n:Entity) RETURN n.name LIMIT 25"  // i18n-ok: Cypher, not words
        tools={<>
          <MenuButton label={t("Ejemplos")} items={EXAMPLES.map(([title, text]) => ({ key: title, label: t(title), onClick: () => pick(text) }))} />
          <MenuButton label={t("Historial")} items={hist.map((h) => ({ key: h, label: h.length > 90 ? `${h.slice(0, 90)}…` : h, onClick: () => pick(h) }))} />
          {before !== null && <Btn kind="ghost" icon="undo" onClick={() => { setQ(before); setBefore(null); }}>{t("Deshacer")}</Btn>}
        </>}
        status={res ? <>{t("{{total}} filas · {{ms}} ms", { total: res.total, ms: res.ms })}{res.truncated ? t(" · resultado recortado a 500 filas") : ""}</> : ""} />
      <MutationError error={err} />
      {!res && busy && <Loading label={t("Ejecutando…")} />}
      {!res && !err && !busy && <EmptyState>{t("Escribe una consulta o elige un ejemplo y pulsa Ejecutar: verás sus filas en una tabla y, si devuelve nodos, también en un grafo.")}</EmptyState>}
      {res && <CypherResult key={`${res.ms}-${res.total}-${res.columns.join()}`} res={res} />}
    </>
  );
}

/** One query's result: a bar to switch between graph and table (the graph only when nodes came back), then the canvas with the detail of
 *  what is picked beside it, or the table, every column sortable and filterable on its visible value. */
function CypherResult({ res }: { res: QRes }) {
  const { t } = useTranslation();
  const [view, setView] = useState(res.nodes.length ? "grafo" : "tabla");
  const [effects] = useState(readEffects);  // the one picked under «Explorar» for this device
  const [sel, setSel] = useState<{ node?: string; edge?: string }>({});
  const objs = useMemo(() => res.rows.map((r, i) => ({ i, r })), [res]);
  const cols = useMemo(() => Object.fromEntries(res.columns.map((c, j) => [c, { get: (o: { r: any[] }) => { const v = o.r[j]; return typeof v === "number" ? v : typeof v === "string" ? v : cell(v); } }])), [res]);
  const v = useTableView(objs, cols);

  // result -> the canvas (the Explore tab's, 2D with the force layout)
  const canvas = useMemo(() => ({
    nodes: res.nodes.map((n): CanvasNode => ({ id: n.id, color: typeColor(nodeType(n, t("Nodo"))), size: 8, caption: nodeName(n), visible: true, tooltip: `${nodeName(n)}\n${nodeType(n, t("Nodo"))}` })),
    // a fact's edge is a RELATES_TO whose own relation is in its `name`: that is the one worth reading on the link
    links: res.edges.map((e): CanvasLink => ({ id: e.id, source: e.source, target: e.target, label: relName(e), color: e.properties.invalid_at ? CANVAS.linkInvalid : CANVAS.link, dashed: !!e.properties.invalid_at, visible: true })),
  }), [res]); // eslint-disable-line react-hooks/exhaustive-deps

  const node = sel.node ? res.nodes.find((n) => n.id === sel.node) : undefined;
  const edge = sel.edge ? res.edges.find((e) => e.id === sel.edge) : undefined;
  const nameOf = (nid: string) => { const n = res.nodes.find((x) => x.id === nid); return n ? nodeName(n) : nid; };

  return (
    <>
      <ViewBar title={t("Resultado")} meta={view === "grafo" ? t("{{nodes}} nodos · {{edges}} aristas", { nodes: res.nodes.length, edges: res.edges.length }) : undefined}>
        {res.nodes.length > 0 && <Segments label={t("Ver como")} value={view} onChange={setView}
          data={[{ value: "grafo", label: t("Grafo") }, { value: "tabla", label: t("Tabla ({{n}})", { n: res.total }) }]} />}
        {view === "tabla" && <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />}
      </ViewBar>
      {view === "grafo" ? (
        <SplitView main={
          <div className="ms-canvas">
            <GraphCanvas nodes={canvas.nodes} links={canvas.links} effects={effects} selectedNode={sel.node} selectedLink={sel.edge}
              onNodeClick={(nid) => setSel({ node: nid })} onLinkClick={(lid) => setSel({ edge: lid })} onBackgroundClick={() => setSel({})} />
          </div>} aside={
          // the detail of what is picked on the canvas, as under «Explorar»
          <FillArea>
            {node ? (
              <Block title={nodeName(node)} actions={node.labels.includes("Entity") && node.properties.uuid
                ? <Btn size="row" icon="graph" component={Link} to={`/entidad/${node.properties.uuid}`}>{t("Ver página")}</Btn> : undefined}>
                <Group gap={4}>{node.labels.map((l) => <Pill key={l}>{l}</Pill>)}</Group>
                <Properties props={node.properties} />
              </Block>
            ) : edge ? (
              <Block title={relName(edge)}>
                <CellText sub={<>{nameOf(edge.source)} → {nameOf(edge.target)}</>}>{String(edge.properties.fact ?? "")}</CellText>
                <Properties props={edge.properties} />
              </Block>
            ) : <EmptyState>{t("Clic en un nodo o en una arista para ver el detalle.")}</EmptyState>}
          </FillArea>} />
      ) : res.rows.length ? (
        <FillArea>
          <DataTable fz="xs"><DataTable.Thead><DataTable.Tr>{res.columns.map((c) => <ColHead key={c} sort={v.sortProps(c)} filter={v.text(c)}>{c}</ColHead>)}</DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{v.rows.map((o) => <DataTable.Tr key={o.i}>{o.r.map((x, j) => <DataTable.Td key={j}>{entityUuid(x) ? <Link to={`/entidad/${entityUuid(x)}`}>{cell(x)}</Link> : cell(x)}</DataTable.Td>)}</DataTable.Tr>)}</DataTable.Tbody>
          </DataTable>
        </FillArea>
      ) : <EmptyState>{t("La consulta no ha devuelto ninguna fila.")}</EmptyState>}
    </>
  );
}

/** The properties of a picked node or edge, as stored in the graph. */
function Properties({ props }: { props: Record<string, any> }) {
  const { t } = useTranslation();
  const rows = Object.entries(props).filter(readable).sort(([a], [b]) => a.localeCompare(b));
  if (!rows.length) return null;
  return (
    <DataTable fz="xs" aria-label={t("Propiedades")}>
      <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Propiedad")}</DataTable.Th><DataTable.Th>{t("Valor")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
      <DataTable.Tbody>{rows.map(([k, val]) => (
        <DataTable.Tr key={k}><DataTable.Td><span className="ms-data">{k}</span></DataTable.Td><DataTable.Td>{cell(val)}</DataTable.Td></DataTable.Tr>))}
      </DataTable.Tbody>
    </DataTable>
  );
}
