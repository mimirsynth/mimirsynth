import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { Btn, Check, FillArea, IconButton, Page, PageHeader, NumberField, Panel, Pill, Segments, SelectField, Slider, TextField, NODE_PALETTE, HALO_PALETTE, CANVAS, SplitView, Legend, LegendSection, LegendItem, GraphCanvas, Notice, type GraphCanvasHandle, type CanvasNode, type CanvasLink, type CanvasHalo, type Effects, type EffectsMode, type Layout } from "../ui";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fmt, get, GLink, GNode, GraphData, Grouping, Overview } from "../api";
import { T } from "../i18n";

const PALETTE = NODE_PALETTE;
const DAY = 86_400_000;
const download = (name: string, type: string, data: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type })); a.download = name; a.click(); };
const id = (x: any) => (typeof x === "object" ? x.uuid ?? x.id : x);
const GROUPINGS: [Grouping, string][] = [["source", T("Tipo de origen")], ["document", T("Documento")], ["author", T("Contribuidor")], ["token", T("Agente / token")], ["label", T("Tipo de entidad")]];
const MAX_HALOS = 8;  // los orígenes mayores llevan halo propio; el resto se junta en «Otros»
const OTHER = "__otros__";
const EFFECTS_KEY = "ms-graph-effects";  // por dispositivo, no en la cuenta: la GPU es del equipo, no de la persona
const readEffects = (): EffectsMode => { try { const v = localStorage.getItem(EFFECTS_KEY); return v === "full" || v === "reduced" ? v : "auto"; } catch { return "auto"; } };
const hasWebGL = () => { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; } };

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
  const [layout, setLayout] = useState<Layout>("force");
  const [dim, setDim] = useState<"2d" | "3d">("2d");
  const [paused, setPaused] = useState(false);
  const [extra, setExtra] = useState<GraphData[]>([]);
  const [sel, setSel] = useState<GNode | null>(null);
  const [selLink, setSelLink] = useState<GLink | null>(null);
  const [hiddenLabels, setHiddenLabels] = useState<Set<string>>(new Set());
  const [hiddenRels, setHiddenRels] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [legendOpen, setLegendOpen] = useState(() => window.innerWidth > 1000);
  const [groupBy, setGroupBy] = useState<Grouping>("source");
  const [halosOn, setHalosOn] = useState(true);
  const [hiddenOrigins, setHiddenOrigins] = useState<Set<string>>(new Set());
  const [onlyRobust, setOnlyRobust] = useState(false);
  const [effects, setEffects] = useState<EffectsMode>(readEffects);
  const [effective, setEffective] = useState<Effects>("full");
  const [no3d, setNo3d] = useState(false);
  const [slow3d, setSlow3d] = useState(false);
  const pickEffects = (v: EffectsMode) => { setEffects(v); try { localStorage.setItem(EFFECTS_KEY, v); } catch { /* sin almacenamiento: vale para esta visita */ } };
  const pickDim = (v: string) => { setSlow3d(false); if (v === "3d" && !hasWebGL()) { setNo3d(true); return; } setNo3d(false); setDim(v as "2d" | "3d"); };
  const onSlow = useCallback(() => setSlow3d(true), []);
  useEffect(() => setHiddenOrigins(new Set()), [groupBy]);
  // al filtrar quedan pocos nodos y al cambiar los halos se recolocan: se encuadran de nuevo (no en la primera carga)
  const viewKey = `${onlyRobust && groupBy !== "label"}|${groupBy}|${halosOn}|${[...hiddenOrigins].join(",")}`;
  const seenKey = useRef(viewKey);
  useEffect(() => {
    if (seenKey.current === viewKey) return;
    seenKey.current = viewKey;
    requestAnimationFrame(() => gc.current?.fit(600));
  }, [viewKey]);
  const gc = useRef<GraphCanvasHandle>(null);
  const force = layout === "force";  // los halos solo tienen sentido en la disposición de fuerza (2D y 3D)
  const colorOf = useRef(new Map<string, string>());
  const color = (l?: string) => { const k = l ?? t("(sin tipo)"); if (!colorOf.current.has(k)) colorOf.current.set(k, PALETTE[colorOf.current.size % PALETTE.length]); return colorOf.current.get(k)!; };

  const [now] = useState(() => Date.now());  // fijo: si cambiara en cada render, as_of también, y el grafo se pediría sin fin
  const t0 = ov.data?.first_episode_at ? new Date(ov.data.first_episode_at).getTime() : now - 90 * DAY;
  const total = Math.max(1, Math.ceil((now - t0) / DAY));
  const asOf = useTime && day !== null ? new Date(t0 + day * DAY + DAY - 1).toISOString() : "";
  useEffect(() => { if (day === null && ov.data) setDay(total); }, [ov.data, total, day]);
  useEffect(() => { setExtra([]); setSel(null); setSelLink(null); }, [graph, seeds, depth, withInvalid, asOf, nodo]);

  const base = useQuery({
    queryKey: ["graph", graph, seeds, depth, withInvalid, asOf, nodo],
    queryFn: () => get<GraphData>("graph", { graph, seeds, depth: nodo ? Math.max(depth, 1) : depth, cap: 120, include_invalidated: withInvalid, as_of: asOf, node: nodo, group_by: "source" }),
  });
  useEffect(() => { if (nodo && base.data) { const n = base.data.nodes.find((x) => x.uuid === nodo); if (n) { setSel(n); requestAnimationFrame(() => gc.current?.fit(600, (x) => x === nodo)); } } }, [nodo, base.data]);
  const mentions = useQuery({ queryKey: ["entity-docs", graph, sel?.uuid], enabled: !!sel, staleTime: 60_000,
    queryFn: () => get<{ documents: { document_id: number; title: string; snippet: string; chunks: number }[] }>("docs/mentions", { graph, entity: sel!.uuid }) });

  const { nodes, links } = useMemo(() => {
    const ns = new Map<string, GNode>(); const ls = new Map<string, GLink>();
    [base.data, ...extra].forEach((g) => g && (g.nodes.forEach((n) => ns.set(n.uuid, ns.get(n.uuid) ?? n)), g.links.forEach((l) => ls.set(l.uuid, l))));
    return { nodes: [...ns.values()], links: [...ls.values()].filter((l) => ns.has(id(l.source)) && ns.has(id(l.target))) };
  }, [base.data, extra]);

  const legendLabels = useMemo(() => { const m = new Map<string, number>(); nodes.forEach((n) => { const k = n.labels[0] ?? t("(sin tipo)"); m.set(k, (m.get(k) ?? 0) + 1); }); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [nodes]);
  const legendRels = useMemo(() => { const m = new Map<string, number>(); links.forEach((l) => m.set(l.name, (m.get(l.name) ?? 0) + 1)); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [links]);

  // procedencia: la API trae los orígenes de todas las agrupaciones, así que cambiar de agrupación no vuelve a pedir el grafo
  const srcOf = useCallback((x: GNode | GLink) => x.provenance?.[groupBy] ?? [], [groupBy]);
  const originName = useMemo(() => {
    const m = new Map<string, string>();
    [base.data, ...extra].forEach((g) => g?.groups && Object.values(g.groups).flat().forEach((o) => m.set(o.key, o.name)));
    return m;
  }, [base.data, extra]);
  const origins = useMemo(() => {
    const m = new Map<string, number>();
    nodes.forEach((n) => srcOf(n).forEach((k) => m.set(k, (m.get(k) ?? 0) + 1)));
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [nodes, srcOf]);
  const legendOrigins = useMemo(() => {
    const top = new Set(origins.slice(0, MAX_HALOS).map(([k]) => k));
    const out = origins.slice(0, MAX_HALOS).map(([k, n], i) => ({ key: k, name: originName.get(k) ?? k, count: n, color: HALO_PALETTE[i] }));
    const rest = nodes.filter((n) => srcOf(n).some((k) => !top.has(k))).length;
    if (rest) out.push({ key: OTHER, name: t("Otros"), count: rest, color: HALO_PALETTE[HALO_PALETTE.length - 1] });
    return out;
  }, [origins, originName, nodes, srcOf]); // eslint-disable-line react-hooks/exhaustive-deps
  const halos = useMemo<CanvasHalo[]>(() => (halosOn && force ? legendOrigins.filter((o) => !hiddenOrigins.has(o.key)) : []), [halosOn, force, legendOrigins, hiddenOrigins]);
  const haloOf = useCallback((k: string) => (legendOrigins.some((o) => o.key === k) ? k : OTHER), [legendOrigins]);

  // la robustez cuenta orígenes de la procedencia: tener dos tipos de entidad no confirma nada (y los hechos no tienen tipo)
  const robustness = groupBy !== "label";
  const robust = onlyRobust && robustness;
  const backed = useCallback((x: GNode | GLink) => robustness && srcOf(x).length >= 2, [robustness, srcOf]);
  const nodeVisible = useCallback((n: GNode) => !hiddenLabels.has(n.labels[0] ?? t("(sin tipo)")) && (n.degree ?? 0) >= minDeg && (!robust || backed(n)),
    [hiddenLabels, minDeg, robust, backed]); // eslint-disable-line react-hooks/exhaustive-deps
  const linkVisible = useCallback((l: GLink) => !hiddenRels.has(l.name) && (!robust || backed(l)), [hiddenRels, robust, backed]);

  // datos -> lienzo (2D o 3D); cambiar la visibilidad no recoloca
  const cnodes = useMemo<CanvasNode[]>(() => {
    const shown = new Set(halos.map((h) => h.key));
    return nodes.map((n) => ({ id: n.uuid, color: color(n.labels[0]), size: 5 + Math.min(n.degree ?? 1, 40) / 3, caption: n.name, visible: nodeVisible(n),
      groups: [...new Set(srcOf(n).map(haloOf))].filter((k) => shown.has(k)), ring: backed(n),
      tooltip: `${n.name}\n${n.labels[0] ?? t("(sin tipo)")} · ${t("Conexiones: {{count}}", { count: n.degree ?? 0 })}${robustness ? ` · ${t("Orígenes: {{count}}", { count: srcOf(n).length })}` : ""}` }));
  }, [nodes, nodeVisible, halos, srcOf, haloOf, backed, robustness]); // eslint-disable-line react-hooks/exhaustive-deps
  const clinks = useMemo<CanvasLink[]>(() => {
    const vis = new Set(cnodes.filter((n) => n.visible).map((n) => n.id));
    return links.map((l) => ({ id: l.uuid, source: id(l.source), target: id(l.target), label: l.name, color: l.status === "invalidated" ? CANVAS.linkInvalid : CANVAS.link,
      dashed: l.status === "invalidated", visible: vis.has(id(l.source)) && vis.has(id(l.target)) && linkVisible(l), strong: backed(l) }));
  }, [links, cnodes, linkVisible, backed]);
  const pickNode = useCallback((nid: string) => { const o = nodes.find((x) => x.uuid === nid); if (o) { setSel(o); setSelLink(null); } }, [nodes]);
  const pickLink = useCallback((lid: string) => { const o = links.find((x) => x.uuid === lid); if (o) { setSelLink(o); setSel(null); } }, [links]);
  const clearPick = useCallback(() => { setSel(null); setSelLink(null); }, []);

  const expand = useCallback(async (nid: string) => {
    const g = await get<GraphData>("graph", { graph, node: nid, depth: 1, cap: 60, include_invalidated: withInvalid, as_of: asOf, group_by: "source" });
    setExtra((e) => [...e, g]);
  }, [graph, withInvalid, asOf]);

  const doSearch = (q: string) => {
    setSearch(q); if (!q) return;
    const n = nodes.find((x) => x.name.toLowerCase().includes(q.toLowerCase()));
    if (n) { setSel(n); setSelLink(null); gc.current?.fit(600, (x) => x === n.uuid); }
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
        <Segments size="xs" value={layout} onChange={(v) => setLayout(v as Layout)} data={[{ value: "force", label: t("Fuerza") }, { value: "radial", label: t("Radial") }, { value: "tree", label: t("Árbol") }]} />
        <Segments size="xs" value={dim} onChange={pickDim} data={["2d", "3d"]} />
        <SelectField label={t("Agrupar por")} value={groupBy} onChange={(v) => v && setGroupBy(v as Grouping)} allowDeselect={false} w={160}
          data={GROUPINGS.map(([v, l]) => ({ value: v, label: t(l) }))} />
        <SelectField label={t("Efectos gráficos")} value={effects} onChange={(v) => v && pickEffects(v as EffectsMode)} allowDeselect={false} w={190}
          data={[{ value: "auto", label: effects === "auto" && effective === "reduced" ? t("Automático (reducido)") : t("Automático") }, { value: "full", label: t("Completo") }, { value: "reduced", label: t("Reducido") }]} />
        <IconButton icon={paused ? "play" : "pause"} label={paused ? t("Reanudar simulación") : t("Pausar simulación")} disabled={!force} onClick={() => setPaused(!paused)} />
        <IconButton icon="undo" label={t("Deshacer última expansión")} disabled={!extra.length} onClick={() => setExtra((e) => e.slice(0, -1))} />
        <IconButton icon="download" label={t("Exportar JSON")} onClick={() => download("grafo.json", "application/json", JSON.stringify({ nodes, links }, null, 2))} />
        <IconButton icon="image" label={t("Exportar imagen")} onClick={() => { const png = gc.current?.toPng(); if (png) { const a = document.createElement("a"); a.href = png; a.download = "grafo.png"; a.click(); } }} />
        <IconButton icon="fit" label={t("Ajustar a la vista")} onClick={() => gc.current?.fit(400)} />
        <Check size="xs" label={t("Invalidados")} checked={withInvalid} onChange={(e) => setWithInvalid(e.currentTarget.checked)} />
        <Check size="xs" label={t("Viajar en el tiempo")} checked={useTime} onChange={(e) => setUseTime(e.currentTarget.checked)} />
        <Check size="xs" label={t("Halos por origen")} checked={halosOn && force} disabled={!force} title={force ? undefined : t("Los halos solo se dibujan en la disposición de fuerza.")} onChange={(e) => setHalosOn(e.currentTarget.checked)} />
        <Check size="xs" label={t("Solo confirmados por 2 o más orígenes")} checked={robust} disabled={!robustness} onChange={(e) => setOnlyRobust(e.currentTarget.checked)}
          title={robustness ? undefined : t("Con «Tipo de entidad» no hay orígenes que contar: elige otra agrupación.")} />
      </Group>
      {no3d && <Notice tone="warn" p="xs">{t("Este navegador no tiene WebGL, así que la vista 3D no está disponible. El grafo sigue en 2D.")}</Notice>}
      {slow3d && dim === "3d" && (
        <Notice tone="warn" p="xs">
          <Group gap="sm" justify="space-between">{t("El 3D va lento en este equipo, incluso con los efectos reducidos. La vista 2D muestra lo mismo.")}<Btn size="row" onClick={() => pickDim("2d")}>{t("Volver a 2D")}</Btn></Group>
        </Notice>)}
      {useTime && day !== null && (
        <Group gap="md" wrap="nowrap">
          <Text size="xs" w={190}>{t("Qué sabíamos el {{date}}", { date: fmt(new Date(t0 + day * DAY).toISOString()).split(",")[0] })}</Text>
          <Slider className="ms-grow" min={0} max={total} value={day} onChange={setDay} />
        </Group>
      )}
      <SplitView main={<>
        <div className="ms-canvas">
          <GraphCanvas ref={gc} nodes={cnodes} links={clinks} halos={halos} dim={dim} layout={layout} root={nodo || undefined} effects={effects} onEffects={setEffective} onSlow={onSlow}
            busy={base.isFetching ? t("Calculando el grafo…") : undefined} selectedNode={sel?.uuid} selectedLink={selLink?.uuid} paused={paused}
            onNodeClick={pickNode} onNodeContextMenu={expand} onLinkClick={pickLink} onBackgroundClick={clearPick} />
          <Legend open={legendOpen} onToggle={() => setLegendOpen(!legendOpen)}>
            {force && halosOn && legendOrigins.length > 0 && <>
              <LegendSection>{t("Orígenes")}</LegendSection>
              {legendOrigins.map((o) => <LegendItem key={o.key} label={o.name} count={o.count} dot={o.color} off={hiddenOrigins.has(o.key)} onClick={() => toggle(hiddenOrigins, setHiddenOrigins, o.key)} />)}
            </>}
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
                <Sources keys={srcOf(sel)} name={(k) => originName.get(k) ?? k} />
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
                <Sources keys={srcOf(selLink)} name={(k) => originName.get(k) ?? k} />
              </Stack>
            ) : <Text size="sm" c="dimmed">{t("Clic en un nodo o en una arista para ver el detalle. Clic derecho en un nodo para expandirlo. Rueda para zoom, arrastra para mover. Las aristas discontinuas son hechos invalidados. Los elementos de la leyenda se pueden ocultar.")}</Text>}
          </FillArea>
        </Panel>} />
      <Text size="xs" c="dimmed">{t("{{nodes}} nodos · {{links}} hechos", { nodes: nodes.length, links: links.length })}{base.data?.truncated ? t(" · recortado por el tope de nodos") : ""}</Text>
    </Page>
  );
}

/** Orígenes que respaldan un nodo o un hecho, según la agrupación elegida. */
function Sources({ keys, name }: { keys: string[]; name: (k: string) => string }) {
  const { t } = useTranslation();
  return (
    <Stack gap={2}>
      <Text size="xs" fw={700}>{t("Orígenes ({{count}})", { count: keys.length })}</Text>
      {keys.length ? <Group gap={4}>{keys.map((k) => <Pill key={k} size="xs">{name(k)}</Pill>)}</Group> : <Text size="xs" c="dimmed">{t("Sin origen conocido")}</Text>}
    </Stack>
  );
}
