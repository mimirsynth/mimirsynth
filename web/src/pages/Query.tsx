import { useTranslation } from "react-i18next";
import { T } from "../i18n";
import { langHeaders } from "../api";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, ClearFilters, ColHead, DataTable, FillArea, GraphCanvas, Notice, readEffects, Page, PageHeader, Pill, SelectField, Tabs, TextArea, useTableView, NODE_PALETTE, CANVAS, type CanvasLink, type CanvasNode } from "../ui";
import { useMemo, useState } from "react";

type QNode = { id: string; labels: string[]; properties: Record<string, any> };
type QEdge = { id: string; relation: string; source: string; target: string; properties: Record<string, any> };
type QRes = { columns: string[]; rows: any[][]; truncated: boolean; total: number; nodes: QNode[]; edges: QEdge[]; ms: number };

const EXAMPLES: [string, string][] = [
  [T("Hechos invalidados recientes"), "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.invalid_at IS NOT NULL RETURN a, r, b ORDER BY r.invalid_at DESC LIMIT 25"],
  [T("Vecindad de una entidad"), "MATCH (a:Entity)-[r:RELATES_TO]-(b:Entity) WHERE a.name CONTAINS 'Nextcloud' RETURN a, r, b LIMIT 40"],
  [T("Entidades por grado"), "MATCH (n:Entity) OPTIONAL MATCH (n)-[r:RELATES_TO]-() RETURN n.name AS entidad, count(r) AS grado ORDER BY grado DESC LIMIT 30"],
  [T("Episodios recientes"), "MATCH (e:Episodic) RETURN e.name AS nombre, e.created_at AS creado ORDER BY e.created_at DESC LIMIT 20"],
  [T("Hechos por tipo de relación"), "MATCH ()-[r:RELATES_TO]->() RETURN r.name AS relacion, count(*) AS n ORDER BY n DESC"],
];
const PALETTE = NODE_PALETTE;
const cell = (v: any) => (v && typeof v === "object" ? (v._type === "node" ? `(${v.properties?.name ?? v.id}:${(v.labels ?? []).join(":")})` : v._type === "edge" ? `[${v.relation}]` : JSON.stringify(v).slice(0, 120)) : String(v ?? ""));

/** Resultado de una consulta Cypher: columnas arbitrarias, cada una con orden y filtro de texto sobre su valor visible. */
function ResultTable({ columns, rows }: { columns: string[]; rows: any[][] }) {
  const objs = rows.map((r, i) => ({ i, r }));
  const cols = Object.fromEntries(columns.map((c, j) => [c, { get: (o: { r: any[] }) => { const v = o.r[j]; return typeof v === "number" ? v : typeof v === "string" ? v : cell(v); } }]));
  const v = useTableView(objs, cols);
  return (
    <FillArea><Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="xs"><DataTable.Thead><DataTable.Tr>{columns.map((c) => <ColHead key={c} sort={v.sortProps(c)} filter={v.text(c)}>{c}</ColHead>)}</DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((o) => <DataTable.Tr key={o.i}>{o.r.map((x, j) => <DataTable.Td key={j}>{cell(x)}</DataTable.Td>)}</DataTable.Tr>)}</DataTable.Tbody></DataTable>
    </Stack></FillArea>
  );
}

export default function Query({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [q, setQ] = useState(EXAMPLES[1][1]);
  const [res, setRes] = useState<QRes | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<string>("tabla");
  const [hist, setHist] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem("q-hist") || "[]"); } catch { return []; } });
  const [sel, setSel] = useState<string | null>(null);
  const [effects] = useState(readEffects);  // el que se eligió en Grafo para este dispositivo

  const run = async () => {
    setBusy(true); setErr("");
    try {
      const r = await fetch(`/api/brains/${graph}/query`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", ...langHeaders() }, body: JSON.stringify({ query: q }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail ?? r.statusText);
      setRes(j); setSel(null); setTab(j.nodes.length ? "grafo" : "tabla");
      const h = [q, ...hist.filter((x) => x !== q)].slice(0, 12); setHist(h); try { localStorage.setItem("q-hist", JSON.stringify(h)); } catch { /* sin storage */ }
    } catch (e: any) { setErr(String(e.message ?? e)); setRes(null); } finally { setBusy(false); }
  };

  // resultado -> lienzo del grafo (el mismo de la pantalla Grafo, en 2D y con disposición de fuerza)
  const graphData = useMemo(() => {
    if (!res) return { nodes: [] as CanvasNode[], links: [] as CanvasLink[] };
    const colors = new Map<string, string>(); const col = (l: string) => { if (!colors.has(l)) colors.set(l, PALETTE[colors.size % PALETTE.length]); return colors.get(l)!; };
    const lab = (n: QNode) => n.labels.filter((l) => l !== "Entity")[0] ?? n.labels[0] ?? t("Nodo");
    const name = (n: QNode) => String(n.properties.name ?? n.properties.fact ?? n.id);
    return {
      nodes: res.nodes.map((n) => ({ id: n.id, color: col(lab(n)), size: 8, caption: name(n), visible: true, tooltip: `${name(n)}
${lab(n)}` })),
      links: res.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, label: e.relation, color: e.properties.invalid_at ? CANVAS.linkInvalid : CANVAS.link, dashed: !!e.properties.invalid_at, visible: true })),
    };
  }, [res]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Page>
      <PageHeader title={t("Consulta")} description={t("Consultas Cypher de solo lectura contra el grafo del brain (Ctrl+Enter para ejecutar). Cualquier escritura se rechaza.")} />
      <div className="ms-querybox">
        <TextArea autosize minRows={3} maxRows={8} value={q} onChange={(e) => setQ(e.currentTarget.value)} className="ms-mono-input"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); }} placeholder={t("MATCH (n) RETURN n LIMIT 25   (Ctrl+Enter para ejecutar)")} />
        <Stack gap={6} className="ms-querybox-side">
          <Btn kind="primary" onClick={run} loading={busy}>{t("Ejecutar (Ctrl+Enter)")}</Btn>
          <SelectField placeholder={t("Ejemplos")} data={EXAMPLES.map(([title]) => ({ value: title, label: t(title) }))} onChange={(v) => v && setQ(EXAMPLES.find(([title]) => title === v)![1])} clearable />
          <SelectField placeholder={t("Historial")} data={hist.map((h, i) => ({ value: String(i), label: h.slice(0, 60) }))} onChange={(v) => v !== null && setQ(hist[Number(v)])} clearable />
        </Stack>
      </div>
      {err && <Notice tone="danger" p="xs">{err}</Notice>}
      {res && (
        <Tabs value={tab} onChange={(v) => setTab(v ?? "tabla")} className="ms-tabs-fill">
          <Tabs.List>
            <Tabs.Tab value="tabla">{t("Tabla (")}{res.total})</Tabs.Tab>
            <Tabs.Tab value="grafo" disabled={!res.nodes.length}>{t("Grafo (")}{res.nodes.length} {t("nodos ·")} {res.edges.length} {t("aristas)")}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="tabla" className="ms-tabpanel-fill" pt="xs">
            <ResultTable key={res.ms + res.total} columns={res.columns} rows={res.rows} />
          </Tabs.Panel>
          <Tabs.Panel value="grafo" className="ms-tabpanel-fill" pt="xs">
            <div className="ms-canvas ms-canvas-fill">
              <GraphCanvas nodes={graphData.nodes} links={graphData.links} effects={effects} selectedNode={sel} onNodeClick={setSel} onBackgroundClick={() => setSel(null)} />
            </div>
          </Tabs.Panel>
        </Tabs>
      )}
      {res && <Text size="xs" c="dimmed">{t("{{total}} filas · {{ms}} ms", { total: res.total, ms: res.ms })}{res.truncated ? t(" · resultado recortado a 500 filas") : ""}</Text>}
    </Page>
  );
}
