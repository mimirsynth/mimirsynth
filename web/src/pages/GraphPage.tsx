import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { Check, FillArea, IconButton, Page, PageHeader, NumberField, Panel, Pill, Segments, Slider, TextField, NODE_PALETTE, CANVAS, SplitView, Legend, LegendSection, LegendItem } from "../ui";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "@falkordb/canvas";
import { fmt, get, GLink, GNode, GraphData, Overview } from "../api";

const PALETTE = NODE_PALETTE;
const DAY = 86_400_000;
const download = (name: string, type: string, data: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type })); a.download = name; a.click(); };
const id = (x: any) => (typeof x === "object" ? x.uuid ?? x.id : x);

export default function GraphPage({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const ov = useQuery({ queryKey: ["overview", graph], queryFn: () => get<Overview>("overview", { graph }) });
  const [params] = useSearchParams();
  const nodo = params.get("nodo") ?? "";  // llega desde Conocimiento: centra el grafo en esa entidad
  const [seeds, setSeeds] = useState(10);
  const [depth, setDepth] = useState(1);
  const [minDeg, setMinDeg] = useState(1);
  const [withInvalid, setWithInvalid] = useState(true);
  const [useTime, setUseTime] = useState(false);
  const [day, setDay] = useState<number | null>(null);
  const [layout, setLayout] = useState("force");
  const [dim, setDim] = useState("2d");
  const [paused, setPaused] = useState(false);
  const [extra, setExtra] = useState<GraphData[]>([]);
  const [sel, setSel] = useState<GNode | null>(null);
  const [selLink, setSelLink] = useState<GLink | null>(null);
  const [hiddenLabels, setHiddenLabels] = useState<Set<string>>(new Set());
  const [hiddenRels, setHiddenRels] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [legendOpen, setLegendOpen] = useState(() => window.innerWidth > 1000);
  const cv = useRef<any>(null);
  const box = useRef<HTMLDivElement>(null);
  const colorOf = useRef(new Map<string, string>());
  const color = (l?: string) => { const k = l ?? t("(sin tipo)"); if (!colorOf.current.has(k)) colorOf.current.set(k, PALETTE[colorOf.current.size % PALETTE.length]); return colorOf.current.get(k)!; };

  const t0 = ov.data?.first_episode_at ? new Date(ov.data.first_episode_at).getTime() : Date.now() - 90 * DAY;
  const total = Math.max(1, Math.ceil((Date.now() - t0) / DAY));
  const asOf = useTime && day !== null ? new Date(t0 + day * DAY + DAY - 1).toISOString() : "";
  useEffect(() => { if (day === null && ov.data) setDay(total); }, [ov.data, total, day]);
  useEffect(() => { setExtra([]); setSel(null); setSelLink(null); }, [graph, seeds, depth, withInvalid, asOf, nodo]);

  const base = useQuery({
    queryKey: ["graph", graph, seeds, depth, withInvalid, asOf, nodo],
    queryFn: () => get<GraphData>("graph", { graph, seeds, depth: nodo ? Math.max(depth, 1) : depth, cap: 120, include_invalidated: withInvalid, as_of: asOf, node: nodo }),
  });
  useEffect(() => { if (nodo && base.data) { const n = base.data.nodes.find((x) => x.uuid === nodo); if (n) setSel(n); } }, [nodo, base.data]);
  const mentions = useQuery({ queryKey: ["entity-docs", graph, sel?.uuid], enabled: !!sel, staleTime: 60_000,
    queryFn: () => get<{ documents: { document_id: number; title: string; snippet: string; chunks: number }[] }>("docs/mentions", { graph, entity: sel!.uuid }) });

  const { nodes, links } = useMemo(() => {
    const ns = new Map<string, GNode>(); const ls = new Map<string, GLink>();
    [base.data, ...extra].forEach((g) => g && (g.nodes.forEach((n) => ns.set(n.uuid, ns.get(n.uuid) ?? n)), g.links.forEach((l) => ls.set(l.uuid, l))));
    return { nodes: [...ns.values()], links: [...ls.values()].filter((l) => ns.has(id(l.source)) && ns.has(id(l.target))) };
  }, [base.data, extra]);

  const legendLabels = useMemo(() => { const m = new Map<string, number>(); nodes.forEach((n) => { const k = n.labels[0] ?? t("(sin tipo)"); m.set(k, (m.get(k) ?? 0) + 1); }); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [nodes]);
  const legendRels = useMemo(() => { const m = new Map<string, number>(); links.forEach((l) => m.set(l.name, (m.get(l.name) ?? 0) + 1)); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [links]);

  const nodeVisible = useCallback((n: GNode) => !hiddenLabels.has(n.labels[0] ?? t("(sin tipo)")) && (n.degree ?? 0) >= minDeg, [hiddenLabels, minDeg]);

  // datos -> canvas
  useEffect(() => {
    const c = cv.current; if (!c) return;
    const vis = new Set(nodes.filter(nodeVisible).map((n) => n.uuid));
    c.setData({
      nodes: nodes.map((n) => ({ id: n.uuid, labels: n.labels.length ? n.labels : [t("(sin tipo)")], color: color(n.labels[0]), visible: vis.has(n.uuid), size: 5 + Math.min(n.degree ?? 1, 40) / 3, caption: "name", data: { name: n.name, summary: n.summary, degree: n.degree } })),
      links: links.map((l) => ({ id: l.uuid, source: id(l.source), target: id(l.target), relationship: l.name, color: l.status === "invalidated" ? CANVAS.linkInvalid : CANVAS.link, visible: vis.has(id(l.source)) && vis.has(id(l.target)) && !hiddenRels.has(l.name), data: { fact: l.fact, status: l.status } })),
    });
  }, [nodes, links]); // eslint-disable-line react-hooks/exhaustive-deps

  // visibilidad (leyenda / grado mínimo) sin recolocar
  useEffect(() => {
    const c = cv.current; const g = c?.getGraphData?.(); if (!g) return;
    const byId = new Map(nodes.map((n) => [n.uuid, n]));
    g.nodes.forEach((n: any) => { const o = byId.get(String(n.id)); if (o) n.visible = nodeVisible(o); });
    g.links.forEach((l: any) => { const s = byId.get(String(id(l.source))), t = byId.get(String(id(l.target))); l.visible = !!s && !!t && nodeVisible(s) && nodeVisible(t) && !hiddenRels.has(l.relationship); });
    c.refresh?.();
  }, [hiddenLabels, hiddenRels, minDeg]); // eslint-disable-line react-hooks/exhaustive-deps

  // configuración + tamaño
  const expand = useCallback(async (nid: string) => {
    const g = await get<GraphData>("graph", { graph, node: nid, depth: 1, cap: 60, include_invalidated: withInvalid, as_of: asOf });
    setExtra((e) => [...e, g]);
  }, [graph, withInvalid, asOf]);

  useEffect(() => {
    const c = cv.current; if (!c) return;
    c.setConfig({
      backgroundColor: CANVAS.background, foregroundColor: CANVAS.foreground, captionsKeys: ["name"],
      nodeStyle: { fontFamily: "sans-serif" }, linkStyle: { fontFamily: "sans-serif" },
      isNodeSelected: (n: any) => n.id === sel?.uuid,
      isLinkSelected: (l: any) => l.id === selLink?.uuid,
      linkLineDash: (l: any) => (l.data?.status === "invalidated" ? [3, 3] : []),
      eventHandlers: {
        onNodeClick: (n: any) => { const o = nodes.find((x) => x.uuid === String(n.id)); if (o) { setSel(o); setSelLink(null); } },
        onNodeRightClick: (n: any) => expand(String(n.id)),
        onLinkClick: (l: any) => { const o = links.find((x) => x.uuid === String(l.id)); if (o) { setSelLink(o); setSel(null); } },
        onBackgroundClick: () => { setSel(null); setSelLink(null); },
      },
    });
    c.refresh?.();
  }, [nodes, links, sel, selLink, expand]);

  useEffect(() => { cv.current?.setLayout?.(layout); }, [layout]);
  useEffect(() => { cv.current?.setDimension?.(dim).catch(() => setDim("2d")); }, [dim]);
  useEffect(() => { cv.current?.setAnimation?.(!paused); }, [paused]);
  useEffect(() => {
    const el = box.current; if (!el) return;
    const apply = () => { const r = el.getBoundingClientRect(); cv.current?.setWidth?.(Math.floor(r.width)); cv.current?.setHeight?.(Math.floor(r.height)); };
    const ro = new ResizeObserver(apply); ro.observe(el); apply();
    return () => ro.disconnect();
  }, []);

  const doSearch = (q: string) => {
    setSearch(q); if (!q) return;
    const n = nodes.find((x) => x.name.toLowerCase().includes(q.toLowerCase()));
    if (n) { setSel(n); setSelLink(null); cv.current?.zoomToFit?.(2, (x: any) => x.id === n.uuid); }
  };
  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, k: string) => { const s = new Set(set); s.has(k) ? s.delete(k) : s.add(k); setter(s); };
  const nodeFacts = sel ? links.filter((l) => id(l.source) === sel.uuid || id(l.target) === sel.uuid) : [];
  const nameOf = (u: any) => nodes.find((n) => n.uuid === id(u))?.name ?? "";

  return (
    <Page>
      <PageHeader title={t("Grafo")} description={t("Entidades y hechos del brain como mapa. Elige cuántas semillas y saltos cargar; pulsa un nodo para ver sus hechos y los documentos que lo mencionan.")} />
      <Group gap="sm" align="flex-end" wrap="wrap">
        <NumberField label={t("Semillas")} value={seeds} min={5} max={100} onChange={(v) => setSeeds(Number(v) || 15)} w={90} size="xs" />
        <NumberField label={t("Saltos")} value={depth} min={0} max={2} onChange={(v) => setDepth(Number(v) || 0)} w={70} size="xs" />
        <NumberField label={t("Grado mín.")} value={minDeg} min={0} max={20} onChange={(v) => setMinDeg(Number(v) || 0)} w={85} size="xs" />
        <TextField label={t("Buscar nodo")} placeholder={t("Nextcloud…")} value={search} onChange={(e) => doSearch(e.currentTarget.value)} size="xs" w={170} />
        <Segments size="xs" value={layout} onChange={setLayout} data={[{ value: "force", label: t("Fuerza") }, { value: "radial", label: t("Radial") }, { value: "tree", label: t("Árbol") }]} />
        <Segments size="xs" value={dim} onChange={setDim} data={["2d", "3d"]} />
        <IconButton icon={paused ? "play" : "pause"} label={paused ? t("Reanudar simulación") : t("Pausar simulación")} onClick={() => setPaused(!paused)} />
        <IconButton icon="undo" label={t("Deshacer última expansión")} disabled={!extra.length} onClick={() => setExtra((e) => e.slice(0, -1))} />
        <IconButton icon="download" label={t("Exportar JSON")} onClick={() => download("grafo.json", "application/json", JSON.stringify({ nodes, links }, null, 2))} />
        <IconButton icon="image" label={t("Exportar imagen")} onClick={() => { const cn = cv.current?.shadowRoot?.querySelector("canvas") ?? cv.current?.querySelector?.("canvas"); if (cn) { const a = document.createElement("a"); a.href = cn.toDataURL("image/png"); a.download = "grafo.png"; a.click(); } }} />
        <IconButton icon="fit" label={t("Ajustar a la vista")} onClick={() => cv.current?.zoomToFit?.(1)} />
        <Check size="xs" label={t("Invalidados")} checked={withInvalid} onChange={(e) => setWithInvalid(e.currentTarget.checked)} />
        <Check size="xs" label={t("Viajar en el tiempo")} checked={useTime} onChange={(e) => setUseTime(e.currentTarget.checked)} />
      </Group>
      {useTime && day !== null && (
        <Group gap="md" wrap="nowrap">
          <Text size="xs" w={190}>{t("Qué sabíamos el {{date}}", { date: fmt(new Date(t0 + day * DAY).toISOString()).split(",")[0] })}</Text>
          <Slider className="ms-grow" min={0} max={total} value={day} onChange={setDay} />
        </Group>
      )}
      <SplitView main={<>
        <div ref={box} className="ms-canvas">
          <falkordb-canvas ref={cv} />
          <Legend open={legendOpen} onToggle={() => setLegendOpen(!legendOpen)}>
            <LegendSection>{t("Tipos")}</LegendSection>
            {legendLabels.map(([l, n]) => <LegendItem key={l} label={l} count={n} dot={color(l === t("(sin tipo)") ? undefined : l)} off={hiddenLabels.has(l)} onClick={() => toggle(hiddenLabels, setHiddenLabels, l)} />)}
            <LegendSection>{t("Relaciones")}</LegendSection>
            {legendRels.map(([r, n]) => <LegendItem key={r} label={r} count={n} off={hiddenRels.has(r)} onClick={() => toggle(hiddenRels, setHiddenRels, r)} />)}
          </Legend>
        </div></>} aside={
        <Panel withBorder p="sm" h="100%">
          <FillArea>
            {sel ? (
              <Stack gap="xs">
                <Text fw={700}>{sel.name}</Text>
                <Group gap={4}>{sel.labels.map((l) => <Pill key={l} size="xs">{l}</Pill>)}<Pill size="xs">{t("grado")} {sel.degree}</Pill></Group>
                <Text size="xs" c="dimmed" className="ms-prose">{sel.summary}</Text>
                <Text size="xs" fw={700}>{t("Hechos ({{count}})", { count: nodeFacts.length })}</Text>
                {nodeFacts.map((l) => <Text key={l.uuid} size="xs" td={l.status === "invalidated" ? "line-through" : undefined}>• {l.fact}</Text>)}
                {(mentions.data?.documents.length ?? 0) > 0 && <>
                  <Text size="xs" fw={700}>{t("Documentos que la mencionan ({{count}})", { count: mentions.data!.documents.length })}</Text>
                  {mentions.data!.documents.map((d) => (
                    <Stack key={d.document_id} gap={0}>
                      <Text size="xs" component={Link} to={`/conocimiento?doc=${d.document_id}`}>{d.title}{d.chunks > 1 ? t(" · {{chunks}} pasajes", { chunks: d.chunks }) : ""}</Text>
                      <Text size="xs" c="dimmed" lineClamp={2}>…{d.snippet}…</Text>
                    </Stack>))}</>}
                <Text size="xs" c="dimmed">{t("Clic derecho en un nodo: expandir vecindad.")}</Text>
              </Stack>
            ) : selLink ? (
              <Stack gap="xs">
                <Pill>{selLink.name}</Pill>
                <Text size="sm">{selLink.fact}</Text>
                <Text size="xs" c="dimmed">{nameOf(selLink.source)} → {nameOf(selLink.target)}</Text>
                <Text size="xs">{t("Válido desde")} {fmt(selLink.valid_at)}</Text>
                {selLink.invalid_at && <Text size="xs" c="dimmed">{t("Dejó de ser cierto")} {fmt(selLink.invalid_at)}</Text>}
              </Stack>
            ) : <Text size="sm" c="dimmed">{t("Clic en un nodo o en una arista para ver el detalle. Clic derecho en un nodo para expandirlo. Rueda para zoom, arrastra para mover. Las aristas discontinuas son hechos invalidados. Los elementos de la leyenda se pueden ocultar.")}</Text>}
          </FillArea>
        </Panel>} />
      <Text size="xs" c="dimmed">{t("{{nodes}} nodos · {{links}} hechos", { nodes: nodes.length, links: links.length })}{base.data?.truncated ? t(" · recortado por el tope de nodos") : ""}</Text>
    </Page>
  );
}
